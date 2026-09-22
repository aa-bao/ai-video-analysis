from __future__ import annotations

from pathlib import Path

import pytest

from src.video import asr
from src.video.settings import VideoAgentSettings


def test_volc_uid_is_nonsensitive_and_vendor_error_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "volc-secret-value"
    settings = VideoAgentSettings(asr_api_key=secret, asr_model="bigmodel")
    audio = tmp_path / "chunk.mp3"
    audio.write_bytes(b"audio")
    captured: dict = {}

    class Response:
        status_code = 500
        headers = {}
        content = b"error"
        text = f"vendor rejected {secret}"

        @staticmethod
        def json():
            return {"header": {"message": f"vendor rejected {secret}"}}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, json, headers):
            captured.update(json)
            return Response()

    monkeypatch.setattr(asr.httpx, "Client", Client)

    result = asr._transcribe_chunk_volc(0, 0.0, audio, settings, retries=0)

    uid = captured["user"]["uid"]
    assert uid.startswith("rag-video-")
    assert secret not in uid
    assert secret not in result["error"]
    assert "[REDACTED]" in result["error"]


def test_dashscope_media_capability_is_registered_and_revoked(tmp_path: Path) -> None:
    media = tmp_path / "chunk.mp3"
    media.write_bytes(b"audio")

    token, url = asr.register_dashscope_media(
        media, "https://app.example.test/api/video/asr-media"
    )

    assert len(token) == 64
    assert url.endswith(token)
    assert asr.resolve_dashscope_media(token) == media.resolve()
    asr.unregister_dashscope_media(token)
    assert asr.resolve_dashscope_media(token) is None


def test_dashscope_media_requires_https_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "chunk.mp3"
    media.write_bytes(b"audio")
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(asr.AsrError, match="HTTPS"):
        asr.register_dashscope_media(
            media, "http://app.example.test/api/video/asr-media"
        )
