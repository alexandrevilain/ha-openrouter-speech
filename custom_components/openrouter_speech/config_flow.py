"""Config flow for OpenRouter Speech integration."""

from collections.abc import Mapping
from typing import Any, override

import probatio

from homeassistant.components.tts import ATTR_VOICE
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.typing import VolDictType

from .api import OpenRouterAuthError, OpenRouterClient, OpenRouterError
from .const import (
    CONF_BASE_URL,
    CONF_LANGUAGE_MODE,
    CONF_MODEL,
    DEFAULT_BASE_URL,
    DEFAULT_NAME,
    DEFAULT_STT_NAME,
    DEFAULT_TTS_NAME,
    DOMAIN,
    LANGUAGE_MODE_AUTO,
    LANGUAGE_MODE_PIPELINE,
    LOGGER,
    RECOMMENDED_STT_OPTIONS,
    RECOMMENDED_TTS_OPTIONS,
    STT_MODELS,
    TTS_MODELS,
    recommended_tts_options,
)

STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        probatio.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
    }
)


class OpenRouterSpeechConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenRouter Speech."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        return await self._async_step_api_key(user_input, "user")

    async def _async_step_api_key(
        self, user_input: dict[str, Any] | None, step_id: str
    ) -> ConfigFlowResult:
        """Handle an API key form."""
        errors: dict[str, str] = {}
        entry: ConfigEntry | None = None
        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
        elif self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()

        if user_input is not None:
            self._async_abort_entries_match({CONF_API_KEY: user_input[CONF_API_KEY]})
            client = OpenRouterClient(
                async_get_clientsession(self.hass),
                user_input[CONF_API_KEY],
                user_input.get(CONF_BASE_URL, DEFAULT_BASE_URL),
            )
            try:
                await client.async_validate_key()
            except OpenRouterAuthError:
                errors["base"] = "invalid_auth"
            except OpenRouterError:
                errors["base"] = "cannot_connect"
            except Exception:
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if entry is not None:
                    if entry.update_listeners:
                        return self.async_update_and_abort(
                            entry, data_updates=user_input
                        )
                    return self.async_update_reload_and_abort(
                        entry, data_updates=user_input
                    )
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data=user_input,
                    subentries=[
                        {
                            "subentry_type": "stt",
                            "data": RECOMMENDED_STT_OPTIONS,
                            "title": DEFAULT_STT_NAME,
                            "unique_id": None,
                        },
                        {
                            "subentry_type": "tts",
                            "data": recommended_tts_options(self.hass.config.language),
                            "title": DEFAULT_TTS_NAME,
                            "unique_id": None,
                        },
                    ],
                )

        return self.async_show_form(
            step_id=step_id,
            # Pre-fill the entry's current values so an untouched base URL
            # is not reset to the default on reauth/reconfigure.
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA,
                {**(entry.data if entry else {}), **(user_input or {})},
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        return await self._async_step_api_key(user_input, "reauth_confirm")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the API key or base URL."""
        return await self._async_step_api_key(user_input, "reconfigure")

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "stt": OpenRouterSubentrySTTFlowHandler,
            "tts": OpenRouterSubentryTTSFlowHandler,
        }


class OpenRouterSubentryFlowHandler(ConfigSubentryFlow):
    """Shared add/reconfigure plumbing for STT and TTS subentries."""

    options: dict[str, Any]
    recommended: dict[str, Any]
    default_name: str

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == SOURCE_USER

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a subentry."""
        self.options = self._recommended()
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of a subentry."""
        self.options = {**self.recommended, **self._get_reconfigure_subentry().data}
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage the subentry options."""
        # abort if entry is not loaded
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        options = self.options
        if user_input is not None:
            options.update(user_input)
        errors: dict[str, str] = {}
        step_schema: VolDictType = {}
        if self._is_new:
            step_schema[probatio.Required(CONF_NAME, default=self.default_name)] = str
        step_schema.update(await self._async_schema(user_input, errors))

        if user_input is not None and not errors:
            if self._is_new:
                return self.async_create_entry(
                    title=options.pop(CONF_NAME),
                    data=options,
                )
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema), options
            ),
            errors=errors,
        )

    def _recommended(self) -> dict[str, Any]:
        """Return the options a new subentry starts from."""
        return self.recommended.copy()

    async def _async_schema(
        self, user_input: dict[str, Any] | None, errors: dict[str, str]
    ) -> VolDictType:
        """Return the type-specific fields, adding validation errors."""
        raise NotImplementedError


class OpenRouterSubentrySTTFlowHandler(OpenRouterSubentryFlowHandler):
    """Flow for managing OpenRouter STT subentries."""

    recommended = RECOMMENDED_STT_OPTIONS
    default_name = DEFAULT_STT_NAME

    @override
    async def _async_schema(
        self, user_input: dict[str, Any] | None, errors: dict[str, str]
    ) -> VolDictType:
        client: OpenRouterClient = self._get_entry().runtime_data
        try:
            models = await client.async_list_models("transcription")
        except OpenRouterError as err:
            LOGGER.warning("Could not fetch OpenRouter STT models: %s", err)
            models = []
        return {
            probatio.Required(CONF_MODEL): SelectSelector(
                SelectSelectorConfig(
                    options=models or STT_MODELS,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            probatio.Required(CONF_LANGUAGE_MODE): SelectSelector(
                SelectSelectorConfig(
                    options=[LANGUAGE_MODE_PIPELINE, LANGUAGE_MODE_AUTO],
                    translation_key=CONF_LANGUAGE_MODE,
                )
            ),
        }


class OpenRouterSubentryTTSFlowHandler(OpenRouterSubentryFlowHandler):
    """Flow for managing OpenRouter TTS subentries."""

    recommended = RECOMMENDED_TTS_OPTIONS
    default_name = DEFAULT_TTS_NAME
    _shown: dict[str, Any]

    @override
    def _recommended(self) -> dict[str, Any]:
        return recommended_tts_options(self.hass.config.language)

    @override
    async def _async_schema(
        self, user_input: dict[str, Any] | None, errors: dict[str, str]
    ) -> VolDictType:
        if user_input is None:
            self._shown = dict(self.options)  # what the form was opened with
        client: OpenRouterClient = self._get_entry().runtime_data
        try:
            voices = await client.async_list_voices(self.options[CONF_MODEL])
        except OpenRouterError as err:
            LOGGER.warning("Could not fetch OpenRouter voices: %s", err)
            voices = []
        if user_input is not None and (
            ATTR_VOICE not in user_input
            # The model changed but the voice is the old model's and can't be
            # checked against the new one: don't send it to a model that may
            # not know it.
            or (
                not voices
                and self.options[CONF_MODEL] != self._shown[CONF_MODEL]
                and self.options.get(ATTR_VOICE) == self._shown.get(ATTR_VOICE)
            )
        ):
            self.options[ATTR_VOICE] = ""  # cleared: let the model pick
        # Only validate when OpenRouter publishes a voice list for the model.
        if (
            user_input is not None
            and voices
            and self.options.get(ATTR_VOICE)
            and self.options[ATTR_VOICE] not in voices
        ):
            errors[ATTR_VOICE] = "invalid_voice"

        return {
            probatio.Required(CONF_MODEL): SelectSelector(
                SelectSelectorConfig(
                    options=client.cached_speech_models() or TTS_MODELS,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            probatio.Optional(ATTR_VOICE): SelectSelector(
                SelectSelectorConfig(
                    options=voices,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
        }
