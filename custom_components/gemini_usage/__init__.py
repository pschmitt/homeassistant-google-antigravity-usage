"""Google Gemini Usage integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
import json
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client

from .api import GeminiUsageApiClient
from .const import CONF_SCAN_INTERVAL, CONF_TOKEN, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import GeminiUsageCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Google Gemini Usage from a config entry."""
    session = aiohttp_client.async_get_clientsession(hass)
    token = entry.data[CONF_TOKEN]

    @callback
    def _on_token_refreshed(new_access_token: str) -> None:
        """Persist updated access token while keeping refresh token."""
        _LOGGER.debug("Persisting refreshed access token for entry %s", entry.entry_id)
        raw_val = entry.data.get(CONF_TOKEN, "")
        if isinstance(raw_val, str) and raw_val.strip().startswith("{"):
            try:
                parsed = json.loads(raw_val)
                if "token" in parsed and isinstance(parsed["token"], dict):
                    parsed["token"]["access_token"] = new_access_token
                    hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, CONF_TOKEN: json.dumps(parsed)},
                    )
                    return
            except Exception:  # noqa: BLE001
                pass
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_TOKEN: new_access_token},
        )

    client = GeminiUsageApiClient(
        session=session,
        token=token,
        on_token_refreshed=_on_token_refreshed,
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = GeminiUsageCoordinator(
        hass=hass,
        entry=entry,
        client=client,
        update_interval_seconds=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    coordinator: GeminiUsageCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator.update_interval = timedelta(seconds=interval)
