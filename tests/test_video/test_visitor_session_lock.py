"""访客会话**不可清空** + 同 IP 兜底复用（防「清 Cookie 刷新配额」）。

## 为什么需要这层闸

访客配额计数落在 ``rag_visitor.upload_count``，归属键是 ``visitor_id``；
而 ``visitor_id`` 由 ``VisitorService.issue()`` **每次签发都新生成**。于是只要还存在
任何一条「没有 Cookie 就发一个新访客」的路径，用户就能把「剩余次数」刷回满格：

1. 点界面上的「重新开始（清空访客会话）」→ 旧行为直接删掉访客 Cookie；
2. 手动清浏览器 Cookie / 换一个无痕窗口；
3. 脚本循环 ``POST /api/auth/visitor``（该端点原本免鉴权且每次都发新身份）。

三条路径逐一堵死，本文件逐条锁住：

| 闸 | 断言 |
| --- | --- |
| ``POST /api/auth/logout`` 访客侧 403 | 且**不下发任何删除 Cookie 头**（删了与清空等效） |
| 账号退出 | 只删 ``rag_session``，**不动**访客 Cookie（否则顺带重置配额） |
| 同 IP 复用 | 无 Cookie 时复用既有访客，**不新建、不下发 Cookie、不轮换 token** |
| ``POST /api/auth/visitor`` | 同 IP 已有活跃访客时返回 ``reused: true``，不再无限发新身份 |

反向验证：``VIDEO_VISITOR_BIND_IP=0`` 时同 IP 会重新发新访客 —— 即「同 IP 复用」
这一条如果被删掉，本文件的第 4 条会立刻变红。
"""
from __future__ import annotations

import types
import uuid

import pytest
from fastapi import Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.router_auth import (
    VISITOR_SESSION_CLEAR_FORBIDDEN,
    init_visitor,
    logout,
)
from src.auth.sessions import SessionService
from src.auth.visitor import VisitorService
from src.core.security import require_user_or_visitor
from src.db.models import User, Visitor
from src.shared.errors import AppError
from src.video.config import VisitorQuotaSettings
from src.video.quota import VisitorTaskQuota

# 固定出口 IP：同 IP 复用是本文件的主角，不能随机化
IP = "203.0.113.7"


@pytest.fixture
async def engine_maker(migrated_pg_url: str):
    eng = create_async_engine(migrated_pg_url)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    yield maker
    await eng.dispose()


@pytest.fixture(autouse=True)
async def _clean(engine_maker):
    async with engine_maker() as db:
        await db.execute(
            text("TRUNCATE rag_visitor_quota_log, rag_visitor, rag_video_task CASCADE")
        )
        await db.commit()
    yield


def _app(maker):
    return types.SimpleNamespace(state=types.SimpleNamespace(session_factory=maker))


def _request(maker):
    return types.SimpleNamespace(
        app=_app(maker), client=types.SimpleNamespace(host=IP)
    )


def _set_cookie_headers(response: Response) -> str:
    return "; ".join(response.headers.getlist("set-cookie"))


async def _issue(maker, *, ip: str = IP):
    async with maker() as db:
        return await VisitorService(db).issue(ip=ip)


# ── 1. 访客调 logout → 403，且不下发任何删除 Cookie 头 ─────────────
async def test_visitor_logout_forbidden_and_no_cookie_wipe(engine_maker):
    maker = engine_maker
    issued = await _issue(maker)

    async with maker() as db:
        response = Response()
        with pytest.raises(AppError) as exc:
            await logout(
                response, db, rag_session=None, video_visitor=issued.raw_token
            )

    assert exc.value.status_code == 403
    assert exc.value.code == VISITOR_SESSION_CLEAR_FORBIDDEN
    # 关键：不能下发任何 set-cookie —— 删掉 video_visitor 与「清空」等效
    assert _set_cookie_headers(response) == ""

    # 访客行原样保留（含计数）
    async with maker() as db:
        v = await db.scalar(
            select(Visitor).where(Visitor.visitor_id == issued.visitor_id)
        )
        assert v is not None
        assert v.status == "active"


