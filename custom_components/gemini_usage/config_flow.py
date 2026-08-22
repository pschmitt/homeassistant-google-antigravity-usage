"""Config flow for Google Gemini Usage."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import GeminiUsageApiClient
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TIER,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .exceptions import GeminiUsageApiError, GeminiUsageAuthenticationError

_LOGGER = logging.getLogger(__name__)


async def _validate_input(hass: Any, token: str) -> dict[str, Any]:
    """Validate token and fetch info."""
    session = async_get_clientsession(hass)
    client = GeminiUsageApiClient(session=session, token=token)
    info = await client.async_validate()
    tier = info.get("tier", "Antigravity")
    return {
        "title": f"Google Gemini ({tier})",
        "unique_id": f"gemini_usage_{tier.lower().replace(' ', '_')}",
        "tier": tier,
    }


class GeminiUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Google Gemini Usage."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GeminiUsageOptionsFlow:
        """Return the options flow."""
        return GeminiUsageOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user step: enter OAuth / Antigravity token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input.get(CONF_TOKEN, "").strip()
            if not token:
                errors[CONF_TOKEN] = "missing_token"
            else:
                try:
                    info = await _validate_input(self.hass, token)
                except GeminiUsageAuthenticationError:
                    errors["base"] = "invalid_auth"
                except GeminiUsageApiError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected exception validating Gemini Usage config")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(info["unique_id"])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=info["title"],
                        data={
                            CONF_TOKEN: token,
                            CONF_TIER: info["tier"],
                        },
                        options={
                            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth with a fresh token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input.get(CONF_TOKEN, "").strip()
            try:
                info = await _validate_input(self.hass, token)
            except GeminiUsageAuthenticationError:
                errors["base"] = "invalid_auth"
            except GeminiUsageApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error in Gemini Usage reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_TOKEN: token,
                        CONF_TIER: info["tier"],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )


class GeminiUsageOptionsFlow(OptionsFlow):
    """Handle options for Google Gemini Usage."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            mode=NumberSelectorMode.BOX,
                            step=60,
                        )
                    ),
                }
            ),
        )
