"""TTS entity tests."""

import re

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.openrouter_speech.api import OpenRouterError
from homeassistant.components import tts
from homeassistant.components.tts import DATA_COMPONENT, TextToSpeechEntity, Voice
from homeassistant.core import HomeAssistant

from .conftest import API, VOICES


def _entity(hass: HomeAssistant) -> TextToSpeechEntity:
    entity = hass.data[DATA_COMPONENT].get_entity("tts.openrouter_tts")
    assert entity is not None
    return entity


async def test_tts_voices_and_defaults(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    entity = _entity(hass)
    assert entity.async_get_supported_voices("fr-FR") == [Voice(v, v) for v in VOICES]
    assert entity.default_options == {"voice": "fr_marie_neutral"}
    # Home Assistant converts mp3 itself when a satellite asks for wav.
    assert entity.supported_options == ["voice"]


async def test_tts_mp3(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(f"{API}/audio/speech", content=b"ID3mp3data")

    result = await _entity(hass).async_get_tts_audio(
        "Bonjour", "fr-FR", {"voice": "fr_marie_happy"}
    )

    assert result == ("mp3", b"ID3mp3data")
    assert aioclient_mock.mock_calls[-1][2] == {
        "model": "mistralai/voxtral-mini-tts-3-0",
        "input": "Bonjour",
        "response_format": "mp3",
        "voice": "fr_marie_happy",
    }


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (402, "Insufficient OpenRouter credits"),
        (429, "OpenRouter rate limit reached"),
        (502, "OpenRouter upstream failure (HTTP 502)"),
    ],
)
async def test_tts_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    message: str,
) -> None:
    aioclient_mock.post(
        f"{API}/audio/speech",
        status=status,
        json={"error": {"code": status, "message": "upstream says no"}},
    )

    with pytest.raises(OpenRouterError, match=re.escape(message)):
        await _entity(hass).async_get_tts_audio("Bonjour", "fr-FR", {})


async def test_tts_auth_error_starts_reauth(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(f"{API}/audio/speech", status=401)

    with pytest.raises(OpenRouterError, match="Invalid OpenRouter API key"):
        await _entity(hass).async_get_tts_audio("Bonjour", "fr-FR", {})
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_tts_invalid_models_response(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(f"{API}/key", json={"data": {"label": "test"}})
    aioclient_mock.get(f"{API}/models", text="<html>proxy error</html>")
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # The entity is still added; only the configured default voice is offered.
    voices = _entity(hass).async_get_supported_voices("fr-FR")
    assert voices == [Voice("fr_marie_neutral", "fr_marie_neutral")]


async def test_tts_through_manager(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Go through Home Assistant's TTS manager, not the entity directly."""
    aioclient_mock.post(f"{API}/audio/speech", content=b"ID3mp3data")

    # No file cache: it would outlive the test and replay the audio next run.
    stream = hass.data[tts.DATA_TTS_MANAGER].async_create_result_stream(
        "tts.openrouter_tts", use_file_cache=False, language="fr-FR"
    )
    stream.async_set_message("Bonjour")
    data = b"".join([chunk async for chunk in stream.async_stream_result()])

    assert data == b"ID3mp3data"
    # The manager merged the subentry's default voice into the options.
    speech = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert [c[2]["voice"] for c in speech] == ["fr_marie_neutral"]
