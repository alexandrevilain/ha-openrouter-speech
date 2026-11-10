"""Config and subentry flow tests."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.openrouter_speech.const import DEFAULT_BASE_URL, DOMAIN
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import API, MODELS_RESPONSE

TTS_MODEL = "mistralai/voxtral-mini-tts-3-0"


@pytest.mark.parametrize(
    ("language", "voice"), [("fr", "fr_marie_neutral"), ("en", "")]
)
async def test_user_flow_success(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, language: str, voice: str
) -> None:
    hass.config.language = language
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "sk-or-good"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"api_key": "sk-or-good", "base_url": DEFAULT_BASE_URL}
    subentries = result["result"].subentries.values()
    assert sorted(s.subentry_type for s in subentries) == ["stt", "tts"]
    # The French default voice is only offered to French installs.
    tts = next(s for s in subentries if s.subentry_type == "tts")
    assert tts.data["voice"] == voice
    # The key is sent as a bearer token to the validation endpoint.
    assert mock_api.mock_calls[0][3]["Authorization"] == "Bearer sk-or-good"


async def test_user_flow_invalid_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{API}/key", status=401, json={"error": {"code": 401, "message": "No auth"}}
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "sk-or-bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{API}/key", exc=TimeoutError())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "sk-or-x"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_setup_auth_failure_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(f"{API}/key", status=401)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_setup_spend_limit_retries_without_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A 403 (spend limit) keeps the key: retry instead of asking for a new one."""
    aioclient_mock.get(f"{API}/key", status=403)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    assert hass.config_entries.flow.async_progress() == []


async def test_stt_subentry_add_and_reconfigure(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await hass.config_entries.subentries.async_init(
        (init_integration.entry_id, "stt"),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Small STT",
            "model": "mistralai/voxtral-small-transcribe-3-0",
            "language_mode": "auto",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(
        s for s in init_integration.subentries.values() if s.title == "Small STT"
    )
    assert subentry.data == {
        "model": "mistralai/voxtral-small-transcribe-3-0",
        "language_mode": "auto",
    }

    result = await init_integration.start_subentry_reconfigure_flow(
        hass, subentry.subentry_id
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"model": "openai/whisper-large-v3", "language_mode": "pipeline"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.subentries[subentry.subentry_id].data == {
        "model": "openai/whisper-large-v3",
        "language_mode": "pipeline",
    }


async def test_tts_subentry_voice_validation(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await hass.config_entries.subentries.async_init(
        (init_integration.entry_id, "tts"),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM

    user_input = {
        "name": "Paul",
        "model": TTS_MODEL,
        "voice": "nope",
    }
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )
    assert result["errors"] == {"voice": "invalid_voice"}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**user_input, "voice": "en_paul_neutral"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "model": TTS_MODEL,
        "voice": "en_paul_neutral",
    }


async def test_tts_subentry_model_without_voices(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    tts = next(
        s for s in init_integration.subentries.values() if s.subentry_type == "tts"
    )
    result = await init_integration.start_subentry_reconfigure_flow(
        hass, tts.subentry_id
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"model": "other/no-voices-tts", "voice": "fr_marie_neutral"},
    )
    assert result["reason"] == "reconfigure_successful"
    # The old model's voice is dropped: the new model can't confirm it knows it.
    assert init_integration.subentries[tts.subentry_id].data["voice"] == ""


async def test_tts_subentry_custom_voice_for_model_without_voices(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    tts = next(
        s for s in init_integration.subentries.values() if s.subentry_type == "tts"
    )
    result = await init_integration.start_subentry_reconfigure_flow(
        hass, tts.subentry_id
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"model": "other/no-voices-tts", "voice": "custom"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.subentries[tts.subentry_id].data["voice"] == "custom"


async def test_reconfigure_prefills_current_base_url(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    eu = "https://eu.openrouter.ai/api/v1"
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "base_url": eu}
    )
    result = await mock_config_entry.start_reconfigure_flow(hass)
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
    }
    assert suggested == {"api_key": "sk-or-secret", "base_url": eu}


async def test_tts_subentry_clear_voice(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    tts = next(
        s for s in init_integration.subentries.values() if s.subentry_type == "tts"
    )

    def models_calls() -> int:
        return sum(c[1].path.endswith("/models") for c in aioclient_mock.mock_calls)

    result = await init_integration.start_subentry_reconfigure_flow(
        hass, tts.subentry_id
    )
    # The form reuses the voice list the entity already fetched.
    assert models_calls() == 1
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"model": TTS_MODEL}
    )
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.subentries[tts.subentry_id].data["voice"] == ""
    # Saving reloads the entry, whose fresh client fetches once more.
    assert models_calls() == 2


async def test_subentry_models_discovered(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    def model_options(result: Any) -> list[str]:
        key = next(k for k in result["data_schema"].schema if str(k) == "model")
        return result["data_schema"].schema[key].config["options"]

    for subentry_type in ("stt", "tts"):
        result = await hass.config_entries.subentries.async_init(
            (init_integration.entry_id, subentry_type),
            context={"source": config_entries.SOURCE_USER},
        )
        assert model_options(result) == sorted(m["id"] for m in MODELS_RESPONSE["data"])
