"""数据可见性（本服务自持，已剥离平台租户 / dataScope 语义）。

改造前这里做两件事：按 ``tenant_id`` 过滤、按平台 dataScope（部门 ID / 平台用户 ID）过滤。
独立化之后两者的前提都不成立：

- 没有租户概念（单实例单部署，不再对接平台的多租户控制面）
- 没有平台部门与平台用户 ID；数据归属就是本地 ``rag_user`` 主键

因此 ``scope_condition`` 退化为恒真。**保留这个函数（而不是删掉约 31 处调用点）
是有意的**：

1. 各 router / repository 早已显式带上 ``owner_user_id == identity.user_id`` 条件，
   可见性并未因本函数退化而放松 —— 它从来只是"额外收紧"，不是唯一防线。
2. 阶段 6 的访客沙箱隔离需要一个**统一的收紧位置**：
   访客可见范围 = 公共库 ∪ 自己的沙箱库。那段逻辑落在这里，
   就不必再把 31 处调用点重改一遍。
"""
from __future__ import annotations

from typing import TypeAlias

from sqlalchemy import ColumnElement, true

from src.core.identity import RequestIdentity

ScopeCondition: TypeAlias = ColumnElement[bool]


def scope_condition(table: object, identity: RequestIdentity) -> ScopeCondition:
    """数据可见性条件（当前恒真，见模块 docstring）。

    ``table`` 与 ``identity`` 参数暂时保留是为了让阶段 6 能在此处按
    ``identity.kind``（account / visitor）收紧可见范围，而不必再动调用点。
    """
    del table, identity  # 当前无附加过滤；阶段 6 起按 kind 收紧
    return true()
