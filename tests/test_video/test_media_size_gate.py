"""P2 · 媒体体积闸门（方案 §8.2 阶段 5 第 5 条「⚠️ 另加下载前体积预检」）。

**结论先行（本轮核对）**：该条**已经实现**，而且不止一道 —— 因此本文件的价值不是
"新加闸门"，而是**把一条从没人测过的参数级契约钉死**。

阶段 4c 的教训在此处完全适用：全链路把 HTTP stub 掉之后，**参数级约定失效能一路绿灯**
（当时 `dimensions` 漏传就是这样躲过 328 个用例的）。视频侧同样如此 ——
`--max-filesize` 一直在传，但**没有任何用例断言它等于 `MAX_MEDIA_BYTES`**，
改动参数时不会变红。这里补齐。

实测存在的三道闸门：

1. `validate_public_url_redirects`：用 `Range: bytes=0-0` 读 `content-length`，**下载前**拒绝；
2. yt-dlp `--max-filesize MAX_MEDIA_BYTES`：音频与视频两条下载路径都带（本文件新增覆盖）；
3. `_validate_downloaded_media`：**下载后**按 `MAX_MEDIA_BYTES` 兜底并清理超限文件
   （已由 `test_network_safety.py::test_downloaded_media_size_limit_removes_oversized_file` 覆盖，此处不重复）。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.video import acquire


def _fake_run_command(out_dir: Path, name: str, captured: dict[str, list[str]]):
    """拦截 yt-dlp 调用：记录 argv，并造出它本应产出的媒体文件。"""

    def run(command: list[str], timeout: float) -> SimpleNamespace:
        captured["command"] = list(command)
        target = out_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * 32)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return run


@pytest.fixture
def offline_yt_dlp(monkeypatch: pytest.MonkeyPatch) -> None:
    """去掉网络与外部二进制依赖：只观察 yt-dlp 的命令行。"""
    monkeypatch.setattr(acquire, "validate_public_url_redirects", lambda *a, **k: "https://cdn.example/media")
    monkeypatch.setattr(acquire, "ffmpeg_executable", lambda: "ffmpeg")


def test_audio_download_passes_max_filesize_to_yt_dlp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_yt_dlp: None
) -> None:
    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(acquire, "run_command", _fake_run_command(tmp_path, "audio.mp3", captured))

    acquire.download_url_audio("https://public.example/video", tmp_path, 30.0)

    command = captured["command"]
    assert "--max-filesize" in command, command
    assert command[command.index("--max-filesize") + 1] == str(acquire.MAX_MEDIA_BYTES)


def test_video_download_passes_max_filesize_to_yt_dlp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_yt_dlp: None
) -> None:
    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(acquire, "run_command", _fake_run_command(tmp_path, "video.mp4", captured))

    acquire.download_url_video("https://public.example/video", tmp_path, 30.0)

    command = captured["command"]
    assert "--max-filesize" in command, command
    assert command[command.index("--max-filesize") + 1] == str(acquire.MAX_MEDIA_BYTES)


def test_pre_download_content_length_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """第一道闸门：只看响应头就能在**下载前**拒绝超限媒体。

    这一道是三道里最省流量的 —— 5 Mbps 带宽下，若靠下载后才发现超限，
    字节已经花掉了（方案 §7.4 的 500GB 月流量包按出站计费的是服务器上行，
    但入站同样占带宽窗口）。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-length": str(acquire.MAX_MEDIA_BYTES + 1),
                "content-type": "video/mp4",
            },
        )

    real_client = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(acquire, "validate_public_url", lambda url: None)
    monkeypatch.setattr(
        acquire.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    with pytest.raises(ValueError, match="size limit"):
        acquire.validate_public_url_redirects("https://public.example/huge.mp4", 1)
