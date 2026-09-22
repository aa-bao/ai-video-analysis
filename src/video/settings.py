"""视频解析 agent 设置模型 + 运行时热更新 + DB 持久化。

配置语义（参照 shared.runtime.RuntimeModelRelay 模式）：
- ASR 双渠道：ASR_PROVIDER 决定渠道（dashscope 百炼 / volcengine 火山）。
  百炼凭证用 DASHSCOPE_ASR_*（模型默认 qwen-audio-3.0-asr-flash-filetrans，公网 URL 拉音频），
  火山凭证用 VOLC_ASR_*（单一 Key 或 App ID + Access Token），两套互不干扰。
- Chat 可覆盖：chat_base_url / chat_model / chat_api_key 为空 = 复用系统
  model_relay；非空时用视频 agent 独立配置（默认预填豆包方舟）。
- 问答模型可独立配置 qa_base_url / qa_model / qa_api_key；空字段回退到摘要配置。
- 响应绝不回显密钥明文，只暴露 has_asr_api_key / has_asr_access_token /
  has_chat_api_key。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import VideoSetting
from src.db.repositories import VideoSettingRepository
from src.core.config import secret_root

# 默认值常量
ASR_PROVIDER_DEFAULT = "volcengine"
ASR_MODEL_DEFAULT = os.environ.get("VOLC_ASR_MODEL", "bigmodel")
ASR_RESOURCE_ID_DEFAULT = os.environ.get("VOLC_ASR_RESOURCE_ID", "volc.bigasr.auc_turbo")
# provider 别名 → 都走百炼渠道
DASHSCOPE_ASR_PROVIDERS = {"dashscope", "qwen", "aliyun", "bailian", "aliyun-bailian"}
# 百炼渠道（dashscope）：提交端点与应用 HTTPS 媒体入口
# ⚠️ 端点是 /transcription（单数）。曾经误写成 /transcriptions（复数），会 404。
DASHSCOPE_ASR_ENDPOINT_DEFAULT = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
DASHSCOPE_ASR_MODEL_DEFAULT = "qwen-audio-3.1-asr-flash-filetrans"
# 百炼音频送入方式：oss（getPolicy 直传 OSS，本地可用）/ public-url（暴露公网入口）
ASR_UPLOAD_MODE_DEFAULT = "oss"
FRAMES_DEFAULT = 12
CHAT_BASE_URL_DEFAULT = os.environ.get("VOLC_CHAT_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
CHAT_MODEL_DEFAULT = os.environ.get("VOLC_CHAT_MODEL", "doubao-seed-2-1-pro-260628")
QA_MODEL_DEFAULT = os.environ.get("VOLC_CHAT_QA_MODEL", "doubao-seed-2-1-turbo-260628")


def _read_env_file(path: Path) -> dict[str, str]:
    """读取 key=value 形式的 .env 文件（# 注释、引号剥离）。"""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _runtime_secret(*names: str, fallback: str = "") -> str:
    """Controller secret files win over environment and legacy local files."""
    root = secret_root()
    for name in names:
        path = root / name
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return fallback.strip()


