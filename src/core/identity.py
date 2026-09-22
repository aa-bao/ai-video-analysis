"""请求级身份视图（本服务自持，不再依赖 TYT RPA 平台）。

阶段 1（独立化改造）把原 `src/platform/principal.py:ProjectPrincipal` 迁到这里，
并做了两件事：

1. **剥离平台专有字段** —— ``tenant_id`` / ``external_user_id`` / ``department_id`` /
   ``display_name`` / ``data_scope_*`` 全部移除。LOCAL 模式下它们恒为空，
   是死字段；保留只会让后续代码继续被平台语义污染。
2. **定下访客形态** —— 新增 ``kind ∈ {account, visitor}`` 与 ``visitor_id``。

第 2 条必须在阶段 1 完成而不能拖到阶段 6：方案 §12.3 第 1 条与风险 R13 都指出，
访客 ID 要能**落库**到文档表与视频任务表（否则 D13「数据不清理」之后，
无法区分是谁何时上传的，也无法按人处置）。若阶段 1 不预留该字段，
阶段 6 就得把这约 92 处权限注入点再改一遍。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.shared.errors import AppError

# 权限字符（与 rpa-application.yaml 声明一致）。
# 保留原字符是为了让 router 层的 require_permission(...) 调用点无需改动；
# 前缀 rag-database 是本项目自身的应用标识，与平台无关。
PERMISSION_PROJECT_VIEW = "rag-database:project:view"
PERMISSION_KB_MANAGE = "rag-database:knowledge-base:manage"
PERMISSION_CHAT_USE = "rag-database:chat:use"
PERMISSION_SETTINGS_MANAGE = "rag-database:settings:manage"
ALL_PERMISSIONS = frozenset(
    {
        PERMISSION_PROJECT_VIEW,
        PERMISSION_KB_MANAGE,
        PERMISSION_CHAT_USE,
        PERMISSION_SETTINGS_MANAGE,
    }
)

# 角色：本地账号双轨（管理员 / 普通用户）+ 访客
ROLE_ADMIN = "account_admin"
ROLE_USER = "user"
ROLE_VISITOR = "visitor"

# 访客可用的能力：能看、能问，但不能改设置
_VISITOR_PERMISSIONS = frozenset({PERMISSION_PROJECT_VIEW, PERMISSION_CHAT_USE})

IdentityKind = Literal["account", "visitor"]


@dataclass(frozen=True)
class RequestIdentity:
    """请求级身份。

    - ``user_id``：本地 ``rag_user`` 主键；访客为影子账号 id（阶段 6 影子账号方案）。
    - ``visitor_id``：访客标识，``kind == "visitor"`` 时有效且**可落库**
      （文档表 / 视频任务表的归属标记）。
    """

    user_id: int
    username: str = ""
    role: str = ROLE_USER
    kind: IdentityKind = "account"
    visitor_id: str = ""
    permissions: frozenset[str] = field(default_factory=frozenset)

    # ---- 能力 ----

    def require_permission(self, permission: str) -> None:
        if permission not in self.permissions:
            raise AppError("FORBIDDEN", "没有执行此操作的权限", status_code=403)

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_visitor(self) -> bool:
        return self.kind == "visitor"

    @property
    def owner_key(self) -> str:
        """数据归属键：账号用 ``u:<id>``、访客用 ``v:<visitor_id>``。

        阶段 6 的沙箱隔离与按人清理都依赖这个键，故与身份一并定下。
        """
        if self.kind == "visitor":
            return f"v:{self.visitor_id}"
        return f"u:{self.user_id}"

    # ---- 构造 ----

    @classmethod
    def for_local_user(
        cls, user_id: int, *, role: str = ROLE_USER, username: str = ""
    ) -> "RequestIdentity":
        """本地账号：account_admin 拥有全部能力；普通用户仅可查看与对话。"""
        if role == ROLE_ADMIN:
            permissions = ALL_PERMISSIONS
        else:
            permissions = frozenset({PERMISSION_PROJECT_VIEW, PERMISSION_CHAT_USE})
        return cls(
            user_id=user_id,
            username=username,
            role=role,
            kind="account",
            permissions=permissions,
        )

    @classmethod
    def for_visitor(
        cls, visitor_id: str, *, shadow_user_id: int
    ) -> "RequestIdentity":
        """免登录访客：能力受限，且归属靠 visitor_id 追溯。

        阶段 6 影子账号方案：访客在 ``rag_user`` 持有一行影子账号
        （``username='v:' || visitor_id``，``status='disabled'``），其 id 即本访客的
        ``owner_user_id``。``user_id`` 用影子 id 而非 0（不再以 ``user_id == 0`` 判定访客，
        改由 ``kind`` 判定）。
        """
        return cls(
            user_id=shadow_user_id,
            username="访客",
            role=ROLE_VISITOR,
            kind="visitor",
            visitor_id=visitor_id,
            permissions=_VISITOR_PERMISSIONS,
        )
