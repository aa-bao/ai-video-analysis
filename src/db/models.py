"""P2 的 ORM 模型（阶段 5a 从 P1 `db/models.py` 裁出）。

保留：`VideoSetting` / `VideoTaskRecord`（视频域自有）+
`User` / `Session`（本地账号鉴权基础设施，`core/security.py` 与 `auth/sessions.py` 直接依赖）。

已裁掉（属 P1 业务域，本文件从 P1 同源文件裁剪而成）：
`ModelSetting` / `KnowledgeBase` / `Document` / `DocumentJob` /
`Conversation` / `ConversationKb` / `Message` / `Reference` / `QueryLog` / `Chunk`。

随之不再需要 `pgvector.sqlalchemy.HALFVEC`（本项目无向量列）—— 依赖里也就没有 `pgvector`。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


CURRENT_TIMESTAMP = text("CURRENT_TIMESTAMP")

class VideoSetting(Base):
    """视频解析 agent 设置持久化，单行（id=1）。

    - ASR 必配：asr_model + asr_api_key（独立于系统模型配置）。
    - Chat 可覆盖：chat_base_url / chat_model / chat_api_key 为空 = 复用系统
      model_relay 配置；非空时用视频 agent 独立配置。
    - api_key 明文存储（内部系统可接受），响应中绝不返回明文，只暴露 has_*。
    """

    __tablename__ = "video_setting"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asr_provider: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'volcengine'"))
    asr_model: Mapped[str] = mapped_column(String(200), nullable=False, server_default=text("'bigmodel'"))
    # 新版控制台单一 Key（X-Api-Key）
    asr_api_key: Mapped[str] = mapped_column(String(1000), nullable=False, server_default=text("''"))
    # 旧版控制台 App ID + Access Token（新版 Key 未配时使用）
    asr_app_id: Mapped[str] = mapped_column(String(200), nullable=False, server_default=text("''"))
    asr_access_token: Mapped[str] = mapped_column(String(1000), nullable=False, server_default=text("''"))
    # 空串 = 复用系统 model_relay
    chat_base_url: Mapped[str] = mapped_column(String(500), nullable=False, server_default=text("''"))
    chat_model: Mapped[str] = mapped_column(String(200), nullable=False, server_default=text("''"))
    chat_api_key: Mapped[str] = mapped_column(String(1000), nullable=False, server_default=text("''"))
    qa_model: Mapped[str] = mapped_column(String(200), nullable=False, server_default=text("''"))
    # 问答模型可独立配置；空串 = 复用摘要模型/系统配置
    qa_base_url: Mapped[str] = mapped_column(String(500), nullable=False, server_default=text("''"))
    qa_api_key: Mapped[str] = mapped_column(String(1000), nullable=False, server_default=text("''"))
    frames: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("12"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=CURRENT_TIMESTAMP,
    )

class VideoTaskRecord(Base):
    """视频解析任务与分析结果持久化（文件系统状态 JSON 的 PG 镜像）。

    文件系统仍是运行时的实时状态源；PG 用于存档、检索与跨任务统计。
    JSON 字段直接存储结构化结果（summary/report/keyframes/events/qa_history）。
    """

    __tablename__ = "rag_video_task"
    __table_args__ = (
        Index("idx_video_task_created", "created_at"),
        Index("idx_video_task_status", "status"),
        Index("idx_video_task_kind", "kind"),
        Index("idx_video_task_owner_status", "owner_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger)
    owner_visitor_id: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(2000), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    output_dir: Mapped[str | None] = mapped_column(String(1000))
    error: Mapped[str | None] = mapped_column(Text)
    frames_requested: Mapped[int | None] = mapped_column(Integer)
    transcript_source: Mapped[str | None] = mapped_column(String(200))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    transcript: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict | None] = mapped_column(JSONB)
    report: Mapped[dict | None] = mapped_column(JSONB)
    keyframes: Mapped[list | None] = mapped_column(JSONB)
    cost: Mapped[dict | None] = mapped_column(JSONB)
    events: Mapped[list | None] = mapped_column(JSONB)
    qa_history: Mapped[list | None] = mapped_column(JSONB)
    video_path: Mapped[str | None] = mapped_column(String(1000))
    audio_path: Mapped[str | None] = mapped_column(String(1000))
    content_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'video'"))
    # 图文帖子：正文/作者/标签/发布时间/图片列表
    post_text: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(200))
    hashtags: Mapped[list | None] = mapped_column(JSONB)
    publish_time: Mapped[str | None] = mapped_column(String(100))
    post_images: Mapped[list | None] = mapped_column(JSONB)
    image_captions: Mapped[dict | None] = mapped_column(JSONB)

class Visitor(Base):
    """阶段 6 访客行（影子账号方案的归属键）。token / ip 只存 sha256。"""

    __tablename__ = "rag_visitor"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_user.id", ondelete="CASCADE"), nullable=False
    )
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    upload_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    upload_chars: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    chat_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=CURRENT_TIMESTAMP
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=CURRENT_TIMESTAMP
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VisitorQuotaLog(Base):
    """阶段 6 访客配额扣减流水（幂等去重依据：visitor_id + action + ref_id）。"""

    __tablename__ = "rag_visitor_quota_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    ref_id: Mapped[str | None] = mapped_column(String(100))
    amount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=CURRENT_TIMESTAMP
    )


class User(Base):
    __tablename__ = "rag_user"
    __table_args__ = (
        CheckConstraint("role IN ('user','account_admin')", name="ck_rag_user_role"),
        CheckConstraint("status IN ('active','disabled','deleting')", name="ck_rag_user_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'user'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=CURRENT_TIMESTAMP
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=CURRENT_TIMESTAMP,
    )

class Session(Base):
    __tablename__ = "rag_session"
    __table_args__ = (
        Index("idx_session_user_expiry", "user_id", "expires_at"),
        Index("idx_session_expiry", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_user.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=CURRENT_TIMESTAMP
    )