@dataclass
class VideoAgentSettings:
    """视频 agent 运行时可变配置（仿 RuntimeModelRelay）。

    密钥存明文（内部系统可接受），任何 API 响应（to_dict）都不会回显。
    """

    asr_provider: str = ASR_PROVIDER_DEFAULT
    asr_model: str = ASR_MODEL_DEFAULT
    asr_api_key: str = ""
    asr_app_id: str = ""
    asr_access_token: str = ""
    # 百炼渠道：提交端点（空=默认）与应用 HTTPS 媒体入口
    asr_endpoint: str = ""
    asr_public_base_url: str = ""
    # 百炼音频送入方式：oss（getPolicy 直传 OSS，本地可用）/ public-url（需公网入口）
    asr_upload_mode: str = ASR_UPLOAD_MODE_DEFAULT
    chat_base_url: str = ""
    chat_model: str = ""
    chat_api_key: str = ""
    qa_model: str = ""
    qa_base_url: str = ""
    qa_api_key: str = ""
    frames: int = FRAMES_DEFAULT

    # ── 工厂 ──

    @classmethod
    def from_env(cls) -> "VideoAgentSettings":
        """从项目 .env / 环境变量加载默认配置（用户填写后的初始值）。

        ASR 为双渠道：ASR_PROVIDER 决定当前渠道（dashscope / volcengine），
        .env 中两套凭证（DASHSCOPE_ASR_* / VOLC_ASR_*）互不干扰，随时可切换。
        """
        env = os.environ
        watch_env = _read_env_file(Path.home() / ".config" / "watch" / ".env")
        provider = (
            env.get("ASR_PROVIDER", "")
            or env.get("VOLC_ASR_PROVIDER", "")
            or ASR_PROVIDER_DEFAULT
        ).strip().lower()
        is_dashscope = provider in DASHSCOPE_ASR_PROVIDERS
        return cls(
            asr_provider=provider,
            asr_model=(
                env.get("DASHSCOPE_ASR_MODEL", DASHSCOPE_ASR_MODEL_DEFAULT).strip()
                if is_dashscope
                else env.get("VOLC_ASR_MODEL", ASR_MODEL_DEFAULT).strip()
            ),
            asr_api_key=(
                (
                    _runtime_secret(
                        "DASHSCOPE_ASR_API_KEY",
                        fallback=watch_env.get("DASHSCOPE_ASR_API_KEY", ""),
                    )
                )
                if is_dashscope
                else (
                    _runtime_secret(
                        "VOLC_ASR_API_KEY",
                        fallback=watch_env.get("VOLC_ASR_API_KEY", ""),
                    )
                )
            ).strip(),
            asr_app_id=_runtime_secret(
                "VOLC_ASR_APP_ID", fallback=watch_env.get("VOLC_ASR_APP_ID", "")
            ),
            asr_access_token=(
                _runtime_secret(
                    "VOLC_ASR_ACCESS_TOKEN",
                    fallback=watch_env.get("VOLC_ASR_ACCESS_TOKEN", ""),
                )
            ),
            asr_endpoint=env.get("DASHSCOPE_ASR_ENDPOINT", "").strip(),
            asr_public_base_url=_runtime_secret(
                "DASHSCOPE_ASR_PUBLIC_BASE_URL"
            ),
            asr_upload_mode=(
                env.get("ASR_UPLOAD_MODE", "").strip().lower()
                or ASR_UPLOAD_MODE_DEFAULT
            ),
            chat_base_url=(
                env.get("VIDEO_CHAT_BASE_URL", "").strip()
                or env.get("VOLC_CHAT_BASE_URL", CHAT_BASE_URL_DEFAULT).strip()
            ),
            chat_model=(
                env.get("VIDEO_CHAT_MODEL", "").strip()
                or env.get("VOLC_CHAT_MODEL", CHAT_MODEL_DEFAULT).strip()
            ),
            chat_api_key=(
                _runtime_secret("VIDEO_CHAT_API_KEY", "VOLC_CHAT_API_KEY")
            ),
            qa_model=(
                env.get("VIDEO_CHAT_QA_MODEL", "").strip()
                or env.get("VOLC_CHAT_QA_MODEL", QA_MODEL_DEFAULT).strip()
            ),
            qa_base_url=(
                env.get("VIDEO_CHAT_QA_BASE_URL", "").strip()
                or env.get("VOLC_CHAT_QA_BASE_URL", "").strip()
            ),
            qa_api_key=(
                _runtime_secret("VIDEO_CHAT_QA_API_KEY", "VOLC_CHAT_QA_API_KEY")
            ),
            frames=int(
                env.get("VIDEO_FRAMES", "")
                or env.get("VOLC_VIDEO_FRAMES", str(FRAMES_DEFAULT))
                or FRAMES_DEFAULT
            ),
        )

    @classmethod
    def from_row(cls, row: VideoSetting) -> "VideoAgentSettings":
        """从 DB 行恢复（服务重启后保留已保存配置）。"""
        return cls(
            asr_provider=row.asr_provider,
            asr_model=row.asr_model,
            asr_api_key=row.asr_api_key or "",
            asr_app_id=row.asr_app_id or "",
            asr_access_token=row.asr_access_token or "",
            asr_endpoint=os.environ.get("DASHSCOPE_ASR_ENDPOINT", "").strip(),
            asr_public_base_url=_runtime_secret("DASHSCOPE_ASR_PUBLIC_BASE_URL"),
            asr_upload_mode=(
                os.environ.get("ASR_UPLOAD_MODE", "").strip().lower()
                or ASR_UPLOAD_MODE_DEFAULT
            ),
            chat_base_url=row.chat_base_url or "",
            chat_model=row.chat_model or "",
            chat_api_key=row.chat_api_key or "",
            qa_model=row.qa_model or "",
            qa_base_url=row.qa_base_url or "",
            qa_api_key=row.qa_api_key or "",
            frames=row.frames,
        )

    # ── 响应 / 持久化 ──

    def to_dict(self) -> dict[str, object]:
        """响应结构：绝不包含密钥明文，只暴露是否已配置。"""
        return {
            "asr_provider": self.asr_provider,
            "asr_model": self.asr_model,
            "asr_resource_id": ASR_RESOURCE_ID_DEFAULT,
            "asr_endpoint": self.asr_endpoint or DASHSCOPE_ASR_ENDPOINT_DEFAULT,
            "asr_upload_mode": self.asr_upload_mode,
            "has_asr_public_base_url": bool(self.asr_public_base_url),
            "has_asr_api_key": bool(self.asr_api_key),
            "has_asr_app_id": bool(self.asr_app_id),
            "has_asr_access_token": bool(self.asr_access_token),
            # 空串 = 复用系统 model_relay
            "chat_base_url": self.chat_base_url,
            "chat_model": self.chat_model,
            "has_chat_api_key": bool(self.chat_api_key),
            "qa_model": self.qa_model,
            "qa_base_url": self.qa_base_url,
            "has_qa_api_key": bool(self.qa_api_key),
            "frames": self.frames,
        }

    def to_storage(self) -> dict[str, str | int]:
        """DB 持久化字段（含密钥明文，仅内部使用）。"""
        return {
            "asr_provider": self.asr_provider,
            "asr_model": self.asr_model,
            "asr_api_key": self.asr_api_key,
            "asr_app_id": self.asr_app_id,
            "asr_access_token": self.asr_access_token,
            "chat_base_url": self.chat_base_url,
            "chat_model": self.chat_model,
            "chat_api_key": self.chat_api_key,
            "qa_model": self.qa_model,
            "qa_base_url": self.qa_base_url,
            "qa_api_key": self.qa_api_key,
            "frames": self.frames,
        }

    def copy(self) -> "VideoAgentSettings":
        return replace(self)

    # ── 查询辅助 ──

    @property
    def asr_configured(self) -> bool:
        """ASR 凭证是否已配置（新版 Key 或旧版 AppID+Token 任一）。"""
        return bool(self.asr_api_key) or bool(self.asr_app_id and self.asr_access_token)

    @property
    def asr_headers(self) -> dict[str, str] | None:
        """火山语音技术请求头；凭证未配置时返回 None。"""
        import uuid

        headers = {
            "X-Api-Resource-Id": ASR_RESOURCE_ID_DEFAULT,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
        }
        if self.asr_api_key:
            headers["X-Api-Key"] = self.asr_api_key
        elif self.asr_app_id and self.asr_access_token:
            headers["X-Api-App-Key"] = self.asr_app_id
            headers["X-Api-Access-Key"] = self.asr_access_token
        else:
            return None
        return headers

    @property
    def chat_configured(self) -> bool:
        """Chat 是否配置了独立通道（base_url + model + key 三者齐备）。"""
        return bool(self.chat_base_url.strip() and self.chat_model.strip() and self.chat_api_key.strip())

    @property
    def qa_configured(self) -> bool:
        """问答模型是否可走独立通道；缺省字段回退到摘要模型配置。"""
        base_url = self.qa_base_url.strip() or self.chat_base_url.strip()
        model = self.qa_model.strip() or self.chat_model.strip()
        api_key = self.qa_api_key.strip() or self.chat_api_key.strip()
        return bool(base_url and model and api_key)


