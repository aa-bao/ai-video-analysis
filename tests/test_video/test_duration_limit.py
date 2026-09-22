"""P2 · 单条视频时长闸门（方案 §8.2 阶段 5 第 5 条）。

覆盖三件事：
1. 常量与方案定案一致（20 分钟上限 / 任务墙钟 3600s）；
2. 三个检查点的判定语义（等于上限放行、超过拒绝、时长未知不误杀）；
3. **「未受理」是可区分的** —— 拒绝后状态里必须留稳定错误码，
   因为方案 §11.7 规定这类失败在配额上不扣次数，阶段 6 的闸门靠这个码判断。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.video.config import VideoConfig
from src.video.service import (
    MAX_TASK_DURATION_SECONDS,
    REJECT_DURATION_LIMIT,
    STATUS_FAILED,
    VideoTaskError,
    VideoTaskManager,
    VideoTaskRejected,
    _TASK_TIMEOUT_SECONDS,
)
from src.video.settings import VideoAgentSettings


def _manager(tmp_path: Path) -> VideoTaskManager:
    config = VideoConfig(
        task_root=tmp_path / "tasks",
        output_root=tmp_path / "output",
        upload_dir=tmp_path / "uploads",
        library_root=tmp_path / "library",
        cookie_file=None,
        douyin_cookie_file=tmp_path / "cookies_douyin.txt",
        wx_cookie_file=tmp_path / "wx-cookies" / "cookies.json",
        python="python",
    )
    return VideoTaskManager(config, lambda: VideoAgentSettings())


def test_limits_match_phase5_decisions() -> None:
    """20 分钟上限；任务墙钟由 1800 放宽到 3600（D14）—— 20 分钟源全流程跑得完。"""
    assert MAX_TASK_DURATION_SECONDS == 1200
    assert _TASK_TIMEOUT_SECONDS == 3600
    assert REJECT_DURATION_LIMIT == "DURATION_LIMIT_EXCEEDED"


def test_duration_exactly_at_limit_is_accepted(tmp_path: Path) -> None:
    """边界：正好 20 分钟必须放行（`<=` 而不是 `<`）。"""
    manager = _manager(tmp_path)
    manager._enforce_duration_limit(
        "boundary", float(MAX_TASK_DURATION_SECONDS), checkpoint="captions_fetched"
    )


def test_unknown_duration_is_not_rejected(tmp_path: Path) -> None:
    """时长未知（0）不能当成"超长" —— 否则字幕/探测拿不到时长的源会被全量误杀。"""
    manager = _manager(tmp_path)
    manager._enforce_duration_limit("unknown", 0.0, checkpoint="captions_fetched")


@pytest.mark.parametrize(
    "checkpoint", ["captions_fetched", "audio_downloaded", "local_probed"]
)
def test_duration_over_limit_is_rejected_at_every_checkpoint(
    tmp_path: Path, checkpoint: str
) -> None:
    """三个检查点语义一致，不能只在主检查点生效。"""
    manager = _manager(tmp_path)
    with pytest.raises(VideoTaskRejected) as error:
        manager._enforce_duration_limit("too-long", 1200.5, checkpoint=checkpoint)

    assert error.value.code == REJECT_DURATION_LIMIT
    assert isinstance(error.value, VideoTaskError)
    assert "20 分钟" in str(error.value)


@pytest.mark.asyncio
async def test_rejected_task_records_stable_error_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """拒绝路径必须把码写进状态与事件 —— 这是阶段 6「未受理不扣次数」的唯一依据。"""
    manager = _manager(tmp_path)
    task_id = "task-rejected"
    state_path = manager._state_path(task_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"task_id": task_id, "status": "submitted", "stage": "submitted"}),
        encoding="utf-8",
    )

    async def reject(*_args: object, **_kwargs: object) -> None:
        raise VideoTaskRejected(
            "视频时长 25.0 分钟，超过 20 分钟上限，已拒绝处理。"
        )

    monkeypatch.setattr(manager, "_run_pipeline", reject)

    await manager.run(task_id, "https://public.example/video")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == STATUS_FAILED
    assert state["error_code"] == REJECT_DURATION_LIMIT
    assert "20 分钟上限" in state["error"]

    codes = [
        (event.get("data") or {}).get("error_code") for event in state.get("events") or []
    ]
    assert REJECT_DURATION_LIMIT in codes


@pytest.mark.asyncio
async def test_ordinary_failure_has_no_rejection_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """反向断言：普通失败**不能**带上「未受理」码，否则配额会放过本该扣次数的任务。"""
    manager = _manager(tmp_path)
    task_id = "task-broken"
    state_path = manager._state_path(task_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"task_id": task_id, "status": "submitted", "stage": "submitted"}),
        encoding="utf-8",
    )

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("yt-dlp produced no audio")

    monkeypatch.setattr(manager, "_run_pipeline", boom)

    await manager.run(task_id, "https://public.example/video")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == STATUS_FAILED
    assert "error_code" not in state
    assert "任务执行异常" in state["error"]
