"""视频模块配置测试。

独立化改造后：
- 环境语义从 ``RPA_ENVIRONMENT``(LOCAL/TEST/PRODUCTION) 改为
  ``APP_ENV``(development/test/production)
- 生产类环境的数据根从平台绝对路径 ``/opt/tyt-rpa/app/data/video``
  改为 ``<APP_DATA_ROOT>/video``
"""
from pathlib import Path

import pytest

from src.video.config import VideoConfig

_PATH_VARIABLES = (
    "QUICK_WATCH_TASK_ROOT",
    "QUICK_WATCH_OUTPUT_ROOT",
    "QUICK_WATCH_UPLOAD_DIR",
    "QUICK_WATCH_LIBRARY_ROOT",
)

_COOKIE_VARIABLES = (
    "QUICK_WATCH_DOUYIN_COOKIE_FILE",
    "WX_CHANNELS_COOKIE_FILE",
)


@pytest.mark.parametrize("environment", ["test", "production"])
def test_production_video_directories_stay_under_data_root_despite_overrides(
    monkeypatch: pytest.MonkeyPatch, environment: str, tmp_path: Path
) -> None:
    """生产类环境：目录一律锁定在数据根下，忽略各项覆盖变量（镜像层只读）。"""
    for name in _PATH_VARIABLES:
        monkeypatch.setenv(name, str(Path("/read-only-root") / name.lower()))
    for name in _COOKIE_VARIABLES:
        monkeypatch.setenv(name, str(Path("/read-only-root") / name.lower()))
    monkeypatch.setenv("APP_DATA_ROOT", str(tmp_path))

    config = VideoConfig.load(environment=environment)

    video_root = tmp_path / "video"
    assert config.task_root == video_root / "tasks"
    assert config.output_root == video_root / "output"
    assert config.upload_dir == video_root / "uploads"
    assert config.library_root == video_root / "library"
    assert config.douyin_cookie_file == video_root / "cookies" / "cookies_douyin.txt"
    assert config.wx_cookie_file == video_root / "cookies" / "wx-cookies" / "cookies.json"


def test_development_video_directories_keep_environment_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = {
        "QUICK_WATCH_TASK_ROOT": tmp_path / "tasks",
        "QUICK_WATCH_OUTPUT_ROOT": tmp_path / "output",
        "QUICK_WATCH_UPLOAD_DIR": tmp_path / "uploads",
        "QUICK_WATCH_LIBRARY_ROOT": tmp_path / "library",
    }
    for name, path in paths.items():
        monkeypatch.setenv(name, str(path))

    config = VideoConfig.load(environment="development")

    assert config.task_root == paths["QUICK_WATCH_TASK_ROOT"]
    assert config.output_root == paths["QUICK_WATCH_OUTPUT_ROOT"]
    assert config.upload_dir == paths["QUICK_WATCH_UPLOAD_DIR"]
    assert config.library_root == paths["QUICK_WATCH_LIBRARY_ROOT"]


def test_unknown_environment_cannot_use_local_video_directories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in _PATH_VARIABLES:
        monkeypatch.setenv(name, f"/local-only/{name.lower()}")

    with pytest.raises(ValueError, match="Unsupported APP_ENV: staging"):
        VideoConfig.load(environment="staging")
