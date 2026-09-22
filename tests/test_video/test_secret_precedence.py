from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.video.settings import VideoAgentSettings, VideoAgentSettingsService


def test_settings_copy_preserves_runtime_only_asr_configuration() -> None:
    settings = VideoAgentSettings(
        asr_endpoint="https://asr.example.test/submit",
        asr_public_base_url="https://app.example.test/api/video/asr-media",
    )

    copied = settings.copy()

    assert copied is not settings
    assert copied.asr_endpoint == settings.asr_endpoint
    assert copied.asr_public_base_url == settings.asr_public_base_url


@pytest.mark.asyncio
async def test_controller_secret_wins_over_stale_database_key(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "VOLC_ASR_API_KEY").write_text("controller-key\n", encoding="utf-8")
    monkeypatch.setenv("APP_SECRET_ROOT", str(tmp_path))
    stale = SimpleNamespace(
        asr_provider="volcengine",
        asr_model="bigmodel",
        asr_api_key="stale-db-key",
        asr_app_id="",
        asr_access_token="",
        chat_base_url="",
        chat_model="",
        chat_api_key="",
        qa_model="",
        qa_base_url="",
        qa_api_key="",
        frames=12,
    )

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return None

    class FakeRepository:
        def __init__(self, session):
            pass

        async def get(self):
            return stale

    monkeypatch.setattr("src.video.settings.VideoSettingRepository", FakeRepository)
    current = VideoAgentSettings()
    await VideoAgentSettingsService(current, SessionContext).restore()
    assert current.asr_api_key == "controller-key"
