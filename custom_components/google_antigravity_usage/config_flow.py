"""Config flow for Google Antigravity Usage."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    ImplementationUnavailableError,
)
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import slugify

from .api import GoogleAntigravityUsageApiClient
from .const import (
    CONF_ACCOUNT_EMAIL,
    CONF_ACCOUNT_ID,
    CONF_ACCOUNT_NAME,
    CONF_AUTH_IMPLEMENTATION,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TIER,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    OAUTH2_TOKEN_URL,
    OAUTH_AUTHORIZE_URL,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPES,
)
from .exceptions import GoogleAntigravityUsageApiError, GoogleAntigravityUsageAuthenticationError

_LOGGER = logging.getLogger(__name__)


def _generate_pkce() -> tuple[str, str]:
    """Generate a PKCE verifier and S256 challenge."""
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def _validate_input(
    hass: Any, token: str, refresh_token: str | None = None
) -> dict[str, Any]:
    """Validate a token and fetch account and plan information."""
    session = async_get_clientsession(hass)
    client = GoogleAntigravityUsageApiClient(
        session=session, token=token, refresh_token=refresh_token
    )
    info = await client.async_validate()

    account_info: dict[str, Any] = {}
    try:
        account_info = await client.async_fetch_account_info()
    except (GoogleAntigravityUsageApiError, GoogleAntigravityUsageAuthenticationError) as err:
        # Older Antigravity tokens may not include userinfo scopes. They remain
        # valid for quota polling, so retain the tier fallback for those tokens.
        _LOGGER.debug("Could not identify Google account during setup: %s", err)

    tier = str(info.get("tier", "Antigravity"))
    account_id = account_info.get("account_id")
    account_name = account_info.get("account_name")
    account_email = account_info.get("account_email")
    return {
        "access_token": client.access_token,
        "refresh_token": client.refresh_token,
        "account_id": account_id,
        "account_name": account_name,
        "account_email": account_email,
        "title": _build_title(tier, account_name, account_email),
        "unique_id": account_id or f"{DOMAIN}_tier_{slugify(tier)}",
        "tier": tier,
    }


def _build_title(tier: str, account_name: str | None, account_email: str | None) -> str:
    """Build a useful config-entry title."""
    account = account_name or account_email
    if account and account != tier:
        return f"Google Antigravity ({account} - {tier})"
    return f"Google Antigravity ({tier})"


class GoogleAntigravityUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Google Antigravity Usage."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._pkce_verifier: str | None = None
        self._state: str | None = None
        self._oauth_url: str | None = None
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._auth_implementation: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GoogleAntigravityUsageOptionsFlow:
        """Return the options flow."""
        return GoogleAntigravityUsageOptionsFlow()

    async def _async_prepare_oauth(self, existing_entry: ConfigEntry | None) -> bool:
        """Load the OAuth client credentials configured in Home Assistant."""
        try:
            implementations = await config_entry_oauth2_flow.async_get_implementations(
                self.hass, DOMAIN
            )
        except ImplementationUnavailableError:
            return False

        implementation_domain = (
            existing_entry.data.get(CONF_AUTH_IMPLEMENTATION)
            if existing_entry is not None
            else None
        )
        implementation = (
            implementations.get(implementation_domain)
            if implementation_domain
            else None
        )
        if implementation is None and len(implementations) == 1:
            implementation = next(iter(implementations.values()))
        if implementation is None:
            return False

        self._client_id = getattr(implementation, "client_id", None)
        self._client_secret = getattr(implementation, "client_secret", None)
        self._auth_implementation = implementation.domain
        return bool(self._client_id)

    def _async_start_oauth(self) -> None:
        """Create a one-time Google authorization URL."""
        if not self._client_id:
            return
        self._pkce_verifier, challenge = _generate_pkce()
        self._state = secrets.token_urlsafe(32)
        self._oauth_url = f"{OAUTH_AUTHORIZE_URL}?{urlencode({
            'client_id': self._client_id,
            'response_type': 'code',
            'redirect_uri': OAUTH_REDIRECT_URI,
            'scope': OAUTH_SCOPES,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'state': self._state,
            'access_type': 'offline',
            'prompt': 'consent',
        })}"

    @staticmethod
    def _parse_auth_input(auth_input: str) -> tuple[str, str | None]:
        """Extract an authorization code and optional state from pasted input."""
        value = auth_input.strip()
        if value.startswith(("http://", "https://")):
            parsed = urlparse(value)
            query = parse_qs(parsed.query)
            return query.get("code", [""])[0], query.get("state", [None])[0]
        if "#" in value:
            code, state = value.split("#", 1)
            return code, state
        return value, None

    async def _exchange_code(self, auth_input: str) -> dict[str, Any] | None:
        """Exchange a pasted Google authorization code for OAuth tokens."""
        code, returned_state = self._parse_auth_input(auth_input)
        if not code or not self._pkce_verifier:
            return None
        if returned_state and self._state and returned_state != self._state:
            _LOGGER.error("Google OAuth state mismatch - possible CSRF attack")
            return None

        session = async_get_clientsession(self.hass)
        try:
            resp = await session.post(
                OAUTH2_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret or "",
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": OAUTH_REDIRECT_URI,
                    "code_verifier": self._pkce_verifier,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            )
            if not resp.ok:
                _LOGGER.error("Google OAuth code exchange failed (%s)", resp.status)
                return None
            data = await resp.json()
        except (aiohttp.ClientError, TimeoutError, OSError):
            _LOGGER.exception("Google OAuth code exchange request failed")
            return None

        if "access_token" not in data:
            _LOGGER.error("Google OAuth response missing access_token")
            return None
        return data

    async def _async_finish(
        self, token_data: dict[str, Any], existing_entry: ConfigEntry | None = None
    ) -> ConfigFlowResult:
        """Validate OAuth tokens and create or update the config entry."""
        access_token = token_data.get("access_token")
        if not access_token:
            return self.async_abort(reason="oauth_failed")

        info = await _validate_input(
            self.hass, str(access_token), token_data.get("refresh_token")
        )
        expires_in = token_data.get("expires_in")
        data = {
            CONF_TOKEN: info["access_token"],
            CONF_TIER: info["tier"],
            CONF_ACCOUNT_ID: info.get("account_id"),
            CONF_ACCOUNT_NAME: info.get("account_name"),
            CONF_ACCOUNT_EMAIL: info.get("account_email"),
            CONF_REFRESH_TOKEN: info.get("refresh_token"),
        }
        if self._auth_implementation:
            data[CONF_AUTH_IMPLEMENTATION] = self._auth_implementation
        if expires_in:
            data[CONF_EXPIRES_AT] = time.time() + int(expires_in)
        data = {key: value for key, value in data.items() if value is not None}

        if existing_entry is not None:
            if any(
                other.entry_id != existing_entry.entry_id
                and other.unique_id == info["unique_id"]
                for other in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")
            return self.async_update_reload_and_abort(
                existing_entry,
                unique_id=info["unique_id"],
                data_updates=data,
            )

        await self.async_set_unique_id(info["unique_id"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=info["title"], data=data)

    def _existing_entry(self) -> ConfigEntry | None:
        """Return the entry being reauthenticated or reconfigured."""
        if self.source == SOURCE_RECONFIGURE:
            return self._get_reconfigure_entry()
        if self.source == SOURCE_REAUTH:
            return self._get_reauth_entry()
        return None

    async def _async_step_auth(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Handle browser authorization and the legacy token fallback."""
        errors: dict[str, str] = {}
        existing_entry = self._existing_entry()
        if self._oauth_url is None:
            if await self._async_prepare_oauth(existing_entry):
                self._async_start_oauth()

        if user_input is not None:
            auth_code = str(user_input.get("auth_code", "")).strip()
            legacy_token = str(user_input.get(CONF_TOKEN, "")).strip()
            token_data: dict[str, Any] | None = None
            if auth_code:
                if self._oauth_url is None:
                    errors["base"] = "oauth_credentials_missing"
                else:
                    token_data = await self._exchange_code(auth_code)
                if auth_code and token_data is None and "base" not in errors:
                    errors["base"] = "exchange_failed"
            elif legacy_token:
                token_data = {"access_token": legacy_token}
            else:
                errors["base"] = "missing_credentials"

            if token_data is not None:
                try:
                    return await self._async_finish(token_data, existing_entry)
                except GoogleAntigravityUsageAuthenticationError:
                    errors["base"] = "invalid_auth"
                except GoogleAntigravityUsageApiError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception validating Antigravity Usage config")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Optional("auth_code"): str,
                    vol.Optional(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            description_placeholders={
                "url": self._oauth_url or "https://accounts.google.com/",
                "name": existing_entry.title if existing_entry else "Google Antigravity",
            },
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        return await self._async_step_auth("user", user_input)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication after an authentication failure."""
        return await self._async_step_auth("reauth_confirm", None)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the reauthentication form."""
        return await self._async_step_auth("reauth_confirm", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user-requested account changes."""
        return await self._async_step_auth("reauth_confirm", user_input)


class GoogleAntigravityUsageOptionsFlow(OptionsFlow):
    """Handle options for Google Antigravity Usage."""

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