# ── 2. 账号退出只删 rag_session，不动访客 Cookie ──────────────────
async def test_account_logout_keeps_visitor_cookie(engine_maker):
    maker = engine_maker
    issued = await _issue(maker)

    async with maker() as db:
        user = User(
            username=f"admin-{uuid.uuid4().hex[:8]}",
            password_hash="x",
            role="account_admin",
            status="active",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        session = await SessionService(db).issue(user.id)

    async with maker() as db:
        response = Response()
        await logout(
            response, db, rag_session=session.raw_token, video_visitor=issued.raw_token
        )

    headers = _set_cookie_headers(response)
    assert "rag_session=" in headers
    # 访客 Cookie 必须原样留着：删掉它 = 下次请求换新访客 = 配额重置
    assert "video_visitor" not in headers
    async with maker() as db:
        assert await db.scalar(select(func.count()).select_from(Visitor)) == 1


# ── 3. 无任何会话时 logout 幂等成功（不写删除 Cookie 头） ──────────
async def test_logout_without_session_is_idempotent(engine_maker):
    maker = engine_maker
    async with maker() as db:
        response = Response()
        out = await logout(response, db, rag_session=None, video_visitor=None)
    assert out == {"success": True, "data": None}
    assert _set_cookie_headers(response) == ""


# ── 4. 同 IP 复用：清掉 Cookie 也换不出新配额（本文件的主角） ──────
async def test_same_ip_reuse_keeps_quota(engine_maker):
    maker = engine_maker

    # 首次访问：签发访客并下发 Cookie，用掉 2 条
    async with maker() as db:
        first_cookie = Response()
        first = await require_user_or_visitor(
            _request(maker), first_cookie, rag_session=None, video_visitor=None, db=db
        )
        await VisitorTaskQuota(db, first).check_and_consume_task("task-1")
        await VisitorTaskQuota(db, first).check_and_consume_task("task-2")
    assert "set-cookie" in first_cookie.headers

    # 模拟用户手动清掉浏览器 Cookie（或换无痕窗口）：请求不再带 video_visitor
    async with maker() as db:
        second_cookie = Response()
        second = await require_user_or_visitor(
            _request(maker), second_cookie, rag_session=None, video_visitor=None, db=db
        )

    assert second.visitor_id == first.visitor_id, (
        "同 IP 应复用既有访客；若这里发出新访客，清 Cookie 就能把配额刷回满格"
    )
    # 复用分支故意不下发凭据：覆盖 token_hash 会让同 IP 其他浏览器的 Cookie 立刻失效
    assert _set_cookie_headers(second_cookie) == ""

    async with maker() as db:
        snap = await VisitorTaskQuota(db, second).snapshot()
    assert snap["tasks_used"] == 2, "复用必须带着已用次数，而不是从 0 开始"
    assert snap["tasks_max"] == 5


# ── 5. 复用不动既有 Cookie：同 IP 两个浏览器不会互相顶掉 ──────────
async def test_reuse_does_not_rotate_existing_token(engine_maker):
    maker = engine_maker

    # 浏览器 A：正常带 Cookie 访问
    async with maker() as db:
        issued = await VisitorService(db).issue(ip=IP)
    async with maker() as db:
        a1 = await require_user_or_visitor(
            _request(maker),
            Response(),
            rag_session=None,
            video_visitor=issued.raw_token,
            db=db,
        )
    assert a1.visitor_id == issued.visitor_id

    # 浏览器 B：同一出口、无 Cookie → 复用 A 的身份，但不下发 Cookie
    async with maker() as db:
        b_cookie = Response()
        b = await require_user_or_visitor(
            _request(maker), b_cookie, rag_session=None, video_visitor=None, db=db
        )
    assert b.visitor_id == issued.visitor_id
    assert _set_cookie_headers(b_cookie) == ""

    # 回到 A：原 Cookie 仍必须有效（若复用分支轮换了 token，这里会掉到新访客）
    async with maker() as db:
        a2 = await require_user_or_visitor(
            _request(maker),
            Response(),
            rag_session=None,
            video_visitor=issued.raw_token,
            db=db,
        )
    assert a2.visitor_id == issued.visitor_id
    async with maker() as db:
        assert await db.scalar(select(func.count()).select_from(Visitor)) == 1


# ── 6. 反向验证 / 逃生开关：VIDEO_VISITOR_BIND_IP=0 时重新发新访客 ─
async def test_bind_ip_disabled_mints_new_visitor(engine_maker, monkeypatch):
    maker = engine_maker
    async with maker() as db:
        first = await require_user_or_visitor(
            _request(maker), Response(), rag_session=None, video_visitor=None, db=db
        )

    monkeypatch.setenv("VIDEO_VISITOR_BIND_IP", "0")
    async with maker() as db:
        cookie = Response()
        second = await require_user_or_visitor(
            _request(maker), cookie, rag_session=None, video_visitor=None, db=db
        )

    assert second.visitor_id != first.visitor_id, (
        "关掉同 IP 复用后应当回到「每次发新访客」—— 反过来说明第 4 条锁的正是这个行为"
    )
    assert "set-cookie" in cookie.headers


# ── 7. POST /api/auth/visitor 不再是「无限刷身份」入口 ────────────
async def test_init_visitor_reuses_within_same_ip(engine_maker):
    maker = engine_maker
    async with maker() as db:
        first_cookie = Response()
        first = await init_visitor(_request(maker), first_cookie, db)
    assert first["data"]["reused"] is False
    assert "set-cookie" in first_cookie.headers

    async with maker() as db:
        second_cookie = Response()
        second = await init_visitor(_request(maker), second_cookie, db)
    assert second["data"]["reused"] is True
    assert second["data"]["visitor_id"] == first["data"]["visitor_id"]
    assert _set_cookie_headers(second_cookie) == ""

    async with maker() as db:
        assert await db.scalar(select(func.count()).select_from(Visitor)) == 1


# ── 8. 设置项：默认开；只有显式的假值才算关 ──────────────────────
def test_bind_ip_setting_default_and_env(monkeypatch):
    monkeypatch.delenv("VIDEO_VISITOR_BIND_IP", raising=False)
    assert VisitorQuotaSettings.load().bind_ip is True

    for value in ("0", "false", "FALSE", "no", "off"):
        monkeypatch.setenv("VIDEO_VISITOR_BIND_IP", value)
        assert VisitorQuotaSettings.load().bind_ip is False, value

    for value in ("1", "true", "on", "yes", "", "typo"):
        monkeypatch.setenv("VIDEO_VISITOR_BIND_IP", value)
        assert VisitorQuotaSettings.load().bind_ip is True, value
