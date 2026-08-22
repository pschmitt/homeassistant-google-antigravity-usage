"""API client for Google Gemini Usage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from typing import Any
import aiohttp

try:
    from homeassistant.util import dt as dt_util
    from homeassistant.util import slugify
except ImportError:
    import re
    class dt_util:  # type: ignore[no-redef]
        @staticmethod
        def parse_datetime(val: str) -> datetime | None:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                return None
    def slugify(value: str, separator: str = "_") -> str:  # type: ignore[no-redef]
        value = re.sub(r"[^\w\s-]", "", value.lower()).strip()
        return re.sub(r"[-\s]+", separator, value)

from .const import (
    CODE_ASSIST_URL,
    QUOTA_API_URL,
    USER_INFO_URL,
    WINDOW_5H_SECONDS,
    WINDOW_WEEKLY_SECONDS,
)
from .exceptions import GeminiUsageApiError, GeminiUsageAuthenticationError

_LOGGER = logging.getLogger(__name__)


def extract_bearer_token(raw_token: str) -> str:
    """Extract raw bearer token from string or JSON."""
    raw = raw_token.strip()
    if raw.startswith("{") and raw.endswith("}"):
        try:
            data = json.loads(raw)
            if "token" in data and isinstance(data["token"], dict):
                return str(
                    data["token"].get("access_token")
                    or data["token"].get("accessToken")
                    or raw
                )
            if "access_token" in data:
                return str(data["access_token"])
        except json.JSONDecodeError:
            pass
    return raw


def _round_to_minute(iso_str: str | None) -> str | None:
    """Round an ISO timestamp to the nearest minute to suppress sub-minute API jitter."""
    if not iso_str:
        return iso_str
    try:
        dt = dt_util.parse_datetime(iso_str)
        if dt is None:
            return iso_str
        remainder = dt.second + dt.microsecond / 1_000_000
        dt = dt.replace(second=0, microsecond=0)
        if remainder >= 30:
            dt += timedelta(minutes=1)
        return dt.isoformat()
    except (ValueError, TypeError):
        return iso_str


class GeminiUsageApiClient:
    """API client for querying Google Gemini / Cloud Code Quota Summary."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        """Initialize API client."""
        self._session = session
        self._raw_token = token

    @property
    def bearer_token(self) -> str:
        """Get the extracted bearer token."""
        return extract_bearer_token(self._raw_token)

    def update_token(self, token: str) -> None:
        """Update the stored token."""
        self._raw_token = token

    async def async_post_json(self, url: str) -> dict[str, Any]:
        """Perform an authorized POST request."""
        token = self.bearer_token
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity-cli/1.0",
        }
        try:
            resp = await self._session.post(
                url,
                json={},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        except aiohttp.ClientError as err:
            raise GeminiUsageApiError(f"Network connection error: {err}") from err

        if resp.status in (401, 403):
            raise GeminiUsageAuthenticationError(
                f"Authentication failed ({resp.status}): Invalid or expired token"
            )

        if not resp.ok:
            body = await resp.text()
            raise GeminiUsageApiError(f"API request failed ({resp.status}): {body}")

        try:
            return await resp.json()
        except ValueError as err:
            raise GeminiUsageApiError("Invalid JSON response from server") from err

    async def async_validate(self) -> dict[str, Any]:
        """Validate credentials and return basic profile info."""
        quota_data = await self.async_post_json(QUOTA_API_URL)
        tier_name = "Antigravity"
        try:
            tier_data = await self.async_post_json(CODE_ASSIST_URL)
            tier_info = tier_data.get("currentTier", {})
            if isinstance(tier_info, dict) and tier_info.get("name"):
                tier_name = tier_info["name"]
        except Exception:  # noqa: BLE001
            pass

        return {
            "title": f"Google Gemini ({tier_name})",
            "tier": tier_name,
            "quota_summary": quota_data,
        }

    async def async_fetch_usage(self) -> dict[str, Any]:
        """Fetch all usage and quota data."""
        quota_data = await self.async_post_json(QUOTA_API_URL)

        tier_name = "Antigravity"
        tier_id = None
        project_id = None
        region_code = None

        try:
            tier_data = await self.async_post_json(CODE_ASSIST_URL)
            tier_info = tier_data.get("currentTier", {})
            if isinstance(tier_info, dict):
                tier_name = tier_info.get("name", tier_name)
                tier_id = tier_info.get("id")
            project_id = tier_data.get("cloudaicompanionProject")
        except Exception as err:
            _LOGGER.debug("Could not fetch tier info: %s", err)

        try:
            user_info = await self.async_post_json(USER_INFO_URL)
            region_code = user_info.get("regionCode")
        except Exception as err:
            _LOGGER.debug("Could not fetch user info: %s", err)

        return self._parse_payload(
            quota_data=quota_data,
            tier_name=tier_name,
            tier_id=tier_id,
            project_id=project_id,
            region_code=region_code,
        )

    def _parse_payload(
        self,
        quota_data: dict[str, Any],
        tier_name: str,
        tier_id: str | None,
        project_id: str | None,
        region_code: str | None,
    ) -> dict[str, Any]:
        """Parse raw API responses into structured sensor data."""
        now = datetime.now(UTC)
        buckets: dict[str, dict[str, Any]] = {}

        groups = quota_data.get("groups") or []
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_name = group.get("displayName", "Default")
            group_desc = group.get("description")
            raw_buckets = group.get("buckets") or []

            for raw_b in raw_buckets:
                if not isinstance(raw_b, dict):
                    continue
                bucket_id = raw_b.get("bucketId")
                if not bucket_id:
                    continue

                display_name = raw_b.get("displayName", bucket_id)
                window = raw_b.get("window", "")
                reset_time_raw = raw_b.get("resetTime")
                reset_time = _round_to_minute(reset_time_raw)
                rem_fraction = raw_b.get("remainingFraction")

                percent_rem: float | None = None
                percent_used: float | None = None

                if rem_fraction is not None:
                    try:
                        rem_f = float(rem_fraction)
                        percent_rem = round(rem_f * 100, 1)
                        percent_used = round(max(0.0, (1.0 - rem_f) * 100), 1)
                    except (ValueError, TypeError):
                        pass

                window_seconds = None
                pace = None

                if window == "5h":
                    window_seconds = WINDOW_5H_SECONDS
                elif window == "weekly":
                    window_seconds = WINDOW_WEEKLY_SECONDS

                if window_seconds and reset_time_raw and percent_used is not None:
                    try:
                        reset_dt = dt_util.parse_datetime(reset_time_raw)
                        if reset_dt is not None:
                            remaining_secs = (reset_dt - now).total_seconds()
                            elapsed = window_seconds - remaining_secs
                            percent_elapsed = (elapsed / window_seconds) * 100
                            pace = round(percent_used - percent_elapsed, 1)
                    except (ValueError, TypeError):
                        pass

                key = slugify(bucket_id, separator="_")
                buckets[key] = {
                    "bucket_id": bucket_id,
                    "key": key,
                    "display_name": display_name,
                    "group_name": group_name,
                    "group_description": group_desc,
                    "window": window,
                    "window_seconds": window_seconds,
                    "reset_time": reset_time,
                    "reset_time_raw": reset_time_raw,
                    "remaining_fraction": rem_fraction,
                    "percent_remaining": percent_rem,
                    "percent_used": percent_used,
                    "pace": pace,
                    "description": raw_b.get("description"),
                }

        return {
            "tier": tier_name,
            "tier_id": tier_id,
            "project_id": project_id,
            "region": region_code,
            "description": quota_data.get("description"),
            "buckets": buckets,
        }
