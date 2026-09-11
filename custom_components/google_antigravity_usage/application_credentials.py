"""Application credentials platform for Google Antigravity Usage."""

from homeassistant.components.application_credentials import ClientCredential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2Implementation,
    LocalOAuth2ImplementationWithPkce,
)

from .const import OAUTH2_TOKEN_URL, OAUTH_AUTHORIZE_URL


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> AbstractOAuth2Implementation:
    """Return the OAuth implementation backed by Home Assistant credentials."""
    return LocalOAuth2ImplementationWithPkce(
        hass,
        auth_domain,
        credential.client_id,
        OAUTH_AUTHORIZE_URL,
        OAUTH2_TOKEN_URL,
        credential.client_secret,
    )
