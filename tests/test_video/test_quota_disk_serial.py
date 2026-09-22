"""W4 · 产物硬配额 / 磁盘告警 / 全局串行 的验证（方案 §7.3 磁盘专项 / §11.4 / §11.7）。

覆盖：
1. 阈值内 → 受理（check_artifact_quota 不抛错）
2. 超阈值 → 拒绝，错误码 ARTIFACT_QUOTA_EXCEEDED，且未创建任何产物目录/任务记录
3. 磁盘告警状态机：同一阈值只报一次；降回后再升重报
4. 配额统计边界：空目录 / 嵌套子目录 / 不存在目录
5. 视频任务全局串行 1：行为钉桩（两条任务不重叠）+ 结构钉桩（Semaphore(1)）
6. 只读端点 /api/video/disk 暴露用法与级别
"""
from __future__ import annotations

import asyncio
import time
import types
from pathlib import Path

import pytest

from src.shared.errors import AppError
from src.video.config import VideoConfig
from src.video.quota import (
    ArtifactUsage,
    DiskAlertMonitor,
    directory_size,
)
from src.video.service import VideoTaskManager
from src.video.settings import VideoAgentSettings

GIB = 1024 ** 3


def _manager(tmp_path: Path, **overrides) -> VideoTaskManager:
    kwargs = dict(
        task_root=tmp_path / "tasks",
        output_root=tmp_path / "output",
        upload_dir=tmp_path / "uploads",
        library_root=tmp_path / "library",
        cookie_file=None,
        douyin_cookie_file=tmp_path / "cookies_douyin.txt",
        wx_cookie_file=tmp_path / "wx-cookies" / "cookies.json",
        python="python",
        artifact_quota_bytes=35 * GIB,
        disk_warn_percent=80,
        disk_critical_percent=90,
    )
    kwargs.update(overrides)
    config = VideoConfig(**kwargs)
    return VideoTaskManager(config, lambda: VideoAgentSettings())


# ── 4. 配额统计边界 ───────────────────────────────────────────────

def test_directory_size_boundaries(tmp_path: Path) -> None:
    # 不存在的目录 → 0（不抛错）
    assert directory_size(tmp_path / "does_not_exist") == 0
    # 空目录 → 0
    empty = tmp_path / "empty"
    empty.mkdir()
    assert directory_size(empty) == 0
    # 嵌套子目录：递归求和
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "f1.bin").write_bytes(b"abc")          # 3
    sub = nested / "sub"
    sub.mkdir()
    (sub / "f2.bin").write_bytes(b"xy")              # 2
    assert directory_size(nested) == 5
    # 文件不可访问（权限/异常）不抛错：用不存在子路径模拟
    assert directory_size(nested / "gone" / "x") == 0


def test_artifact_usage_sums_configured_dirs(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "uploads").mkdir()
    (tmp_path / "output" / "a.bin").write_bytes(b"12345")   # 5
    (tmp_path / "tasks" / "state.json").write_bytes(b"ab")  # 2
    (tmp_path / "uploads" / "v.bin").write_bytes(b"xyz")     # 3
    mgr = _manager(tmp_path)
    mgr._artifact_usage.reset_cache()
    assert mgr.artifact_bytes_used(force=True) == 10


def test_artifact_usage_cache_returns_same_value_within_ttl(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "a.bin").write_bytes(b"x" * 4)
    mgr = _manager(tmp_path)
    mgr._artifact_usage.reset_cache()
    first = mgr.artifact_bytes_used(force=False)   # cold → computes
    (tmp_path / "output" / "b.bin").write_bytes(b"y" * 100)  # write after cache
    second = mgr.artifact_bytes_used(force=False)  # within TTL → stale cached
    assert first == 4
    assert second == first     # 缓存未过期，未重新全量遍历（节流）
    assert mgr.artifact_bytes_used(force=True) == 104  # force 重算看到新文件


# ── 1. 阈值内 → 受理 ──────────────────────────────────────────────

