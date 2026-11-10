"""Fixtures for OpenRouter Speech tests."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.openrouter_speech.const import (
    DEFAULT_BASE_URL,
    DEFAULT_STT_NAME,
    DEFAULT_TTS_NAME,
    DOMAIN,
    RECOMMENDED_STT_OPTIONS,
    RECOMMENDED_TTS_OPTIONS,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

API = DEFAULT_BASE_URL
VOICES = ["fr_marie_neutral", "fr_marie_happy", "en_paul_neutral"]
MODELS_RESPONSE: dict[str, Any] = {
    "data": [
        {"id": "mistralai/voxtral-mini-tts-3-0", "supported_voices": VOICES},
        {"id": "other/no-voices-tts", "supported_voices": None},
    ]
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom_components in every test."""


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a config entry with one STT and one TTS subentry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="OpenRouter Speech",
        data={CONF_API_KEY: "sk-or-secret", "base_url": DEFAULT_BASE_URL},
        subentries_data=[
            {
                "subentry_type": "stt",
                "data": RECOMMENDED_STT_OPTIONS,
                "title": DEFAULT_STT_NAME,
                "unique_id": None,
            },
            {
                "subentry_type": "tts",
                "data": RECOMMENDED_TTS_OPTIONS,
                "title": DEFAULT_TTS_NAME,
                "unique_id": None,
            },
        ],
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Mock the OpenRouter endpoints hit during setup."""
    aioclient_mock.get(f"{API}/key", json={"data": {"label": "test"}})
    aioclient_mock.get(f"{API}/models", json=MODELS_RESPONSE)
    return aioclient_mock


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
) -> MockConfigEntry:
    """Set up the integration."""
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
