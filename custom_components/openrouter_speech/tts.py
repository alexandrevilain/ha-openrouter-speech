"""Text to speech support for OpenRouter."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, override

from propcache.api import cached_property

from homeassistant.components.tts import (
    ATTR_VOICE,
    TextToSpeechEntity,
    TtsAudioType,
    Voice,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OpenRouterAuthError, OpenRouterError
from .const import CONF_MODEL, LOGGER, SUPPORTED_LANGUAGES
from .entity import OpenRouterSpeechEntity

if TYPE_CHECKING:
    from . import OpenRouterConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OpenRouterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up TTS entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "tts":
            continue

        async_add_entities(
            [OpenRouterTTSEntity(config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class OpenRouterTTSEntity(TextToSpeechEntity, OpenRouterSpeechEntity):
    """OpenRouter TTS entity."""

    # preferred_format is left out on purpose: OpenRouter only documents mp3,
    # so Home Assistant converts it with ffmpeg when a satellite asks for wav.
    _attr_supported_options = [ATTR_VOICE]
    _attr_supported_languages = SUPPORTED_LANGUAGES
    # Unused, but required by base class.
    # The models detect the input language automatically.
    _attr_default_language = "en-US"
    # The TTS manager refuses engines without a name of their own.
    _attr_has_entity_name = False

    def __init__(self, entry: OpenRouterConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the entity."""
        super().__init__(entry, subentry)
        self._attr_name = subentry.title

    @override
    async def async_added_to_hass(self) -> None:
        """Warm the voice cache without holding up platform setup."""
        await super().async_added_to_hass()
        self.entry.async_create_task(
            self.hass, self._async_fetch_voices(), "openrouter_speech_voices"
        )

    async def _async_fetch_voices(self) -> None:
        """Fetch the voices of the configured model into the client cache."""
        try:
            await self.entry.runtime_data.async_list_voices(
                self.subentry.data[CONF_MODEL]
            )
        except OpenRouterError as err:
            # Opening the TTS subentry form retries the fetch.
            LOGGER.warning("Could not fetch OpenRouter voices: %s", err)

    @callback
    @override
    def async_get_supported_voices(self, language: str) -> list[Voice] | None:
        """Return a list of supported voices for a language."""
        voices = self.entry.runtime_data.cached_voices(self.subentry.data[CONF_MODEL])
        if (default := self.subentry.data.get(ATTR_VOICE)) and default not in voices:
            voices.insert(0, default)
        return [Voice(voice, voice) for voice in voices] or None

    @cached_property
    @override
    def default_options(self) -> Mapping[str, Any]:
        """Return a mapping with the default options."""
        return {ATTR_VOICE: self.subentry.data.get(ATTR_VOICE)}

    @override
    async def async_get_tts_audio(
        self, message: str, language: str, options: dict[str, Any]
    ) -> TtsAudioType:
        """Load tts audio file from the engine."""
        # Home Assistant already merged default_options into options.
        try:
            audio = await self.entry.runtime_data.async_speak(
                self.subentry.data[CONF_MODEL], message, options.get(ATTR_VOICE), "mp3"
            )
        except OpenRouterAuthError:
            self.entry.async_start_reauth(self.hass)
            raise
        return "mp3", audio
