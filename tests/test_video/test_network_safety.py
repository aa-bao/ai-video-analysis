from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.video import acquire


def test_redirect_to_private_network_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []

    def validate(url: str) -> None:
        if "127.0.0.1" in url:
            raise ValueError("private-network URLs are not allowed")

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    real_client = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(acquire, "validate_public_url", validate)
    monkeypatch.setattr(
        acquire.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    with pytest.raises(ValueError, match="private-network"):
        acquire.validate_public_url_redirects("https://public.example/media", 1)
    assert requested == ["https://public.example/media"]


def test_cookie_header_only_contains_matching_domain(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".example.com\tTRUE\t/\tTRUE\t2147483647\tsession\texample-secret\n"
        ".other.test\tTRUE\t/\tFALSE\t2147483647\tother\tother-secret\n",
        encoding="utf-8",
    )

    header = acquire._cookie_header_for_url(cookie_file, "https://cdn.example.com/image.jpg")
    assert "session=example-secret" in header
    assert "other-secret" not in header
    assert acquire._cookie_header_for_url(cookie_file, "https://unrelated.test/image.jpg") == ""


def test_downloaded_media_size_limit_removes_oversized_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"x" * 8)
    monkeypatch.setattr(acquire, "MAX_MEDIA_BYTES", 4)

    with pytest.raises(RuntimeError, match="size limit"):
        acquire._validate_downloaded_media(media)
    assert not media.exists()


def test_private_extractor_media_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="private-network"):
        acquire._validate_extracted_urls(
            {"formats": [{"url": "http://169.254.169.254/latest/meta-data"}]}
        )


def test_production_yt_dlp_fails_closed_without_egress_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("VIDEO_MEDIA_EGRESS_PROXY", raising=False)

    with pytest.raises(acquire.AcquisitionError, match="VIDEO_MEDIA_EGRESS_PROXY"):
        acquire._yt_dlp_proxy_args(no_proxy=True)


def test_production_yt_dlp_cannot_bypass_configured_egress_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("VIDEO_MEDIA_EGRESS_PROXY", "http://media-egress.internal:3128")

    assert acquire._yt_dlp_proxy_args(no_proxy=True) == [
        "--proxy",
        "http://media-egress.internal:3128",
    ]


def test_production_preflight_uses_same_egress_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("VIDEO_MEDIA_EGRESS_PROXY", "http://media-egress.internal:3128")
    monkeypatch.setattr(acquire, "validate_public_url", lambda source: None)
    captured: dict[str, object] = {}

    class StopClient(Exception):
        pass

    def client(**kwargs):
        captured.update(kwargs)
        raise StopClient

    monkeypatch.setattr(acquire.httpx, "Client", client)

    with pytest.raises(StopClient):
        acquire.validate_public_url_redirects("https://public.example/video", 1)
    assert captured["proxy"] == "http://media-egress.internal:3128"
    assert captured["trust_env"] is False


def test_production_probe_does_not_start_yt_dlp_without_egress_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("VIDEO_MEDIA_EGRESS_PROXY", raising=False)
    monkeypatch.setattr(
        acquire, "validate_public_url_redirects", lambda source, *args, **kwargs: source
    )
    started = False

    def run_command(*args, **kwargs):
        nonlocal started
        started = True
        raise AssertionError("yt-dlp must not start")

    monkeypatch.setattr(acquire, "run_command", run_command)

    with pytest.raises(acquire.AcquisitionError, match="VIDEO_MEDIA_EGRESS_PROXY"):
        acquire.probe_media_info("https://public.example/video", timeout=1)
    assert started is False