def test_quota_accepts_when_under_limit(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    mgr = _manager(tmp_path, artifact_quota_bytes=10 ** 9)  # 1 GB 上限，目录为空
    mgr._artifact_usage.reset_cache()
    # 不应抛错
    mgr.check_artifact_quota()
    assert mgr.artifact_bytes_used(force=True) == 0


# ── 2. 超阈值 → 拒绝 + 错误码 + 未创建记录 ───────────────────────

def test_quota_rejects_when_over_limit(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "big.bin").write_bytes(b"z" * 20)  # 20 字节
    # 配额设为 1 字节 → 必然超
    mgr = _manager(tmp_path, artifact_quota_bytes=1)
    mgr._artifact_usage.reset_cache()
    with pytest.raises(AppError) as exc:
        mgr.check_artifact_quota()
    assert exc.value.code == "ARTIFACT_QUOTA_EXCEEDED"
    assert exc.value.status_code == 507
    # 检查本身不创建任何产物目录 / 任务记录
    assert not any((tmp_path / "tasks").glob("*.json"))


def test_submit_rejected_before_creating_record(tmp_path: Path, monkeypatch) -> None:
    """router.submit_task 必须在 submit 之前做配额检查（fail-closed）。"""
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "big.bin").write_bytes(b"z" * 20)
    mgr = _manager(tmp_path, artifact_quota_bytes=1)
    mgr._artifact_usage.reset_cache()

    spy = {"submit_called": False}

    def fake_submit(*_a, **_k):
        spy["submit_called"] = True
        return {"task_id": "t", "status": "submitted"}

    monkeypatch.setattr(mgr, "submit", fake_submit)
    monkeypatch.setattr(mgr, "start_background", lambda *_a, **_k: None)
    monkeypatch.setattr(mgr, "persist_to_db", lambda *_a, **_k: None)

    # 构造最小 Request / App 使 _manager(request) 返回我们的 manager
    app_state = types.SimpleNamespace(video_manager=mgr, session_factory=None)
    app = types.SimpleNamespace(state=app_state)
    request = types.SimpleNamespace(app=app)
    principal = types.SimpleNamespace(user_id=1, owner_key="k", kind="account")

    from src.video.router import SubmitTaskRequest, submit_task

    body = SubmitTaskRequest(source="https://1.2.3.4/video.mp4", kind="url")
    with pytest.raises(AppError) as exc:
        asyncio.run(submit_task(body, request, principal))  # type: ignore[arg-type]
    assert exc.value.code == "ARTIFACT_QUOTA_EXCEEDED"
    assert spy["submit_called"] is False
    assert not any((tmp_path / "tasks").glob("*.json"))


# ── 3. 磁盘告警状态机 ─────────────────────────────────────────────

def test_disk_alert_logs_only_on_transition(caplog) -> None:
    """同一阈值只报一次；降回阈值以下再升上来才重报。"""
    import logging

    mon = DiskAlertMonitor(Path("/"), warn_percent=80, critical_percent=90)
    with caplog.at_level(logging.DEBUG, logger="src.video.quota"):
        n0 = len(caplog.records)
        assert mon.evaluate(50) == "normal"
        assert len(caplog.records) == n0          # 初始即 normal，无跃迁不报
        mon.evaluate(85)
        assert len(caplog.records) == n0 + 1      # 进入 warn：报一次
        mon.evaluate(85)
        assert len(caplog.records) == n0 + 1      # 停留 warn：不再报
        mon.evaluate(95)
        assert len(caplog.records) == n0 + 2      # 进入 critical：报一次
        mon.evaluate(95)
        assert len(caplog.records) == n0 + 2      # 停留 critical：不再报
        mon.evaluate(70)
        assert len(caplog.records) == n0 + 3      # 回落 normal：报一次
        mon.evaluate(85)
        assert len(caplog.records) == n0 + 4      # 再次升到 warn：重报


