from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import _session_factory, require_user, require_user_or_visitor
from src.auth.passwords import PasswordHasher
from src.auth.rate_limiter import (
    clear_login_attempts,
    is_login_rate_limited,
    login_rate_limit_key,
    record_login_failure,
)
from src.auth.sessions import IssuedSession, SessionService
from src.core.config import ENV_DEVELOPMENT, app_env
from src.db.models import Session as DbSession
from src.db.models import User
from src.core.identity import (
    ALL_PERMISSIONS,
    PERMISSION_CHAT_USE,
    PERMISSION_PROJECT_VIEW,
    _VISITOR_PERMISSIONS,
    RequestIdentity,
)
from src.shared.errors import AppError
from src.auth.visitor import (
    VISITOR_COOKIE,
    VisitorService,
    visitor_bind_ip_enabled,
)
from src.video.quota import VisitorTaskQuota

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 本地普通用户权限（与 RequestIdentity.for_local_user 推导一致）
LOCAL_USER_PERMISSIONS = frozenset({PERMISSION_PROJECT_VIEW, PERMISSION_CHAT_USE})

# 稳定错误码：访客侧调用退出登录（= 清空访客会话）时返回，前端据此提示而不是跳登录页。
VISITOR_SESSION_CLEAR_FORBIDDEN = "VISITOR_SESSION_CLEAR_FORBIDDEN"

_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$YS0oGGj2ABX3BWFAphSfQA$"
    "Xxk+Rx7UOZBpOmg8KApL3uQmcKw42vT9oFkHePqAVpQ"
)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(_session_factory),
) -> dict[str, object]:
    # 仅 development 开放本地口令登录（原平台 LOCAL 语义，见 core/config.py）
    if app_env() != ENV_DEVELOPMENT:
        raise AppError(
            "AUTH_LOCAL_LOGIN_DISABLED",
            "Local password login is disabled in this environment",
            status_code=403,
        )

    username = body.username.strip()
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_key = login_rate_limit_key(username, client_ip)

    if is_login_rate_limited(rate_key):
        hasher = PasswordHasher()
        hasher.verify(_DUMMY_HASH, body.password)
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", status_code=429)

    result = await db.execute(
        select(User.id, User.password_hash, User.role, User.status).where(
            User.username == username
        )
    )
    row = result.one_or_none()

    if row is None:
        hasher = PasswordHasher()
        hasher.verify(_DUMMY_HASH, body.password)
        record_login_failure(rate_key)
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", status_code=401)

    user_id, password_hash, user_role, user_status = row

    if user_status != "active":
        hasher = PasswordHasher()
        hasher.verify(_DUMMY_HASH, body.password)
        record_login_failure(rate_key)
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", status_code=401)

    hasher = PasswordHasher()
    if not hasher.verify(password_hash, body.password):
        record_login_failure(rate_key)
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", status_code=401)

    clear_login_attempts(rate_key)
    issued = await SessionService(db).issue(user_id)
    response.set_cookie(
        key="rag_session",
        value=issued.raw_token,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    return {"success": True, "data": {"id": user_id, "username": username, "role": user_role}}


@router.post("/logout")
async def logout(
    response: Response,
    db: AsyncSession = Depends(_session_factory),
    rag_session: str | None = Cookie(default=None),
    video_visitor: str | None = Cookie(default=None, alias=VISITOR_COOKIE),
) -> dict[str, object]:
    """退出登录。

    ⚠️ **访客会话不可清空**（403 ``VISITOR_SESSION_CLEAR_FORBIDDEN``）：
    访客配额计数落在访客行上，而访客行由 ``video_visitor`` Cookie 指向 ——
    清掉它，下一次请求就会签发**全新访客**（``upload_count`` 从 0 开始），
    等于把「剩余次数」刷回满格。故访客侧直接拒绝，且**不下发任何删除 Cookie 头**
    （删了与清空等效）。访客若要换用管理员身份，请走登录页 —— 登录后账号身份优先，
    访客 Cookie 原样保留，配额也不会被重置。

    账号退出不受影响；此处**只删 ``rag_session``**，不动访客 Cookie
    （顺带删访客 Cookie 同样等于重置配额）。
    """
    if rag_session is not None:
        await SessionService(db).revoke(rag_session)
        response.delete_cookie(key="rag_session", path="/")
        return {"success": True, "data": None}

    if await VisitorService.authenticate(db, video_visitor) is not None:
        raise AppError(
            VISITOR_SESSION_CLEAR_FORBIDDEN,
            "访客会话不可清空（免登录额度按访客累计）；如需管理员身份请在登录页登录。",
            status_code=403,
        )

    # 无任何有效会话：幂等成功，且不写任何删除 Cookie 头
    return {"success": True, "data": None}


@router.post("/visitor")
async def init_visitor(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(_session_factory),
) -> dict[str, object]:
    """显式初始化访客：签发影子账号 + 访客行，写 video_visitor Cookie。

    ⚠️ 这个端点原来是个**免鉴权的「无限刷身份」入口**：脚本循环 POST 即可拿到
    一个又一个 ``upload_count=0`` 的新访客，把配额闸门整个绕过去。现在与自动签发
    同规则 —— 开了 ``VIDEO_VISITOR_BIND_IP``（默认）时，同 IP 已有活跃访客就
    **复用**它并返回 ``reused: true``，既不发新身份也不下发 Cookie。
    """
    client_ip = request.client.host if request.client else None
    visitor_service = VisitorService(db)
    if visitor_bind_ip_enabled():
        existing = await visitor_service.find_active_by_ip(client_ip)
        if existing is not None:
            return {
                "success": True,
                "data": {
                    "visitor_id": existing.visitor_id,
                    "is_guest": True,
                    "reused": True,
                },
            }

    issued = await visitor_service.issue(ip=client_ip)
    response.set_cookie(
        key=VISITOR_COOKIE,
        value=issued.raw_token,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    return {
        "success": True,
        "data": {"visitor_id": issued.visitor_id, "is_guest": True, "reused": False},
    }


@router.get("/me")
async def me(
    db: AsyncSession = Depends(_session_factory),
    principal: RequestIdentity = Depends(require_user_or_visitor),
) -> dict[str, object]:
    """当前用户信息（账号优先，否则访客，无 Cookie 时自动签发访客，永不 401）。

    - 访客也有影子账号行（``username='v:' || visitor_id``），故 User.username 可查到；
      role / permissions 按 ``kind`` 分支返回，并补充 ``is_guest`` 标记与配额快照。
    """
    username = await db.scalar(select(User.username).where(User.id == principal.user_id))
    if username is None:
        raise AppError("AUTH_REQUIRED", "请登录", status_code=401)
    if principal.is_visitor:
        permissions = sorted(_VISITOR_PERMISSIONS)
    elif principal.is_admin:
        permissions = sorted(ALL_PERMISSIONS)
    else:
        permissions = sorted(LOCAL_USER_PERMISSIONS)

    # 阶段 6：访客附带配额快照（键名 = 前端契约）；账号返回 None（前端据此隐藏配额 UI）。
    quota = await VisitorTaskQuota(db, principal).snapshot() if principal.is_visitor else None

    return {
        "success": True,
        "data": {
            "id": principal.user_id,
            "username": username,
            "role": principal.role,
            "permissions": permissions,
            "platform": False,
            "is_guest": principal.is_visitor,
            "quota": quota,
        },
    }
