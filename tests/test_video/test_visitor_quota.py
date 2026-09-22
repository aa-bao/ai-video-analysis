"""阶段 6 · 访客「解析条数」配额集成测试（方案 §11.7，与 P1 同构）。

覆盖：
1. 访客自动签发（影子账号 + rag_visitor 行 + Cookie）
2. 第 6 条任务被拒 403，且不落任何产物目录 / 任务记录 / 不扣次数
3. 超时长（DURATION_LIMIT_EXCEEDED）→ 未受理失败，绝不扣次数
4. 坏链（VIDEO_BAD_URL）→ 未受理失败，绝不扣次数
5. 受理成功按 ref_id 幂等扣减，恰好 +1；账号不扣
6. owner_visitor_id / owner_user_id 正确，两访客相互隔离
7. 篡改保护（把扣减移到时长检查点之前）→ 超时长也会扣（即 item 3 会变红）；恢复后通过

配额闸门语义：超限一律 HTTP 403（绝不用 401），错误码 VIDEO_QUOTA_EXCEEDED。
"""
from __future__ import annotations

import asyncio
import os
import types
from pathlib import Path

import pytest
from fastapi import Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.auth.visitor import VisitorService
from src.core.identity import RequestIdentity
from src.core.security import require_user_or_visitor
from src.db.models import VideoTaskRecord, Visitor, VisitorQuotaLog
from src.shared.errors import AppError
from src.video.config import VideoConfig, VisitorQuotaSettings
from src.video.quota import VideoQuotaExceeded, VisitorTaskQuota
from src.video.router import SubmitTaskRequest, submit_task
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
    return VideoTaskManager(VideoConfig(**kwargs), lambda: VideoAgentSettings())


def _app_with(mgr: VideoTaskManager, session_factory):
    return types.SimpleNamespace(state=types.SimpleNamespace(video_manager=mgr, session_factory=session_factory))


def _request(app):
    return types.SimpleNamespace(app=app, client=types.SimpleNamespace(host="127.0.0.1"))


@pytest.fixture
async def engine_maker(migrated_pg_url: str):
    eng = create_async_engine(migrated_pg_url)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    yield maker
    await eng.dispose()


@pytest.fixture(autouse=True)
async def _clean(engine_maker):
    async with engine_maker() as db:
        await db.execute(text("TRUNCATE rag_visitor_quota_log, rag_visitor, rag_video_task CASCADE"))
        await db.commit()
    yield


async def _issue_visitor(maker) -> tuple[object, int]:
    """签发一个访客，返回 (visitor_id, shadow_user_id)。"""
    async with maker() as db:
        issued = await VisitorService(db).issue(ip="127.0.0.1")
        return issued.visitor_id, issued.owner_user_id


def _visitor_principal(visitor_id: str, shadow_user_id: int) -> RequestIdentity:
    return RequestIdentity.for_visitor(visitor_id, shadow_user_id=shadow_user_id)


# ── 1. 访客自动签发 ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_guest_auto_issue(engine_maker, monkeypatch):
    """无会话 Cookie 时 require_user_or_visitor 自动签发访客并写 Cookie。"""
    maker = engine_maker
    async with maker() as db:
        request = _request(types.SimpleNamespace(state=types.SimpleNamespace(session_factory=maker)))
        response = Response()
        identity = await require_user_or_visitor(
            request, response, rag_session=None, video_visitor=None, db=db
        )

    assert identity.kind == "visitor"
    assert identity.is_visitor is True
    assert identity.visitor_id
    # Cookie 已写入（HttpOnly / strict / path=/，明文 token 仅回传一次）
    assert response.headers.get("set-cookie")
    assert "video_visitor" in response.headers.get("set-cookie")

    async with maker() as db:
        v = await db.scalar(select(Visitor).where(Visitor.visitor_id == identity.visitor_id))
        assert v is not None
        assert v.status == "active"
        # 影子账号：username='v:' || visitor_id，不可登录
        from src.db.models import User

        u = await db.scalar(select(User).where(User.id == v.owner_user_id))
        assert u is not None
        assert u.username == f"v:{identity.visitor_id}"
        assert u.status == "disabled"


