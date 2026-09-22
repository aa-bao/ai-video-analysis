"""视频解析模块配置：路径与运行环境（流水线已内建，不再依赖 quick-watch 脚本）。"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from src.core.config import (
    ENV_DEVELOPMENT,
    PRODUCTION_ENVIRONMENTS,
    app_env,
    data_root,
)
from src.video.quota import (
    DEFAULT_ARTIFACT_QUOTA_BYTES,
    DEFAULT_DISK_CRITICAL_PERCENT,
    DEFAULT_DISK_WARN_PERCENT,
)

# 任务状态与输出根目录（相对 rag-service 数据目录）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 默认落在项目内 data/ 下，避免改造前写死的开发机绝对路径
# （原值 E:\dev\project\rag-database\rag-service\data\video_tasks）。
DEFAULT_TASK_ROOT = Path(os.environ.get(
    "QUICK_WATCH_TASK_ROOT",
    str(_PROJECT_ROOT / "data" / "video_tasks"),
)).expanduser()

# 网页版交付物根目录（每任务一个文件夹）
DEFAULT_OUTPUT_ROOT = Path(os.environ.get(
    "QUICK_WATCH_OUTPUT_ROOT",
    str(_PROJECT_ROOT / "data" / "video_output"),
)).expanduser()

# 上传的本地视频暂存目录
DEFAULT_UPLOAD_DIR = Path(os.environ.get(
    "QUICK_WATCH_UPLOAD_DIR",
    str(_PROJECT_ROOT / "data" / "video_uploads"),
)).expanduser()

# 历史视频库：quick-watch skill 默认输出根目录（C 盘用户目录下）
DEFAULT_LIBRARY_ROOT = Path(os.environ.get(
    "QUICK_WATCH_LIBRARY_ROOT",
    str(Path.home() / "quick-watch"),
)).expanduser()

# yt-dlp cookie 文件（平台需要新鲜会话 cookie 时使用；不存在则忽略）
DEFAULT_COOKIE_FILE = Path(os.environ.get(
    "QUICK_WATCH_COOKIE_FILE",
    str(Path(__file__).resolve().parent.parent.parent / "cookies.txt"),
)).expanduser()

# 抖音专用 yt-dlp cookie 文件（由设置页写入；抖音链接优先使用，不覆盖通用 cookies.txt）
DEFAULT_DOUYIN_COOKIE_FILE = Path(os.environ.get(
    "QUICK_WATCH_DOUYIN_COOKIE_FILE",
    str(Path(__file__).resolve().parent.parent.parent / "cookies_douyin.txt"),
)).expanduser()

# 元宝 cookie 文件：与 wx-channels 共享目录（Docker 挂载 rag-service/wx-cookies -> /cookies）
DEFAULT_WX_COOKIE_FILE = Path(os.environ.get(
    "WX_CHANNELS_COOKIE_FILE",
    str(Path(__file__).resolve().parent.parent.parent / "wx-cookies" / "cookies.json"),
)).expanduser()




@dataclass(frozen=True)
class VideoConfig:
    """视频解析运行配置（流水线内建，无外部脚本依赖）。"""

    task_root: Path
    output_root: Path
    upload_dir: Path
    library_root: Path
    cookie_file: Path | None
    douyin_cookie_file: Path
    wx_cookie_file: Path
    python: str
    # 磁盘硬配额与告警（方案 §7.3 磁盘专项）：env 覆盖，缺省用安全默认值
    artifact_quota_bytes: int = DEFAULT_ARTIFACT_QUOTA_BYTES
    disk_warn_percent: int = DEFAULT_DISK_WARN_PERCENT
    disk_critical_percent: int = DEFAULT_DISK_CRITICAL_PERCENT

    @classmethod
    def load(cls, *, environment: str | None = None) -> "VideoConfig":
        """从环境变量加载；缺省使用项目内的固定默认值。"""
        resolved_environment = environment or app_env()
        if resolved_environment not in (ENV_DEVELOPMENT, *PRODUCTION_ENVIRONMENTS):
            raise ValueError(f"Unsupported APP_ENV: {resolved_environment}")
        if resolved_environment in PRODUCTION_ENVIRONMENTS:
            video_root = data_root() / "video"
            task_root = video_root / "tasks"
            output_root = video_root / "output"
            upload_dir = video_root / "uploads"
            library_root = video_root / "library"
        else:
            task_root = Path(os.environ.get("QUICK_WATCH_TASK_ROOT", str(DEFAULT_TASK_ROOT)))
            output_root = Path(
                os.environ.get("QUICK_WATCH_OUTPUT_ROOT", str(DEFAULT_OUTPUT_ROOT))
            )
            upload_dir = Path(os.environ.get("QUICK_WATCH_UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR)))
            library_root = Path(
                os.environ.get("QUICK_WATCH_LIBRARY_ROOT", str(DEFAULT_LIBRARY_ROOT))
            )
        cookie_file = DEFAULT_COOKIE_FILE
        if not cookie_file.is_file():
            cookie_file = None
        if resolved_environment in PRODUCTION_ENVIRONMENTS:
            # Cookie 必须写入可持久化数据卷（镜像层只读），与
            # task/output/upload/library 一致地锁定在数据根下。
            cookie_root = data_root() / "video" / "cookies"
            douyin_cookie_file = cookie_root / "cookies_douyin.txt"
            wx_cookie_file = cookie_root / "wx-cookies" / "cookies.json"
        else:
            douyin_cookie_file = Path(os.environ.get(
                "QUICK_WATCH_DOUYIN_COOKIE_FILE",
                str(DEFAULT_DOUYIN_COOKIE_FILE),
            )).expanduser()
            wx_cookie_file = Path(os.environ.get(
                "WX_CHANNELS_COOKIE_FILE",
                str(DEFAULT_WX_COOKIE_FILE),
            )).expanduser()

        # 本机 Python：优先 venv 的 python，其次系统 python
        python = os.environ.get("QUICK_WATCH_PYTHON", "")
        if not python:
            python = shutil.which("python") or sys.executable

        artifact_quota_bytes = int(
            os.environ.get("VIDEO_ARTIFACT_QUOTA_BYTES", str(DEFAULT_ARTIFACT_QUOTA_BYTES))
        )
        disk_warn_percent = int(
            os.environ.get("VIDEO_DISK_WARN_PERCENT", str(DEFAULT_DISK_WARN_PERCENT))
        )
        disk_critical_percent = int(
            os.environ.get("VIDEO_DISK_CRITICAL_PERCENT", str(DEFAULT_DISK_CRITICAL_PERCENT))
        )
        return cls(
            task_root=task_root,
            output_root=output_root,
            upload_dir=upload_dir,
            library_root=library_root,
            cookie_file=cookie_file,
            douyin_cookie_file=douyin_cookie_file,
            wx_cookie_file=wx_cookie_file,
            python=python,
            artifact_quota_bytes=artifact_quota_bytes,
            disk_warn_percent=disk_warn_percent,
            disk_critical_percent=disk_critical_percent,
        )


@dataclass(frozen=True)
class VisitorQuotaSettings:
    """访客配额（解析条数 + 单条时长上限）。env 可覆盖，缺省 5 条 / 1200 秒。

    ``bind_ip``：**无 Cookie 的访客不再一律新建**，而是复用同 IP 的最近活跃访客
    （见 ``src/core/security.py`` 的签发分支）。

    必要性：配额计数落在 ``rag_visitor.upload_count``，归属键是 ``visitor_id``，
    而 ``visitor_id`` 每次签发都是新的 —— 只要允许「每次都发新访客」，用户手动清
    Cookie 或换一个无痕窗口就能把「剩余次数」刷回满格。默认开启。

    代价：同一公网出口（NAT / 家庭网络 / 公司）下多人**共用**一份配额。
    需要按浏览器隔离时用 ``VIDEO_VISITOR_BIND_IP=0`` 关掉（同时也就放弃了这层防刷）。
    """

    max_tasks: int = 5
    max_duration_seconds: int = 1200
    bind_ip: bool = True

    @classmethod
    def load(cls, *, environment: str | None = None) -> "VisitorQuotaSettings":
        max_tasks = int(os.environ.get("VIDEO_QUOTA_MAX_TASKS", str(cls.max_tasks)))
        max_duration_seconds = int(
            os.environ.get(
                "VIDEO_QUOTA_MAX_DURATION_SECONDS", str(cls.max_duration_seconds)
            )
        )
        # 只有显式的 "0"/"false"/"no"/"off" 才算关闭：拼写错误一律保持默认（fail-safe）
        raw_bind = os.environ.get("VIDEO_VISITOR_BIND_IP", "").strip().lower()
        bind_ip = raw_bind not in {"0", "false", "no", "off"}
        return cls(
            max_tasks=max_tasks,
            max_duration_seconds=max_duration_seconds,
            bind_ip=bind_ip,
        )
