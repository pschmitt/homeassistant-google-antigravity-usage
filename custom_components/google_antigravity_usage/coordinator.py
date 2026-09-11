"""DataUpdateCoordinator for Google Antigravity Usage."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import GoogleAntigravityUsageApiClient
from .const import (
    DOMAIN,
    RESET_TIME_JITTER_CONFIRMATIONS,
    RESET_TIME_JITTER_TOLERANCE,
)
from .exceptions import GoogleAntigravityUsageApiError, GoogleAntigravityUsageAuthenticationError

_LOGGER = logging.getLogger(__name__)


class GoogleAntigravityUsageCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch Antigravity usage data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GoogleAntigravityUsageApiClient,
        update_interval_seconds: int,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self._pending_reset_time_updates: dict[str, tuple[str, int]] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_seconds),
            config_entry=entry,
            always_update=False,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch usage data from the API."""
        try:
            data = await self.client.async_fetch_usage()
        except GoogleAntigravityUsageAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GoogleAntigravityUsageApiError as err:
            raise UpdateFailed(str(err)) from err

        return self._stabilize_reset_times(data)

    def _stabilize_reset_times(self, current: dict[str, Any]) -> dict[str, Any]:
        """Suppress transient minute-level reset-time jitter."""
        if not self.data:
            self._pending_reset_time_updates.clear()
            return current

        prev_buckets = self.data.get("buckets", {})
        curr_buckets = current.get("buckets", {})
        if not isinstance(prev_buckets, dict) or not isinstance(curr_buckets, dict):
            return current

        stabilized = dict(current)
        stabilized_buckets = dict(curr_buckets)

        for key, bucket in curr_buckets.items():
            prev_bucket = prev_buckets.get(key)
            if not prev_bucket:
                self._pending_reset_time_updates.pop(key, None)
                continue

            prev_time = prev_bucket.get("reset_time")
            curr_time = bucket.get("reset_time")

            if not prev_time or not curr_time:
                self._pending_reset_time_updates.pop(key, None)
                continue

            if prev_time == curr_time:
                self._pending_reset_time_updates.pop(key, None)
                continue

            prev_dt = dt_util.parse_datetime(prev_time)
            curr_dt = dt_util.parse_datetime(curr_time)
            if prev_dt is None or curr_dt is None:
                self._pending_reset_time_updates.pop(key, None)
                continue

            if abs(curr_dt - prev_dt) > RESET_TIME_JITTER_TOLERANCE:
                self._pending_reset_time_updates.pop(key, None)
                continue

            pending_val, pending_count = self._pending_reset_time_updates.get(key, (None, 0))
            if pending_val == curr_time:
                pending_count += 1
            else:
                pending_val = curr_time
                pending_count = 1

            if pending_count >= RESET_TIME_JITTER_CONFIRMATIONS:
                self._pending_reset_time_updates.pop(key, None)
                continue

            self._pending_reset_time_updates[key] = (pending_val, pending_count)
            bucket_copy = dict(bucket)
            bucket_copy["reset_time"] = prev_time
            stabilized_buckets[key] = bucket_copy

        stabilized["buckets"] = stabilized_buckets
        return stabilized