# ── 2. 第 6 条任务被拒 403，且完全不受理 ─────────────────────────
@pytest.mark.asyncio
async def test_sixth_task_rejected_403(tmp_path, engine_maker, monkeypatch):
    maker = engine_maker
    visitor_id, shadow = await _issue_visitor(maker)
    # 预置已用满 5 条
    async with maker() as db:
        v = await db.scalar(select(Visitor).where(Visitor.visitor_id == visitor_id))
        v.upload_count = 5
        await db.commit()

    mgr = _manager(tmp_path)
    app = _app_with(mgr, maker)
    spy = {"called": False}

    def fake_submit(*_a, **_k):
        spy["called"] = True
        return {"task_id": "x", "status": "submitted"}

    monkeypatch.setattr(mgr, "submit", fake_submit)
    monkeypatch.setattr(mgr, "start_background", lambda *_a, **_k: None)
    monkeypatch.setattr(mgr, "persist_to_db", lambda *_a, **_k: None)

    async with maker() as db:
        principal = _visitor_principal(visitor_id, shadow)
        body = SubmitTaskRequest(source="https://example.com/video.mp4", kind="url")
        with pytest.raises(VideoQuotaExceeded) as exc:
            await submit_task(body, _request(app), principal, db)
    assert exc.value.status_code == 403
    assert exc.value.code == "VIDEO_QUOTA_EXCEEDED"

    # 未受理：submit 未被调用；无任务记录；无配额流水
    assert spy["called"] is False
    async with maker() as db:
        assert await db.scalar(
            select(func.count()).select_from(VideoTaskRecord)
        ) == 0
        assert await db.scalar(
            select(func.count()).select_from(VisitorQuotaLog)
            .where(VisitorQuotaLog.visitor_id == visitor_id)
        ) == 0


# ── 3. 超时长 → 未受理失败，绝不扣次数 ───────────────────────────
@pytest.mark.asyncio
async def test_duration_exceed_does_not_consume(tmp_path, engine_maker, monkeypatch):
    maker = engine_maker
    visitor_id, shadow = await _issue_visitor(maker)
    mgr = _manager(tmp_path)
    mgr._app = _app_with(mgr, maker)

    # 让时长探测返回超长；内容类型直接判为视频，跳过网络
    monkeypatch.setattr("src.video.acquire.media_duration", lambda *a, **k: 99999.0)
    async def _rt(*a, **k):
        return "video"
    monkeypatch.setattr(mgr, "_resolve_content_type", _rt)

    calls: list[tuple] = []
    real_consume = mgr._consume_visitor_quota

    async def _spy(task_id):
        calls.append(task_id)
        return await real_consume(task_id)
    monkeypatch.setattr(mgr, "_consume_visitor_quota", _spy)

    fake = tmp_path / "clip.mp4"
    fake.write_bytes(b"fake")
    state = mgr.submit(str(fake), owner_user_id=shadow, owner_visitor_id=visitor_id, is_visitor=True)
    await mgr.run(state["task_id"], str(fake), kind="file")

    st = mgr._load(state["task_id"])
    assert st["status"] == "failed"
    assert st.get("error_code") == "DURATION_LIMIT_EXCEEDED"
    # 关键：时长超限属「未受理」，扣减逻辑绝未被触达
    assert calls == [], "超时长不应触发配额扣减"
    async with maker() as db:
        assert await db.scalar(
            select(func.count()).select_from(VisitorQuotaLog)
            .where(VisitorQuotaLog.visitor_id == visitor_id)
        ) == 0


