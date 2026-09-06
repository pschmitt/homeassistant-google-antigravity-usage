"""Base entity for Google Gemini Usage."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ACCOUNT_EMAIL, CONF_ACCOUNT_NAME, DOMAIN
from .coordinator import GeminiUsageCoordinator


class GeminiUsageEntity(CoordinatorEntity[GeminiUsageCoordinator]):
    """Base entity for Gemini Usage integration."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GeminiUsageCoordinator) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        tier = coordinator.data.get("tier", "Antigravity")
        account_name = entry.data.get(CONF_ACCOUNT_NAME)
        account_email = entry.data.get(CONF_ACCOUNT_EMAIL)
        device_name_parts = ["Google Gemini"]
        account_label = account_name or account_email
        if account_label:
            device_name_parts.append(f"({account_label}")
            if account_email and account_email != account_label:
                device_name_parts.append(f"- {account_email})")
            else:
                device_name_parts[-1] += ")"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=" ".join(device_name_parts),
            entry_type=DeviceEntryType.SERVICE,
            model=f"Gemini ({tier})",
            sw_version=tier,
        )
