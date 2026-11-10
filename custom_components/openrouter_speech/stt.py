"""Speech to text support for OpenRouter."""

from collections.abc import AsyncIterable
from typing import TYPE_CHECKING, override

from homeassistant.components import stt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OpenRouterAuthError, OpenRouterError, wav_wrap
from .const import (
    CONF_LANGUAGE_MODE,
    CONF_MODEL,
    LANGUAGE_MODE_AUTO,
    LOGGER,
    SUPPORTED_LANGUAGES,
)
from .entity import OpenRouterSpeechEntity

if TYPE_CHECKING:
    from . import OpenRouterConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OpenRouterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up STT entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "stt":
            continue

        async_add_entities(
            [OpenRouterSTTEntity(config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class OpenRouterSTTEntity(stt.SpeechToTextEntity, OpenRouterSpeechEntity):
    """OpenRouter speech to text entity."""

    @property
    @override
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return SUPPORTED_LANGUAGES

    @property
    @override
    def supported_formats(self) -> list[stt.AudioFormats]:
        """Return a list of supported formats."""
        return [stt.AudioFormats.WAV]

    @property
    @override
    def supported_codecs(self) -> list[stt.AudioCodecs]:
        """Return a list of supported codecs."""
        return [stt.AudioCodecs.PCM]

    @property
    @override
    def supported_bit_rates(self) -> list[stt.AudioBitRates]:
        """Return a list of supported bit rates."""
        return list(stt.AudioBitRates)

    @property
    @override
    def supported_sample_rates(self) -> list[stt.AudioSampleRates]:
        """Return a list of supported sample rates."""
        return list(stt.AudioSampleRates)

    @property
    @override
    def supported_channels(self) -> list[stt.AudioChannels]:
        """Return a list of supported channels."""
        return [stt.AudioChannels.CHANNEL_MONO, stt.AudioChannels.CHANNEL_STEREO]

    @override
    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Process an audio stream to STT service."""
        pcm = bytearray()
        async for chunk in stream:
            pcm.extend(chunk)
        if not pcm:
            # Nothing to transcribe; don't pay for a request.
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        # Home Assistant streams headerless PCM even when the format is WAV.
        audio = wav_wrap(
            pcm,
            metadata.sample_rate.value,
            metadata.bit_rate.value // 8,
            metadata.channel.value,
        )

        options = self.subentry.data
        language = None
        if options[CONF_LANGUAGE_MODE] != LANGUAGE_MODE_AUTO:
            language = metadata.language.split("-")[0].lower()

        try:
            text = await self.entry.runtime_data.async_transcribe(
                options[CONF_MODEL], audio, language
            )
        except OpenRouterAuthError as err:
            LOGGER.error("Error during STT: %s", err)
            self.entry.async_start_reauth(self.hass)
        except OpenRouterError as err:
            LOGGER.error("Error during STT: %s", err)
        else:
            LOGGER.debug("Transcript: %s", text)
            if text:
                return stt.SpeechResult(text, stt.SpeechResultState.SUCCESS)

        return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
