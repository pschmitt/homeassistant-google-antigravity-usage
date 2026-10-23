"""Sensor platform for Google Antigravity Usage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import GoogleAntigravityUsageCoordinator
from .entity import GoogleAntigravityUsageEntity


@dataclass(frozen=True, kw_only=True)
class AntigravityBucketSensorDescription(SensorEntityDescription):
    """Describe a quota bucket sensor."""

    bucket_key: str
    metric: str


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Antigravity Usage sensors from a config entry."""
    coordinator: GoogleAntigravityUsageCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        "coordinator"
    ]
    known_entities: set[str] = set()

    @callback
    def async_add_missing_entities() -> None:
        new_entities: list[SensorEntity] = []

        tier_unique_id = f"{config_entry.entry_id}_tier"
        if tier_unique_id not in known_entities:
            known_entities.add(tier_unique_id)
            new_entities.append(AntigravityTierSensor(coordinator, tier_unique_id))

        buckets = (coordinator.data or {}).get("buckets")
        if isinstance(buckets, dict):
            for bucket_key, bucket_data in buckets.items():
                for desc in _build_descriptions(bucket_key, bucket_data):
                    unique_id = f"{config_entry.entry_id}_{bucket_key}_{desc.metric}"
                    if unique_id in known_entities:
                        continue
                    known_entities.add(unique_id)
                    if desc.metric == "reset_time":
                        new_entities.append(
                            AntigravityResetTimestampSensor(
                                coordinator=coordinator,
                                description=desc,
                                unique_id=unique_id,
                            )
                        )
                    else:
                        new_entities.append(
                            AntigravityBucketMetricSensor(
                                coordinator=coordinator,
                                description=desc,
                                unique_id=unique_id,
                            )
                        )

        if new_entities:
            async_add_entities(new_entities)

    async_add_missing_entities()
    config_entry.async_on_unload(coordinator.async_add_listener(async_add_missing_entities))


def _build_descriptions(
    bucket_key: str, bucket_data: dict[str, Any]
) -> list[AntigravityBucketSensorDescription]:
    """Build sensor descriptions for a quota bucket."""
    group_name = bucket_data.get("group_name", "")
    window = bucket_data.get("window", "")

    prefix = group_name if group_name else "Antigravity"
    if "gemini" in bucket_key:
        prefix = "Gemini"
    elif "3p" in bucket_key:
        prefix = "3P Models"

    window_label = (
        "Session" if window == "5h" else "Weekly" if window == "weekly" else window.title()
    )

    descriptions = [
        AntigravityBucketSensorDescription(
            key=f"{bucket_key}_used",
            bucket_key=bucket_key,
            metric="percent_used",
            name=f"{prefix} {window_label} Usage",
            native_unit_of_measurement="%",
            icon="mdi:timer-sand" if window == "5h" else "mdi:calendar-week",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        AntigravityBucketSensorDescription(
            key=f"{bucket_key}_remaining",
            bucket_key=bucket_key,
            metric="percent_remaining",
            name=f"{prefix} {window_label} Remaining",
            native_unit_of_measurement="%",
            icon="mdi:battery-high",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        AntigravityBucketSensorDescription(
            key=f"{bucket_key}_reset_time",
            bucket_key=bucket_key,
            metric="reset_time",
            name=f"{prefix} {window_label} Reset Time",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:timer-refresh" if window == "5h" else "mdi:calendar-clock",
        ),
    ]

    if window == "weekly":
        descriptions.append(
            AntigravityBucketSensorDescription(
                key=f"{bucket_key}_pace",
                bucket_key=bucket_key,
                metric="pace",
                name=f"{prefix} Weekly Usage Pace",
                native_unit_of_measurement="%",
                icon="mdi:speedometer",
                state_class=SensorStateClass.MEASUREMENT,
            )
        )

    return descriptions


class AntigravityTierSensor(GoogleAntigravityUsageEntity, SensorEntity):
    """Sensor for Google Antigravity tier / plan."""

    def __init__(self, coordinator: GoogleAntigravityUsageCoordinator, unique_id: str) -> None:
        """Initialize tier sensor."""
        super().__init__(coordinator)
        self._attr_name = "Plan Tier"
        self._attr_unique_id = unique_id
        self._attr_icon = "mdi:shield-star"

    @property
    def native_value(self) -> str:
        """Return the subscription tier."""
        return str((self.coordinator.data or {}).get("tier", "Antigravity"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes."""
        return {
            "tier_id": (self.coordinator.data or {}).get("tier_id"),
            "project_id": (self.coordinator.data or {}).get("project_id"),
            "region": (self.coordinator.data or {}).get("region"),
        }


class AntigravityBucketMetricSensor(GoogleAntigravityUsageEntity, SensorEntity):
    """Sensor for a numerical metric within a quota bucket."""

    entity_description: AntigravityBucketSensorDescription

    def __init__(
        self,
        coordinator: GoogleAntigravityUsageCoordinator,
        description: AntigravityBucketSensorDescription,
        unique_id: str,
    ) -> None:
        """Initialize metric sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = unique_id

    @property
    def _bucket(self) -> dict[str, Any] | None:
        """Get bucket data."""
        buckets = (self.coordinator.data or {}).get("buckets", {})
        if isinstance(buckets, dict):
            return buckets.get(self.entity_description.bucket_key)
        return None

    @property
    def available(self) -> bool:
        """Return availability."""
        return self.coordinator.last_update_success and self._bucket is not None

    @property
    def native_value(self) -> float | None:
        """Return the metric value."""
        bucket = self._bucket
        if not bucket:
            return None
        val = bucket.get(self.entity_description.metric)
        if isinstance(val, (int, float)):
            return float(val)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        bucket = self._bucket
        if not bucket:
            return {}
        return {
            "bucket_id": bucket.get("bucket_id"),
            "group_name": bucket.get("group_name"),
            "window": bucket.get("window"),
            "reset_time": bucket.get("reset_time"),
            "description": bucket.get("description"),
            "remaining_fraction": bucket.get("remaining_fraction"),
        }


class AntigravityResetTimestampSensor(GoogleAntigravityUsageEntity, SensorEntity):
    """Sensor for a reset timestamp within a quota bucket."""

    entity_description: AntigravityBucketSensorDescription

    def __init__(
        self,
        coordinator: GoogleAntigravityUsageCoordinator,
        description: AntigravityBucketSensorDescription,
        unique_id: str,
    ) -> None:
        """Initialize reset timestamp sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = unique_id

    @property
    def _bucket(self) -> dict[str, Any] | None:
        """Get bucket data."""
        buckets = (self.coordinator.data or {}).get("buckets", {})
        if isinstance(buckets, dict):
            return buckets.get(self.entity_description.bucket_key)
        return None

    @property
    def available(self) -> bool:
        """Return availability."""
        return self.coordinator.last_update_success and self._bucket is not None

    @property
    def native_value(self) -> datetime | None:
        """Return the reset timestamp."""
        bucket = self._bucket
        if not bucket:
            return None
        iso_str = bucket.get("reset_time")
        if not isinstance(iso_str, str):
            return None
        return dt_util.parse_datetime(iso_str)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        bucket = self._bucket
        if not bucket:
            return {}
        return {
            "bucket_id": bucket.get("bucket_id"),
            "group_name": bucket.get("group_name"),
            "window": bucket.get("window"),
            "description": bucket.get("description"),
        }
