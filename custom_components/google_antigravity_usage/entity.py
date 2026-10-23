"""Base entity for Google Antigravity Usage."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ACCOUNT_EMAIL, CONF_ACCOUNT_NAME, DOMAIN
from .coordinator import GoogleAntigravityUsageCoordinator


class GoogleAntigravityUsageEntity(CoordinatorEntity[GoogleAntigravityUsageCoordinator]):
    """Base entity for Antigravity Usage integration."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GoogleAntigravityUsageCoordinator) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        tier = (coordinator.data or {}).get("tier", "Antigravity")
        account_name = entry.data.get(CONF_ACCOUNT_NAME)
        account_email = entry.data.get(CONF_ACCOUNT_EMAIL)
        device_name_parts = ["Google Antigravity"]
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
            model=str(tier),
            sw_version=tier,
        )
