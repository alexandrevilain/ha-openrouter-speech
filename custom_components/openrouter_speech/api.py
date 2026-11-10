"""Minimal client for the OpenRouter audio APIs."""

import asyncio
import base64
import io
import json
from typing import Any
import wave

import aiohttp

from homeassistant.exceptions import HomeAssistantError

from .const import LOGGER

KEY_TIMEOUT = aiohttp.ClientTimeout(total=10)
STT_TIMEOUT = aiohttp.ClientTimeout(total=30)
TTS_TIMEOUT = aiohttp.ClientTimeout(total=60)

_STATUS_MESSAGES = {
    400: "OpenRouter rejected the request",
    401: "Invalid OpenRouter API key",
    402: "Insufficient OpenRouter credits",
    403: "OpenRouter key disabled or spend limit reached",
    404: "Unknown model or no OpenRouter provider available",
    429: "OpenRouter rate limit reached, try again later",
}


class OpenRouterError(HomeAssistantError):
    """An OpenRouter API call failed."""


class OpenRouterAuthError(OpenRouterError):
    """The API key was rejected."""


def wav_wrap(
    pcm: bytes | bytearray, sample_rate: int, sample_width: int, channels: int
) -> bytes:
    """Wrap raw PCM frames in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _error(status: int, body: bytes) -> OpenRouterError:
    """Build an exception from an HTTP error response."""
    if status >= 500:
        message = f"OpenRouter upstream failure (HTTP {status})"
    else:
        message = _STATUS_MESSAGES.get(
            status, f"OpenRouter request failed (HTTP {status})"
        )
    try:
        detail = json.loads(body)["error"]["message"]
    except ValueError, KeyError, TypeError:
        detail = None
    if detail:
        message = f"{message}: {detail}"
    # 403 is also a spend limit on a still-valid key: retry, don't ask for a new key.
    return (OpenRouterAuthError if status == 401 else OpenRouterError)(message)


class OpenRouterClient:
    """Calls the OpenRouter audio endpoints with a shared aiohttp session."""

    def __init__(
        self, session: aiohttp.ClientSession, api_key: str, base_url: str
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._voices: dict[str, list[str]] | None = None
        self._voices_lock = asyncio.Lock()

    async def _request(
        self,
        method: str,
        path: str,
        request_timeout: aiohttp.ClientTimeout,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> bytes:
        """Send a request and return the raw response body."""
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                json=payload,
                params=params,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=request_timeout,
            ) as resp:
                body = await resp.read()
                if resp.status >= 400:
                    raise _error(resp.status, body)
                return body
        except TimeoutError as err:
            raise OpenRouterError("Timed out waiting for OpenRouter") from err
        except aiohttp.ClientError as err:
            raise OpenRouterError(f"Cannot reach OpenRouter: {err}") from err

    async def async_validate_key(self) -> None:
        """Check the API key (free call)."""
        await self._request("GET", "/key", KEY_TIMEOUT)

    async def async_list_voices(self, model: str) -> list[str]:
        """Return the voices OpenRouter advertises for a TTS model."""
        # ponytail: cached for the client's lifetime; any entry or subentry
        # change reloads the entry and builds a new client.
        async with self._voices_lock:  # one /models call for concurrent callers
            if self._voices is None:
                body = await self._request(
                    "GET",
                    "/models",
                    KEY_TIMEOUT,
                    params={"output_modalities": "speech"},
                )
                try:
                    self._voices = {
                        item["id"]: list(item.get("supported_voices") or [])
                        for item in json.loads(body)["data"]
                    }
                except (ValueError, KeyError, TypeError, AttributeError) as err:
                    raise OpenRouterError("Invalid models response") from err
        return self._voices.get(model, [])

    def cached_speech_models(self) -> list[str]:
        """Return the TTS models already fetched with the voices."""
        return sorted(self._voices or [])

    async def async_list_models(self, output_modality: str) -> list[str]:
        """Return the ids of the models producing an output modality."""
        body = await self._request(
            "GET",
            "/models",
            KEY_TIMEOUT,
            params={"output_modalities": output_modality},
        )
        try:
            return sorted(item["id"] for item in json.loads(body)["data"])
        except (ValueError, KeyError, TypeError) as err:
            raise OpenRouterError("Invalid models response") from err

    def cached_voices(self, model: str) -> list[str]:
        """Return the voices already fetched for a model, without a request."""
        return (self._voices or {}).get(model, [])

    async def async_transcribe(
        self, model: str, wav_audio: bytes, language: str | None
    ) -> str:
        """Transcribe a WAV file and return the text."""
        payload: dict[str, Any] = {
            "model": model,
            "input_audio": {
                "data": base64.b64encode(wav_audio).decode(),
                "format": "wav",
            },
        }
        if language:
            payload["language"] = language
        LOGGER.debug("Transcribing %d bytes with %s", len(wav_audio), model)
        body = await self._request(
            "POST", "/audio/transcriptions", STT_TIMEOUT, payload
        )
        try:
            return (json.loads(body).get("text") or "").strip()
        except (ValueError, AttributeError) as err:
            raise OpenRouterError("Invalid transcription response") from err

    async def async_speak(
        self, model: str, text: str, voice: str | None, response_format: str
    ) -> bytes:
        """Synthesize text; returns raw audio bytes in response_format."""
        payload: dict[str, Any] = {
            "model": model,
            "input": text,
            "response_format": response_format,
        }
        if voice:
            payload["voice"] = voice
        LOGGER.debug("Synthesizing %d chars with %s/%s", len(text), model, voice)
        audio = await self._request("POST", "/audio/speech", TTS_TIMEOUT, payload)
        if not audio:
            raise OpenRouterError("OpenRouter returned empty audio")
        return audio