class VideoAgentSettingsService:
    """设置的服务层：启动时从 DB 恢复、运行时保存到 DB。"""

    def __init__(self, settings: VideoAgentSettings, session_factory) -> None:
        self._settings = settings
        self._session_factory = session_factory

    @property
    def current(self) -> VideoAgentSettings:
        return self._settings

    async def restore(self) -> None:
        """启动时从 DB 恢复已保存配置；无记录则保留 .env 默认值。

        原地修改当前对象字段，保证 app.state.video_settings 引用持续有效。
        """
        try:
            async with self._session_factory() as session:
                row = await VideoSettingRepository(session).get()
            if row is not None:
                restored = VideoAgentSettings.from_row(row)
                # 已保存过配置：chat/qa 空串 = 复用系统 model_relay，保留空值不回落。
                # 只有 ASR 凭证为空时用 .env 默认，保证开箱即用。
                defaults = VideoAgentSettings.from_env()
                if defaults.asr_api_key or defaults.asr_app_id or defaults.asr_access_token:
                    restored.asr_api_key = defaults.asr_api_key
                    restored.asr_app_id = defaults.asr_app_id
                    restored.asr_access_token = defaults.asr_access_token
                if defaults.chat_api_key:
                    restored.chat_api_key = defaults.chat_api_key
                if defaults.qa_api_key:
                    restored.qa_api_key = defaults.qa_api_key
                self._settings.asr_provider = restored.asr_provider
                self._settings.asr_model = restored.asr_model
                self._settings.asr_api_key = restored.asr_api_key
                self._settings.asr_app_id = restored.asr_app_id
                self._settings.asr_access_token = restored.asr_access_token
                self._settings.chat_base_url = restored.chat_base_url
                self._settings.chat_model = restored.chat_model
                self._settings.chat_api_key = restored.chat_api_key
                self._settings.qa_model = restored.qa_model
                self._settings.qa_base_url = restored.qa_base_url
                self._settings.qa_api_key = restored.qa_api_key
                self._settings.frames = restored.frames
        except Exception as exc:  # noqa: BLE001
            # DB 不可用（如离线启动）不阻断，保留 .env 默认值；记日志便于诊断
            import logging

            logging.getLogger(__name__).warning("video settings restore failed: %s", exc)

    async def save(self, session: AsyncSession) -> None:
        await VideoSettingRepository(session).upsert(self._settings.to_storage())
