"""Google Antigravity Usage integration for Home Assistant."""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow
from homeassistant.helpers.config_entry_oauth2_flow import (
    ImplementationUnavailableError,
)

from .api import GoogleAntigravityUsageApiClient
from .const import (
    CONF_ACCOUNT_EMAIL,
    CONF_ACCOUNT_ID,
    CONF_ACCOUNT_NAME,
    CONF_AUTH_IMPLEMENTATION,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import GoogleAntigravityUsageCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate tier-keyed entries to account-keyed entries."""
    if entry.version > 1:
        return True

    account_info: dict[str, Any] = {}
    session = aiohttp_client.async_get_clientsession(hass)
    client = GoogleAntigravityUsageApiClient(session=session, token=entry.data[CONF_TOKEN])
    try:
        account_info = await client.async_fetch_account_info()
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Could not identify the Google account while migrating Antigravity Usage entry %s",
            entry.entry_id,
        )

    account_id = account_info.get("account_id")
    data = {**entry.data}
    if account_id:
        data.update(
            {
                CONF_ACCOUNT_ID: account_id,
                CONF_ACCOUNT_NAME: account_info.get("account_name"),
                CONF_ACCOUNT_EMAIL: account_info.get("account_email"),
            }
        )
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            unique_id=account_id,
            version=2,
        )
    else:
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Google Antigravity Usage from a config entry."""
    session = aiohttp_client.async_get_clientsession(hass)
    token = entry.data[CONF_TOKEN]

    try:
        implementations = await config_entry_oauth2_flow.async_get_implementations(hass, DOMAIN)
    except ImplementationUnavailableError:
        implementations = {}
    implementation_domain = entry.data.get(CONF_AUTH_IMPLEMENTATION)
    implementation = implementations.get(implementation_domain) if implementation_domain else None
    if implementation is None and len(implementations) == 1:
        implementation = next(iter(implementations.values()))
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_AUTH_IMPLEMENTATION: implementation.domain},
        )

    @callback
    def _on_token_refreshed(
        new_access_token: str,
        new_refresh_token: str | None,
        expires_in: int | None,
    ) -> None:
        """Persist refreshed OAuth credentials."""
        _LOGGER.debug("Persisting refreshed access token for entry %s", entry.entry_id)
        raw_val = entry.data.get(CONF_TOKEN, "")
        data = {**entry.data, CONF_TOKEN: new_access_token}
        if new_refresh_token:
            data[CONF_REFRESH_TOKEN] = new_refresh_token
        if expires_in:
            data[CONF_EXPIRES_AT] = time.time() + expires_in
        if isinstance(raw_val, str) and raw_val.strip().startswith("{"):
            try:
                parsed = json.loads(raw_val)
                if "token" in parsed and isinstance(parsed["token"], dict):
                    parsed["token"]["access_token"] = new_access_token
                    if new_refresh_token:
                        parsed["token"]["refresh_token"] = new_refresh_token
                    data[CONF_TOKEN] = json.dumps(parsed)
            except json.JSONDecodeError:
                _LOGGER.debug("Stored Antigravity token JSON could not be updated")
        hass.config_entries.async_update_entry(entry, data=data)

    client = GoogleAntigravityUsageApiClient(
        session=session,
        token=token,
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        client_id=getattr(implementation, "client_id", None),
        client_secret=getattr(implementation, "client_secret", None),
        on_token_refreshed=_on_token_refreshed,
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = GoogleAntigravityUsageCoordinator(
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
    coordinator: GoogleAntigravityUsageCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator.update_interval = timedelta(seconds=interval)