def test_disk_alert_levels_and_thresholds() -> None:
    mon = DiskAlertMonitor(Path("/"), warn_percent=80, critical_percent=90)
    assert mon.evaluate(10) == "normal"
    assert mon.evaluate(80) == "warn"        # 等于 warn 即告警
    assert mon.evaluate(90) == "critical"    # 等于 critical 即严重
    assert mon.level in {"normal", "warn", "critical"}


# ── 5. 视频任务全局串行 1 ────────────────────────────────────────

def test_serial_semaphore_is_one() -> None:
    """结构钉桩：全局串行 1 是容量前提，必须由 Semaphore(1) 承载（防被无意改并发）。"""
    import asyncio

    mgr = _manager(Path("/tmp"))  # 不写盘，仅查结构
    assert isinstance(mgr._serial_semaphore, asyncio.Semaphore)
    assert mgr._serial_semaphore._value == 1


@pytest.mark.asyncio
async def test_global_serial_execution_no_overlap(tmp_path: Path, monkeypatch) -> None:
    """行为钉桩：同时提交两条任务，运行窗口不得重叠（真正串行）。"""
    mgr = _manager(tmp_path)
    events: list[tuple[str, str, float]] = []

    async def fake_pipeline(task_id: str, *_a, **_k) -> None:
        events.append(("start", task_id, time.monotonic()))
        await asyncio.sleep(0.05)
        events.append(("end", task_id, time.monotonic()))

    monkeypatch.setattr(mgr, "_run_pipeline", fake_pipeline)

    # 同时提交两条；若实现被改成并发，两条会重叠运行
    mgr.start_background("task-a", "https://1.2.3.4/a.mp4")
    mgr.start_background("task-b", "https://1.2.3.4/b.mp4")

    for _ in range(300):
        if sum(1 for e in events if e[0] == "end") >= 2:
            break
        await asyncio.sleep(0.01)

    starts = {tid: t for (k, tid, t) in events if k == "start"}
    ends = {tid: t for (k, tid, t) in events if k == "end"}
    assert set(starts) == {"task-a", "task-b"}
    sa, ea = starts["task-a"], ends["task-a"]
    sb, eb = starts["task-b"], ends["task-b"]
    # 无重叠：b 的开始时间必须 >= a 的结束时间（严格串行）
    assert sb >= ea, f"任务重叠：a=({sa},{ea}) b=({sb},{eb})"


# ── 6. 只读端点 /api/video/disk ─────────────────────────────────

def test_disk_endpoint_exposes_usage_and_level(tmp_path: Path, monkeypatch) -> None:
    mgr = _manager(tmp_path)
    monkeypatch.setattr(
        mgr, "disk_status",
        lambda: {"usage_percent": 42.5, "level": "normal",
                 "warn_percent": 80, "critical_percent": 90},
    )
    app_state = types.SimpleNamespace(video_manager=mgr, session_factory=None)
    app = types.SimpleNamespace(state=app_state)
    request = types.SimpleNamespace(app=app)
    principal = types.SimpleNamespace(user_id=1, owner_key="k", kind="account")

    from src.video.router import get_disk_status

    resp = asyncio.run(get_disk_status(request, principal))  # type: ignore[arg-type]
    assert resp["success"] is True
    data = resp["data"]
    assert data["usage_percent"] == 42.5
    assert data["level"] == "normal"
    assert data["warn_percent"] == 80
    assert data["critical_percent"] == 90


def test_quota_config_defaults() -> None:
    """env 口径：缺省 35 GiB / 80% / 90%（其它 agent 会在 compose / .env.example 写同名变量）。"""
    cfg = VideoConfig(
        task_root=Path("/x/tasks"), output_root=Path("/x/output"),
        upload_dir=Path("/x/uploads"), library_root=Path("/x/library"),
        cookie_file=None, douyin_cookie_file=Path("/x/d.txt"),
        wx_cookie_file=Path("/x/w.json"), python="python",
    )
    assert cfg.artifact_quota_bytes == 35 * GIB
    assert cfg.disk_warn_percent == 80
    assert cfg.disk_critical_percent == 90
