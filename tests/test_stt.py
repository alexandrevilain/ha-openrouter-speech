"""STT entity tests."""

import base64
from collections.abc import AsyncIterator
import io
import wave

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from homeassistant.components import stt
from homeassistant.core import HomeAssistant

from .conftest import API

METADATA = stt.SpeechMetadata(
    language="fr-FR",
    format=stt.AudioFormats.WAV,
    codec=stt.AudioCodecs.PCM,
    bit_rate=stt.AudioBitRates.BITRATE_16,
    sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
    channel=stt.AudioChannels.CHANNEL_MONO,
)
PCM = b"\x01\x00" * 1600


async def _stream() -> AsyncIterator[bytes]:
    yield PCM[:1600]
    yield PCM[1600:]


def _entity(hass: HomeAssistant) -> stt.SpeechToTextEntity:
    entity = stt.async_get_speech_to_text_entity(hass, "stt.openrouter_stt")
    assert entity is not None
    return entity


async def test_stt_success(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(
        f"{API}/audio/transcriptions",
        json={"text": " Allume la lumière. ", "usage": {"seconds": 0.1}},
    )

    result = await _entity(hass).async_process_audio_stream(METADATA, _stream())

    assert result == stt.SpeechResult(
        "Allume la lumière.", stt.SpeechResultState.SUCCESS
    )
    payload = aioclient_mock.mock_calls[-1][2]
    assert payload["model"] == "mistralai/voxtral-mini-transcribe-3-0"
    assert payload["language"] == "fr"
    assert payload["input_audio"]["format"] == "wav"
    with wave.open(io.BytesIO(base64.b64decode(payload["input_audio"]["data"]))) as wav:
        assert wav.getframerate() == 16000
        assert wav.getsampwidth() == 2
        assert wav.getnchannels() == 1
        assert wav.readframes(wav.getnframes()) == PCM


async def test_stt_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(
        f"{API}/audio/transcriptions",
        status=402,
        json={"error": {"code": 402, "message": "Insufficient credits"}},
    )

    result = await _entity(hass).async_process_audio_stream(METADATA, _stream())

    assert result == stt.SpeechResult(None, stt.SpeechResultState.ERROR)


async def test_stt_timeout(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(f"{API}/audio/transcriptions", exc=TimeoutError())

    result = await _entity(hass).async_process_audio_stream(METADATA, _stream())

    assert result.result is stt.SpeechResultState.ERROR


async def test_stt_empty_audio_skips_request(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    async def empty() -> AsyncIterator[bytes]:
        return
        yield

    calls = aioclient_mock.call_count
    result = await _entity(hass).async_process_audio_stream(METADATA, empty())

    assert result == stt.SpeechResult(None, stt.SpeechResultState.ERROR)
    assert aioclient_mock.call_count == calls


async def test_stt_invalid_response(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(f"{API}/audio/transcriptions", json=["not", "an", "object"])

    result = await _entity(hass).async_process_audio_stream(METADATA, _stream())

    assert result == stt.SpeechResult(None, stt.SpeechResultState.ERROR)