# ── 4. 坏链 → 未受理失败，绝不扣次数 ─────────────────────────────
@pytest.mark.asyncio
async def test_bad_url_does_not_consume(tmp_path, engine_maker, monkeypatch):
    maker = engine_maker
    visitor_id, shadow = await _issue_visitor(maker)
    mgr = _manager(tmp_path)
    app = _app_with(mgr, maker)
    spy = {"called": False}

    def fake_submit(*_a, **_k):
        spy["called"] = True
        return {"task_id": "x"}
    monkeypatch.setattr(mgr, "submit", fake_submit)
    monkeypatch.setattr(mgr, "start_background", lambda *_a, **_k: None)
    monkeypatch.setattr(mgr, "persist_to_db", lambda *_a, **_k: None)

    async with maker() as db:
        principal = _visitor_principal(visitor_id, shadow)
        body = SubmitTaskRequest(source="this is not a url", kind="url")
        with pytest.raises(AppError) as exc:
            await submit_task(body, _request(app), principal, db)
    assert exc.value.code == "VIDEO_BAD_URL"
    assert spy["called"] is False
    async with maker() as db:
        assert await db.scalar(
            select(func.count()).select_from(VisitorQuotaLog)
            .where(VisitorQuotaLog.visitor_id == visitor_id)
        ) == 0


# ── 5. 受理成功按 ref_id 幂等扣减，恰好 +1；账号不扣 ──────────────
@pytest.mark.asyncio
async def test_consume_exactly_once_per_ref(engine_maker):
    maker = engine_maker
    visitor_id, shadow = await _issue_visitor(maker)

    async with maker() as db:
        principal = _visitor_principal(visitor_id, shadow)
        quota = VisitorTaskQuota(db, principal)
        # 第一次受理成功 → +1
        await quota.check_and_consume_task("task-A")
        # 同一 ref 重复（幂等）→ 仍 +1
        await quota.check_and_consume_task("task-A")
        # 第二个不同 ref → +1 = 2
        await quota.check_and_consume_task("task-B")

        v = await db.scalar(select(Visitor).where(Visitor.visitor_id == visitor_id))
        assert v.upload_count == 2
        assert await db.scalar(
            select(func.count()).select_from(VisitorQuotaLog)
            .where(VisitorQuotaLog.visitor_id == visitor_id)
        ) == 2
        snap = await quota.snapshot()
        assert snap == {"tasks_used": 2, "tasks_max": 5, "max_duration_seconds": 1200}

    # 账号（非访客）一律放行、不落库
    async with maker() as db:
        account = RequestIdentity.for_local_user(1)
        aq = VisitorTaskQuota(db, account)
        await aq.check_and_consume_task("anything")
        assert await db.scalar(select(func.count()).select_from(VisitorQuotaLog)) == 2
        assert (await aq.snapshot())["tasks_used"] == 0


# ── 6. owner_visitor_id / owner_user_id 正确，两访客隔离 ──────────
@pytest.mark.asyncio
async def test_owner_visitor_id_and_isolation(tmp_path, engine_maker, monkeypatch):
    maker = engine_maker
    va_id, sa = await _issue_visitor(maker)
    vb_id, sb = await _issue_visitor(maker)
    assert va_id != vb_id

    mgr = _manager(tmp_path)
    mgr._app = _app_with(mgr, maker)
    monkeypatch.setattr(mgr, "start_background", lambda *_a, **_k: None)

    async with maker() as db:
        pa = _visitor_principal(va_id, sa)
        body = SubmitTaskRequest(source="https://example.com/a.mp4", kind="url")
        await submit_task(body, _request(mgr._app), pa, db)

        pb = _visitor_principal(vb_id, sb)
        body = SubmitTaskRequest(source="https://example.com/b.mp4", kind="url")
        await submit_task(body, _request(mgr._app), pb, db)

    async with maker() as db:
        ra = await db.scalar(
            select(VideoTaskRecord).where(VideoTaskRecord.owner_visitor_id == va_id)
        )
        rb = await db.scalar(
            select(VideoTaskRecord).where(VideoTaskRecord.owner_visitor_id == vb_id)
        )
        assert ra is not None and rb is not None
        assert ra.owner_visitor_id == va_id and ra.owner_user_id == sa
        assert rb.owner_visitor_id == vb_id and rb.owner_user_id == sb
        # 两访客隔离：归属键互不相同
        assert ra.owner_visitor_id != rb.owner_visitor_id
        assert ra.owner_user_id != rb.owner_user_id


