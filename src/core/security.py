"""鉴权依赖（FastAPI dependency providers）。

阶段 1 从 `src/api/dependencies.py` 迁到这里，以解除 `api ⇄ video` 循环
（方案 §8.2 阶段 1 第 5 条、§6.1 目标结构的 `core/security.py`）。

阶段 2 剥离平台后，鉴权只剩**本地账号**一条路径：

- `DEV_AUTH_BYPASS=1` 且 `APP_ENV=development` 时按管理员放行（仅本地开发）；
- 否则校验本地 `rag_session` Cookie。

原 `_platform_principal`（平台 SSO 会话）与 `_conformance_principal`
（门禁夹具会话）已随 `src/platform/` 一并删除。

⚠️ 中间态说明：`router_auth.login` 目前只在 development 开放本地口令登录
（阶段 1 的口径），因此 test / production 环境下**尚无可用登录入口**。
这是阶段 6（免登录访客 + 管理员登录，方案 §11.5「/login 仅管理员」）要补齐的，
不是遗漏。
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from fastapi import Cookie, Depends, Request, Response, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.sessions import SessionService
from src.auth.visitor import (
    VISITOR_COOKIE,
    VisitorService,
    visitor_bind_ip_enabled,
)
from src.core.identity import ROLE_ADMIN, RequestIdentity
from src.db.models import User, Visitor
from src.shared.errors import AppError

logger = logging.getLogger(__name__)

# 本地开发跳过登录校验：DEV_AUTH_BYPASS=1 且 APP_ENV=development 时所有请求视为该用户
_DEV_AUTH_BYPASS_USER_ID = int(os.environ.get("DEV_AUTH_BYPASS_USER_ID", "1"))


def _dev_bypass_active() -> bool:
    if os.environ.get("DEV_AUTH_BYPASS") != "1":
        return False
    if os.environ.get("APP_ENV", "development") != "development":
        return False
    logger.warning(
        "DEV_AUTH_BYPASS active — all requests authenticated as user %s",
        _DEV_AUTH_BYPASS_USER_ID,
    )
    return True


async def _session_factory(request: Request):
    """按请求提供数据库会话（阶段 2 起不再有「无库」的 conformance 模式）。"""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


async def require_user(
    request: Request,
    rag_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(_session_factory),
) -> RequestIdentity:
    if _dev_bypass_active():
        return RequestIdentity.for_local_user(_DEV_AUTH_BYPASS_USER_ID, role=ROLE_ADMIN)
    user_id = await SessionService.authenticate(db, rag_session)
    if user_id is None:
        raise AppError("AUTH_REQUIRED", "请先登录", status_code=401)
    role = await db.scalar(select(User.role).where(User.id == user_id))
    return RequestIdentity.for_local_user(user_id, role=role or "user")


async def require_admin(
    principal: RequestIdentity = Depends(require_user),
) -> RequestIdentity:
    """管理员校验：本地账号体系下按角色判断（platform 权限字符语义已移除）。"""
    if not principal.is_admin:
        raise AppError("FORBIDDEN", "需要管理员权限", status_code=403)
    return principal


def require_permission(permission: str) -> Callable[..., RequestIdentity]:
    """权限校验依赖（阶段 6 起走**免登录**通道）。

    ⚠️ 必须依赖 ``require_user_or_visitor`` 而不是 ``require_user``。
    所有业务路由都靠 ``require_permission(...)`` 取身份；若仍走 ``require_user``，
    访客（无 ``rag_session`` Cookie）会在**每一个**端点拿到 401 —— 免登录形同虚设。

    访客权限集由 ``_VISITOR_PERMISSIONS`` 限定（view / chat），
    故 ``PERMISSION_SETTINGS_MANAGE`` 类端点对访客自然返回 **403 而非 401**
    （避免前端 401 整页跳登录）。

    注意 ``require_admin`` **不跟着改**：管理员端点保持 401 语义。
    """

    async def _dependency(
        principal: RequestIdentity = Depends(require_user_or_visitor),
    ) -> RequestIdentity:
        principal.require_permission(permission)
        return principal

    return _dependency


async def require_user_or_visitor(
    request: Request,
    response: Response,
    rag_session: str | None = Cookie(default=None),
    video_visitor: str | None = Cookie(default=None, alias=VISITOR_COOKIE),
    db: AsyncSession = Depends(_session_factory),
) -> RequestIdentity:
    """账号优先 -> 访客 -> 自动签发访客（永不 401）。

    - 账号路径：校验 ``rag_session`` Cookie；DEV_AUTH_BYPASS 时按管理员放行。
    - 访客路径：校验 ``video_visitor`` Cookie；命中则构建访客身份并续期 last_seen_at。
    - 都没有：先按 IP 复用既有访客（``VIDEO_VISITOR_BIND_IP``，默认开，**不写 Cookie**），
      确实没有才新建影子账号 + 访客行并写 ``video_visitor`` Cookie
      （HttpOnly / strict / path=/）。
    """
    # 1) 账号优先
    if _dev_bypass_active():
        return RequestIdentity.for_local_user(_DEV_AUTH_BYPASS_USER_ID, role=ROLE_ADMIN)
    user_id = await SessionService.authenticate(db, rag_session)
    if user_id is not None:
        role = await db.scalar(select(User.role).where(User.id == user_id))
        return RequestIdentity.for_local_user(user_id, role=role or "user")

    # 2) 已有访客 Cookie
    visitor = await VisitorService.authenticate(db, video_visitor)
    if visitor is not None:
        await VisitorService(db).touch(visitor.visitor_id)
        return RequestIdentity.for_visitor(
            visitor.visitor_id, shadow_user_id=visitor.owner_user_id
        )

    # 3) 同 IP 兜底复用：访客配额绑 visitor_id，而 visitor_id 每次签发都是新的 ——
    #    不做这一层，用户手动清 Cookie / 换无痕窗口就能把「剩余次数」刷回满格。
    #    复用同 IP 的最近活跃访客即可堵住该旁路。
    #    ⚠️ 这条分支**故意不下发 Cookie**：token_hash 单人单值，覆盖会让同 IP 下其他
    #    浏览器手里的 Cookie 立刻失效，双方互相顶掉、每次请求换一次 token。
    client_ip = request.client.host if request.client else None
    visitor_service = VisitorService(db)
    if visitor_bind_ip_enabled():
        existing = await visitor_service.find_active_by_ip(client_ip)
        if existing is not None:
            return RequestIdentity.for_visitor(
                existing.visitor_id, shadow_user_id=existing.owner_user_id
            )

    # 4) 真·首次访问：新建访客并下发 Cookie
    issued = await visitor_service.issue(ip=client_ip)
    response.set_cookie(
        key=VISITOR_COOKIE,
        value=issued.raw_token,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    return RequestIdentity.for_visitor(
        issued.visitor_id, shadow_user_id=issued.owner_user_id
    )
