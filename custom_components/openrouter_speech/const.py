"""Constants for the OpenRouter Speech integration."""

import logging
from typing import Any

from homeassistant.components.tts import ATTR_VOICE

DOMAIN = "openrouter_speech"
LOGGER: logging.Logger = logging.getLogger(__package__)

DEFAULT_NAME = "OpenRouter Speech"
DEFAULT_STT_NAME = "OpenRouter STT"
DEFAULT_TTS_NAME = "OpenRouter TTS"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
# Passed to the config flow as description placeholders: hassfest forbids
# URLs in strings.json / translations, they must come from the code.
API_KEY_SETTINGS_URL = "https://openrouter.ai/settings/keys"
REGIONAL_BASE_URL_EXAMPLE = "https://eu.openrouter.ai/api/v1"

CONF_BASE_URL = "base_url"
CONF_MODEL = "model"
CONF_LANGUAGE_MODE = "language_mode"

LANGUAGE_MODE_PIPELINE = "pipeline"
LANGUAGE_MODE_AUTO = "auto"

STT_MODELS = [
    "mistralai/voxtral-mini-transcribe-3-0",
    "mistralai/voxtral-small-transcribe-3-0",
]
TTS_MODELS = ["mistralai/voxtral-mini-tts-3-0"]

RECOMMENDED_STT_OPTIONS: dict[str, Any] = {
    CONF_MODEL: STT_MODELS[0],
    CONF_LANGUAGE_MODE: LANGUAGE_MODE_PIPELINE,
}
RECOMMENDED_TTS_OPTIONS: dict[str, Any] = {
    CONF_MODEL: TTS_MODELS[0],
    ATTR_VOICE: "fr_marie_neutral",
}


def recommended_tts_options(language: str) -> dict[str, Any]:
    """Return the recommended TTS options for a Home Assistant language."""
    options = RECOMMENDED_TTS_OPTIONS.copy()
    # ponytail: only the French default voice is known; other languages let
    # the model pick until someone maps a voice per language.
    if not language.lower().startswith("fr"):
        options[ATTR_VOICE] = ""
    return options


# Models behind OpenRouter vary; these are the languages the default Voxtral
# models support plus the most common Assist languages and
# regional variants (Home Assistant matches language tags exactly).
SUPPORTED_LANGUAGES = [
    "ar-SA",
    "ca-ES",
    "cs-CZ",
    "da-DK",
    "de-AT",
    "de-CH",
    "de-DE",
    "el-GR",
    "en-AU",
    "en-CA",
    "en-GB",
    "en-IE",
    "en-IN",
    "en-NZ",
    "en-US",
    "es-ES",
    "es-MX",
    "es-US",
    "fi-FI",
    "fr-BE",
    "fr-CA",
    "fr-CH",
    "fr-FR",
    "he-IL",
    "hi-IN",
    "hu-HU",
    "it-CH",
    "it-IT",
    "ja-JP",
    "ko-KR",
    "nb-NO",
    "nl-BE",
    "nl-NL",
    "pl-PL",
    "pt-BR",
    "pt-PT",
    "ro-RO",
    "ru-RU",
    "sk-SK",
    "sv-SE",
    "tr-TR",
    "uk-UA",
    "vi-VN",
    "zh-CN",
    "zh-TW",
]
