"""运行环境与数据根目录（本服务自持，替代原平台部署路径假设）。

改造前存在三处硬编码的平台路径，独立部署后必然失效：

| 位置 | 原值 |
|---|---|
| ``src/platform/config.py`` | ``SECRET_ROOT = /run/tyt-rpa/secrets`` |
| ``src/shared/config.py`` | ``PLATFORM_DATA_ROOT = /opt/tyt-rpa/app/data`` |
| ``src/video/config.py`` | ``PLATFORM_VIDEO_ROOT = /opt/tyt-rpa/app/data/video`` |

这里统一成一组可由环境变量覆盖的项目内路径：

- ``APP_ENV``：``development`` / ``test`` / ``production``
- ``APP_DATA_ROOT``：数据根，默认 ``./data``
- ``APP_SECRET_ROOT``：密钥目录，默认 ``./secrets``

``APP_ENV`` 取代原 ``RPA_ENVIRONMENT``（LOCAL / TEST / PRODUCTION）——
LOCAL 对应 development，语义不变但不再带平台前缀。
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_DEVELOPMENT = "development"
ENV_TEST = "test"
ENV_PRODUCTION = "production"

_ENVIRONMENTS = (ENV_DEVELOPMENT, ENV_TEST, ENV_PRODUCTION)

# 生产类环境：密钥从文件读取、存储路径锁定在数据根下
PRODUCTION_ENVIRONMENTS = (ENV_TEST, ENV_PRODUCTION)


def app_env() -> str:
    """当前运行环境。未设置时默认 development（等价于改造前的 LOCAL）。"""
    value = os.environ.get("APP_ENV", ENV_DEVELOPMENT).strip().lower()
    if value not in _ENVIRONMENTS:
        raise RuntimeError(
            f"Unsupported APP_ENV: {value} (expected one of {', '.join(_ENVIRONMENTS)})"
        )
    return value


def is_production_like() -> bool:
    return app_env() in PRODUCTION_ENVIRONMENTS


def data_root() -> Path:
    """数据根目录（上传、向量、视频产物等都在其下）。"""
    return Path(os.environ.get("APP_DATA_ROOT", "./data")).expanduser()


def secret_root() -> Path:
    """密钥目录。原平台的 ``/run/tyt-rpa/secrets`` 不再使用。"""
    return Path(os.environ.get("APP_SECRET_ROOT", "./secrets")).expanduser()
