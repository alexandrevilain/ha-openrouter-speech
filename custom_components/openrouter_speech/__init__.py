"""The OpenRouter Speech integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OpenRouterAuthError, OpenRouterClient, OpenRouterError
from .const import CONF_BASE_URL, DEFAULT_BASE_URL

PLATFORMS = (Platform.STT, Platform.TTS)

type OpenRouterConfigEntry = ConfigEntry[OpenRouterClient]


async def async_setup_entry(hass: HomeAssistant, entry: OpenRouterConfigEntry) -> bool:
    """Set up OpenRouter Speech from a config entry."""
    client = OpenRouterClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY],
        entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
    )
    try:
        await client.async_validate_key()
    except OpenRouterAuthError as err:
        raise ConfigEntryAuthFailed(err) from err
    except OpenRouterError as err:
        raise ConfigEntryNotReady(err) from err

    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OpenRouterConfigEntry) -> bool:
    """Unload OpenRouter Speech."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(
    hass: HomeAssistant, entry: OpenRouterConfigEntry
) -> None:
    """Reload when the entry or one of its subentries changes."""
    await hass.config_entries.async_reload(entry.entry_id)
