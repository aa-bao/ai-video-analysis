"""免登录访客（阶段 6 · 方案 §11）。

影子账号方案：每个访客在 ``rag_user`` 持有一行影子账号
（``username = 'v:' || visitor_id``，``status='disabled'``，使其不可登录），
其 id 即该访客的 ``owner_user_id``。视频任务的 ``owner_user_id`` 过滤与全部复合外键
零改动即天然隔离（账号与访客都落到 ``rag_user``，仅 ``status`` 不同）。

``rag_visitor`` 表只存 token 的 sha256（与 ``rag_session`` 同一手法），明文 token 仅
在签发时回传给客户端（写 ``video_visitor`` Cookie）。IP 也只存 hash，不存明文。
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User, Visitor

VISITOR_COOKIE = "video_visitor"


class IssuedVisitor:
    """一次访客签发的结果（raw_token 仅此处可见一次）。"""

    __slots__ = ("raw_token", "visitor_id", "owner_user_id", "token_hash")

    def __init__(
        self,
        *,
        raw_token: str,
        visitor_id: str,
        owner_user_id: int,
        token_hash: str,
    ) -> None:
        self.raw_token = raw_token
        self.visitor_id = visitor_id
        self.owner_user_id = owner_user_id
        self.token_hash = token_hash

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """token 的 sha256（与 src/auth/sessions.py 同一手法，只存 hash）。"""
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _hash_ip(ip: str | None) -> str | None:
    """IP 只存 hash，不存明文。"""
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


class VisitorService:
    """访客影子账号 + 访客行的签发与校验。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def issue(self, *, ip: str | None = None) -> IssuedVisitor:
        """签发一个全新访客：影子账号 + rag_visitor 行，同一事务提交。"""
        # 避免模块加载期循环依赖：惰性引用 router_auth 的 _DUMMY_HASH。
        from src.api.router_auth import _DUMMY_HASH

        visitor_id = uuid.uuid4().hex
        raw_token = secrets.token_urlsafe(32)
        token_hash = IssuedVisitor.hash_token(raw_token)
        ip_hash = _hash_ip(ip)

        # 1) 影子账号：不可登录（status='disabled'），username 唯一可追溯。
        shadow = User(
            username=f"v:{visitor_id}",
            password_hash=_DUMMY_HASH,
            role="user",
            status="disabled",
        )
        self._db.add(shadow)
        await self._db.flush()

        # 2) 访客行（仅存 token hash 与 ip hash）。
        visitor = Visitor(
            visitor_id=visitor_id,
            token_hash=token_hash,
            owner_user_id=shadow.id,
            ip_hash=ip_hash,
        )
        self._db.add(visitor)
        await self._db.commit()
        await self._db.refresh(visitor)

        return IssuedVisitor(
            raw_token=raw_token,
            visitor_id=visitor_id,
            owner_user_id=shadow.id,
            token_hash=token_hash,
        )

    @staticmethod
    async def authenticate(db: AsyncSession, raw_token: str | None) -> Visitor | None:
        """按明文 token 校验访客；无效/过期/禁用返回 None。"""
        if raw_token is None:
            return None
        token_hash = IssuedVisitor.hash_token(raw_token)
        return await db.scalar(
            select(Visitor).where(
                Visitor.token_hash == token_hash,
                Visitor.status == "active",
            )
        )

    async def touch(self, visitor_id: str) -> None:
        """续期 last_seen_at（每次请求命中访客 Cookie 时调用）。"""
        await self._db.execute(
            update(Visitor)
            .where(Visitor.visitor_id == visitor_id)
            .values(last_seen_at=datetime.now(UTC))
        )
        await self._db.commit()

    async def find_active_by_ip(self, ip: str | None) -> Visitor | None:
        """按 IP hash 找该来源**最近活跃**的访客（同 IP 兜底复用的依据）。

        用途：访客 Cookie 缺失时不再无条件新建访客，而是先看这个出口是否已经来过 ——
        命中则复用它的 ``visitor_id``，``upload_count`` 随之一并延续，清 Cookie
        无法把「剩余次数」刷回去。

        ⚠️ **只查不改**：不签发 token、不写 Cookie。``rag_visitor.token_hash`` 是
        单人单值，覆盖它会让同 IP 下其他浏览器手里的 Cookie **立即失效**，双方互相
        顶掉、每次请求都要换一次 token。故复用时只借用身份，不下发新凭据。
        """
        ip_hash = _hash_ip(ip)
        if not ip_hash:
            return None
        return await self._db.scalar(
            select(Visitor)
            .where(Visitor.ip_hash == ip_hash, Visitor.status == "active")
            .order_by(Visitor.last_seen_at.desc())
            .limit(1)
        )


def visitor_bind_ip_enabled() -> bool:
    """访客签发是否复用同 IP 的既有访客（``VIDEO_VISITOR_BIND_IP``，默认开）。

    惰性 import ``src.video.config``：模块加载期 video ⇄ auth 互引会成环，
    与 ``src/video/quota.py::_ensure_settings`` 同一手法。
    """
    from src.video.config import VisitorQuotaSettings

    return VisitorQuotaSettings.load().bind_ip
