"""视频产物磁盘硬配额与文件系统用量告警。

设计要点（方案 §7.3 磁盘专项 / §11.4）：
- 视频产物目录设**硬配额**（默认 35 GiB）：任务*受理前*（fail-closed）判定，
  超过则拒绝新任务并明确提示，而不是先写满再报错（写满会拖垮 PG 与日志）。
- 对**产物所在文件系统**统计使用率，做 80% / 90% 两级告警；用状态机保证
  同一阈值只报一次、降回阈值以下再升上来才重报（避免刷屏）。
- 用量统计对大目录做**带 TTL 的缓存**，避免每次受理都全量遍历。

配额统计覆盖「真正会被写入」的产物目录：``task_root``（状态文件）、
``output_root``（每任务输出，主体）、``upload_dir``（上传源文件）。
``library_root`` 是历史库（读取/归档用途，不随新任务增长），不计入硬配额，
但仍受文件系统告警与手动删除约束。
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.shared.errors import AppError

logger = logging.getLogger(__name__)

GIB = 1024 ** 3

# 稳定错误码：前端与测试据此区分「磁盘满 / 超配额」类未受理拒绝。
ARTIFACT_QUOTA_EXCEEDED = "ARTIFACT_QUOTA_EXCEEDED"

# 默认配额与告警阈值（由 VideoConfig 从同名环境变量覆盖）。
DEFAULT_ARTIFACT_QUOTA_BYTES = 35 * GIB
DEFAULT_DISK_WARN_PERCENT = 80
DEFAULT_DISK_CRITICAL_PERCENT = 90


def directory_size(path: Path) -> int:
    """递归求目录字节数；目录/文件不存在或不可访问时返回 0（不抛错）。"""
    total = 0
    try:
        stack = [path]
        while stack:
            current = stack.pop()
            try:
                entries = list(current.iterdir())
            except (OSError, FileNotFoundError):
                continue
            for entry in entries:
                try:
                    if entry.is_dir():
                        stack.append(entry)
                    elif entry.is_file():
                        total += entry.stat().st_size
                except OSError:
                    continue
    except (OSError, FileNotFoundError):
        return 0
    return total


class ArtifactUsage:
    """带 TTL 缓存的视频产物用量统计。

    大目录（成千上万个文件）每次全量遍历代价高；这里把「全量求和」限频到
    每 ``ttl_seconds`` 一次，其余时间返回缓存值。任务受理是低频人工事件
    （5 条/人、全局串行、单条 12–17 分钟），TTL 窗口内的少量写入不影响判定。
    """

    def __init__(self, dirs: list[Path], *, ttl_seconds: float = 60.0) -> None:
        self._dirs = [Path(d) for d in dirs]
        self._ttl = float(ttl_seconds)
        self._lock = threading.Lock()
        self._cached_bytes = 0
        self._cached_at = 0.0

    def compute(self) -> int:
        """无条件全量求和（仅在缓存过期或被 force 时调用）。"""
        return sum(directory_size(d) for d in self._dirs)

    def bytes_used(self, *, force: bool = False) -> int:
        now = time.monotonic()
        with self._lock:
            if force or (now - self._cached_at) >= self._ttl:
                self._cached_bytes = self.compute()
                self._cached_at = now
            return self._cached_bytes

    def reset_cache(self) -> None:
        with self._lock:
            self._cached_at = 0.0


class DiskAlertMonitor:
    """文件系统用量告警状态机（边沿触发：只在跨阈值时告警一次）。

    三级状态：``normal`` / ``warn`` / ``critical``。
    - 进入 ``warn`` / ``critical`` 时记一条日志；
    - 停留在同一级**不再重复**日志（避免每任务刷屏）；
    - 降到阈值以下后再次升上来，才会重新记录（即「降回再升才重报」）。

    ``evaluate`` 接收百分比，不触碰文件系统，便于纯单元测试。
    """

    LEVEL_NORMAL = "normal"
    LEVEL_WARN = "warn"
    LEVEL_CRITICAL = "critical"

    def __init__(
        self,
        path: Path,
        *,
        warn_percent: int = DEFAULT_DISK_WARN_PERCENT,
        critical_percent: int = DEFAULT_DISK_CRITICAL_PERCENT,
    ) -> None:
        self._path = self._resolve_existing(path)
        self._warn = int(warn_percent)
        self._critical = int(critical_percent)
        self._level = self.LEVEL_NORMAL
        self._lock = threading.Lock()

    @staticmethod
    def _resolve_existing(path: Path) -> Path:
        p = Path(path)
        while not p.exists() and p != p.parent:
            p = p.parent
        return p

    def usage_percent(self) -> float:
        import shutil

        try:
            usage = shutil.disk_usage(self._path)
        except OSError:
            return 0.0
        if usage.total <= 0:
            return 0.0
        return usage.used / usage.total * 100.0

    def evaluate(self, percent: float) -> str:
        percent = float(percent)
        with self._lock:
            prev = self._level
            if percent >= self._critical:
                self._level = self.LEVEL_CRITICAL
            elif percent >= self._warn:
                self._level = self.LEVEL_WARN
            else:
                self._level = self.LEVEL_NORMAL

            if self._level == prev:
                # 边沿未变：不重复告警
                return self._level

            # 状态跃迁：仅在跨阈值时记录
            if self._level == self.LEVEL_CRITICAL:
                logger.error(
                    "视频产物文件系统使用率 %.1f%% 已达严重阈值(%d%%)：请尽快清理或导出历史产物，"
                    "避免写满拖垮 PG 与日志。",
                    percent, self._critical,
                )
            elif self._level == self.LEVEL_WARN:
                logger.warning(
                    "视频产物文件系统使用率 %.1f%% 已达告警阈值(%d%%)：磁盘只增不减，注意清理。",
                    percent, self._warn,
                )
            else:  # 回到 normal
                logger.info(
                    "视频产物文件系统使用率 %.1f%% 已回落至正常区间（< %d%%）。",
                    percent, self._warn,
                )
            return self._level

    def check(self) -> str:
        return self.evaluate(self.usage_percent())

    @property
    def level(self) -> str:
        with self._lock:
            return self._level

    @property
    def warn_percent(self) -> int:
        """告警阈值（%）。公开只读，供状态端点使用，避免外部触碰私有字段。"""
        return self._warn

    @property
    def critical_percent(self) -> int:
        """严重阈值（%）。"""
        return self._critical


class VideoQuotaExceeded(AppError):
    """访客「解析条数」配额超限：固定 403，绝不用 401（防前端整页跳登录）。"""

    def __init__(self, message: str) -> None:
        super().__init__("VIDEO_QUOTA_EXCEEDED", message, status_code=403)


class VisitorTaskQuota:
    """访客「解析条数」配额闸门（阶段 6 · 方案 §11.7）。

    受理前 fail-closed 校验（check_quota），受理成功后 DB 计数扣减
    （check_and_consume_task，按 ref_id 幂等）。账号（非访客）一律放行。
    计数落库（UPDATE rag_visitor SET upload_count+1），重启不丢。
    """

    def __init__(
        self,
        db: AsyncSession,
        identity: "RequestIdentity",
        settings: "VisitorQuotaSettings | None" = None,
    ) -> None:
        self._db = db
        self._identity = identity
        self._settings = settings

    async def _ensure_settings(self) -> None:
        if self._settings is None:
            from src.video.config import VisitorQuotaSettings

            self._settings = VisitorQuotaSettings.load()

    async def _load_visitor(self) -> "Visitor":
        from src.db.models import Visitor

        v = await self._db.scalar(
            select(Visitor).where(Visitor.visitor_id == self._identity.visitor_id)
        )
        if v is None:
            raise VideoQuotaExceeded("访客身份无效，请刷新页面后重试")
        return v

    async def check_quota(self) -> None:
        """受理前 fail-closed 校验：upload_count >= max_tasks 则 403。账号放行。"""
        if not self._identity.is_visitor:
            return
        await self._ensure_settings()
        v = await self._load_visitor()
        if v.upload_count >= self._settings.max_tasks:
            raise VideoQuotaExceeded(
                f"访客最多可解析 {self._settings.max_tasks} 条视频"
            )

    async def check_and_consume_task(self, ref_id: str) -> None:
        """受理成功后扣减：upload_count += 1、写日志（action='video_task'）。

        按 ref_id 幂等：同一 ref_id 重复调用只计一次。账号放行。
        已在 check_quota 通过后调用；此处再次守卫上限（防御性）。
        """
        if not self._identity.is_visitor:
            return
        await self._ensure_settings()
        from src.db.models import Visitor, VisitorQuotaLog

        # 幂等：已存在该 ref_id 的 video_task 日志则跳过
        existing = await self._db.scalar(
            select(VisitorQuotaLog).where(
                VisitorQuotaLog.visitor_id == self._identity.visitor_id,
                VisitorQuotaLog.action == "video_task",
                VisitorQuotaLog.ref_id == ref_id,
            )
        )
        if existing is not None:
            return
        v = await self._load_visitor()
        if v.upload_count >= self._settings.max_tasks:
            raise VideoQuotaExceeded(
                f"访客最多可解析 {self._settings.max_tasks} 条视频"
            )
        await self._db.execute(
            update(Visitor)
            .where(Visitor.visitor_id == self._identity.visitor_id)
            .values(upload_count=Visitor.upload_count + 1)
        )
        self._db.add(
            VisitorQuotaLog(
                visitor_id=self._identity.visitor_id,
                action="video_task",
                ref_id=ref_id,
                amount=1,
            )
        )
        await self._db.commit()

    async def snapshot(self) -> dict[str, int]:
        """配额快照（供 /api/auth/me）。键名固定：tasks_used/tasks_max/max_duration_seconds。"""
        await self._ensure_settings()
        if self._identity.is_visitor:
            v = await self._load_visitor()
            tasks_used = v.upload_count
        else:
            tasks_used = 0
        return {
            "tasks_used": tasks_used,
            "tasks_max": self._settings.max_tasks,
            "max_duration_seconds": self._settings.max_duration_seconds,
        }
