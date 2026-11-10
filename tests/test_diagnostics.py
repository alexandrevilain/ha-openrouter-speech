"""Diagnostics tests."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openrouter_speech.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.core import HomeAssistant


async def test_diagnostics_redacts_api_key(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await async_get_config_entry_diagnostics(hass, init_integration)

    assert result["entry"]["data"]["api_key"] == "**REDACTED**"
    assert "sk-or-secret" not in str(result)
    assert len(result["entry"]["subentries"]) == 2
