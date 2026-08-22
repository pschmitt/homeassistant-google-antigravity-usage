"""Base entity for Google Gemini Usage."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GeminiUsageCoordinator


class GeminiUsageEntity(CoordinatorEntity[GeminiUsageCoordinator]):
    """Base entity for Gemini Usage integration."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GeminiUsageCoordinator) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        tier = coordinator.data.get("tier", "Antigravity")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Google",
            model=f"Gemini ({tier})",
            sw_version=tier,
        )
