"""P2 配置加载（阶段 5a 从 P1 `shared/config.py` 精简而来）。

裁掉的段：`app` / `rag`（chroma_*）/ `upload` / `llm` / `lexical` / `empty_response`
—— 全部属 P1 的文档入库与检索链路，P2 闭包实测零引用。

`ModelRelaySettings` 与 `DatabaseSettings` **保持与 P1 同形**：它们被
`models/client.py`（读 base_url / api_key / embedding_* / *_retries / retry_base_delay_seconds）
与 `models/llm.py`（读 base_url / api_key / chat_model）逐字段读取，
改字段名会让视频侧代码在运行期才对不上。P2 不调用 `embed()`，但保留字段以维持壳的完整性。

`${NAME}` 占位符语义与 P1 一致：development 从环境变量取；
test / production 从 `APP_SECRET_ROOT` 下的**同名文件**取（密钥不落配置文件）。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.core.config import (
    ENV_DEVELOPMENT,
    PRODUCTION_ENVIRONMENTS,
    app_env,
)
from src.core.config import secret_root as _app_secret_root


_ENV_PLACEHOLDER = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")
# 缺失时返回空串而不是报错：P2 允许「只配 ASR、不配 Chat」地启动
_OPTIONAL_SECRET_FILES = {"MODEL_RELAY_API_KEY", "MODEL_RELAY_BASE_URL", "CHAT_MODEL"}


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ModelRelaySettings(FrozenModel):
    base_url: str = ""
    api_key: SecretStr = SecretStr("")
    chat_model: str = ""
    embedding_model: str = ""
    embedding_base_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    timeout_seconds: float = Field(default=300.0, gt=0)
    embedding_max_retries: int = Field(default=3, ge=1)
    chat_pre_stream_max_retries: int = Field(default=1, ge=0)
    retry_base_delay_seconds: float = Field(default=1.0, gt=0)

    def model_post_init(self, _context: object) -> None:
        if not self.embedding_base_url:
            object.__setattr__(self, "embedding_base_url", self.base_url)
        if self.embedding_api_key.get_secret_value() == "":
            object.__setattr__(self, "embedding_api_key", self.api_key)


class DatabaseSettings(FrozenModel):
    url: SecretStr
    pool_size: int = Field(default=5, ge=1)
    pool_recycle_seconds: int = Field(default=1800, ge=1)


class Settings(FrozenModel):
    model_relay: ModelRelaySettings = ModelRelaySettings()
    database: DatabaseSettings

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        environment: str | None = None,
        database_url: str | None = None,
        secret_root: Path | None = None,
    ) -> "Settings":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Configuration root must be a mapping: {path}")
        resolved_environment = environment or app_env()
        if resolved_environment not in (ENV_DEVELOPMENT, *PRODUCTION_ENVIRONMENTS):
            raise ValueError(f"Unsupported APP_ENV: {resolved_environment}")
        root = secret_root if secret_root is not None else _app_secret_root()
        overrides = {"DATABASE_URL": database_url} if database_url is not None else {}
        expanded = _expand_environment(
            raw,
            environment=resolved_environment,
            secret_root=root,
            overrides=overrides,
        )
        return cls.model_validate(expanded)


def _expand_environment(
    value: Any,
    *,
    environment: str = ENV_DEVELOPMENT,
    secret_root: Path | None = None,
    overrides: dict[str, str] | None = None,
) -> Any:
    overrides = overrides or {}
    if secret_root is None:
        secret_root = _app_secret_root()
    if isinstance(value, dict):
        return {
            key: _expand_environment(
                item, environment=environment, secret_root=secret_root, overrides=overrides
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _expand_environment(
                item, environment=environment, secret_root=secret_root, overrides=overrides
            )
            for item in value
        ]
    if not isinstance(value, str):
        return value

    match = _ENV_PLACEHOLDER.fullmatch(value)
    if match is None:
        return value

    name = match.group(1)
    if name in overrides:
        resolved = overrides[name]
        if not resolved:
            raise ValueError(f"Required configuration override is empty: {name}")
        return resolved

    if environment in PRODUCTION_ENVIRONMENTS:
        path = secret_root / name
        try:
            resolved = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            if name in _OPTIONAL_SECRET_FILES:
                return ""
            raise ValueError(f"Missing required secret file: {name}") from None
        except UnicodeDecodeError:
            raise ValueError(f"Required secret file is not valid UTF-8: {name}") from None
        if not resolved:
            if name in _OPTIONAL_SECRET_FILES:
                return ""
            raise ValueError(f"Required secret file is empty: {name}")
        return resolved

    resolved = os.environ.get(name)
    if resolved is None:
        if name in _OPTIONAL_SECRET_FILES:
            return ""
        raise ValueError(f"Missing required environment variable: {name}")
    return resolved