# ── 7. 篡改保护（扣减移到时长检查点之前）→ 超时长也会扣（item 3 变红）；恢复后通过 ──
@pytest.mark.asyncio
async def test_falsification_removing_duration_protection(tmp_path, engine_maker, monkeypatch):
    """反向验证：若有人把扣减从「时长检查点之后」误移到「之前」，
    超时长任务也会扣次数（即 item 3 的断言会变红）。本测试先证明「坏改法」会扣，
    再说明「正确实现」（item 3 已实现）不会扣。"""
    maker = engine_maker
    visitor_id, shadow = await _issue_visitor(maker)
    mgr = _manager(tmp_path)
    mgr._app = _app_with(mgr, maker)
    monkeypatch.setattr("src.video.acquire.media_duration", lambda *a, **k: 99999.0)
    async def _rt(*a, **k):
        return "video"
    monkeypatch.setattr(mgr, "_resolve_content_type", _rt)

    # 坏改法：在 _run_pipeline 最前面就扣减（绕过时长检查点）
    orig = mgr._run_pipeline

    async def _wrapped(task_id, source, *, frames, kind, content_type, channel):
        await mgr._consume_visitor_quota(task_id)  # 时序错误：应在时长检查点之后
        return await orig(task_id, source, frames=frames, kind=kind,
                          content_type=content_type, channel=channel)
    monkeypatch.setattr(mgr, "_run_pipeline", _wrapped)

    fake = tmp_path / "clip.mp4"
    fake.write_bytes(b"fake")
    state = mgr.submit(str(fake), owner_user_id=shadow, owner_visitor_id=visitor_id, is_visitor=True)
    await mgr.run(state["task_id"], str(fake), kind="file")

    # 坏改法下：超时长却已扣次数（item 3 的「绝不扣」断言会失败 → 红）
    async with maker() as db:
        assert await db.scalar(
            select(func.count()).select_from(VisitorQuotaLog)
            .where(VisitorQuotaLog.visitor_id == visitor_id)
        ) == 1

    # 恢复（item 3 已用正确实现）：重新跑一遍，扣减不应发生
    async with maker() as db:
        v = await db.scalar(select(Visitor).where(Visitor.visitor_id == visitor_id))
        v.upload_count = 0
        await db.commit()
    # 去掉坏改法：_run_pipeline 用真实实现（扣减在时长检查点之后）
    monkeypatch.undo()
    fake2 = tmp_path / "clip2.mp4"
    fake2.write_bytes(b"fake")
    state2 = mgr.submit(str(fake2), owner_user_id=shadow, owner_visitor_id=visitor_id, is_visitor=True)
    await mgr.run(state2["task_id"], str(fake2), kind="file")
    async with maker() as db:
        assert await db.scalar(
            select(func.count()).select_from(VisitorQuotaLog)
            .where(VisitorQuotaLog.visitor_id == visitor_id)
        ) == 1  # 仍是 1（恢复后这次超时长未扣）


# ── 配额设置 env 覆盖 ─────────────────────────────────────────────
def test_quota_settings_env_override(monkeypatch):
    monkeypatch.setenv("VIDEO_QUOTA_MAX_TASKS", "3")
    monkeypatch.setenv("VIDEO_QUOTA_MAX_DURATION_SECONDS", "600")
    s = VisitorQuotaSettings.load()
    assert s.max_tasks == 3
    assert s.max_duration_seconds == 600


def test_quota_settings_defaults():
    s = VisitorQuotaSettings.load()
    assert s.max_tasks == 5
    assert s.max_duration_seconds == 1200
