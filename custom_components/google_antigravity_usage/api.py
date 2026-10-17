"""API client for Google Antigravity Usage."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
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
            except (TypeError, ValueError):
                return None

    def slugify(value: str, separator: str = "_") -> str:  # type: ignore[no-redef]
        value = re.sub(r"[^\w\s-]", "", value.lower()).strip()
        return re.sub(r"[-\s]+", separator, value)


import asyncio
from collections.abc import Callable

from .const import (
    CLOUD_CODE_FALLBACK_API_BASE,
    CODE_ASSIST_URL,
    GOOGLE_USERINFO_URL,
    OAUTH2_TOKEN_URL,
    QUOTA_API_URL,
    USER_INFO_URL,
    WINDOW_5H_SECONDS,
    WINDOW_WEEKLY_SECONDS,
)
from .exceptions import (
    GoogleAntigravityUsageApiError,
    GoogleAntigravityUsageAuthenticationError,
)

_LOGGER = logging.getLogger(__name__)


def extract_tokens(raw_token: str) -> tuple[str, str | None]:
    """Extract (access_token, refresh_token) from raw token string or JSON."""
    raw = raw_token.strip()
    if raw.startswith("{") and raw.endswith("}"):
        try:
            data = json.loads(raw)
            if "token" in data and isinstance(data["token"], dict):
                access_token = str(
                    data["token"].get("access_token") or data["token"].get("accessToken") or ""
                )
                refresh_token = data["token"].get("refresh_token")
                return access_token or raw, str(refresh_token) if refresh_token else None
            if "access_token" in data:
                refresh_token = data.get("refresh_token")
                return str(data["access_token"]), str(refresh_token) if refresh_token else None
        except json.JSONDecodeError:
            pass
    return raw, None


def extract_bearer_token(raw_token: str) -> str:
    """Extract raw bearer token from string or JSON."""
    access_tok, _ = extract_tokens(raw_token)
    return access_tok


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


class GoogleAntigravityUsageApiClient:
    """API client for querying Google Antigravity / Cloud Code Quota Summary."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        on_token_refreshed: Callable[[str, str | None, int | None], Any] | None = None,
    ) -> None:
        """Initialize API client."""
        self._session = session
        self._raw_token = token
        access_tok, ref_tok = extract_tokens(token)
        self._access_token = access_tok
        self._refresh_token = refresh_token or ref_tok
        self._client_id = client_id
        self._client_secret = client_secret
        self.on_token_refreshed = on_token_refreshed

    @property
    def bearer_token(self) -> str:
        """Get the extracted bearer token."""
        return self._access_token or extract_bearer_token(self._raw_token)

    @property
    def access_token(self) -> str:
        """Return the current access token."""
        return self._access_token

    @property
    def refresh_token(self) -> str | None:
        """Get the refresh token if available."""
        return self._refresh_token

    def update_token(self, token: str, refresh_token: str | None = None) -> None:
        """Update the stored token."""
        self._raw_token = token
        access_tok, ref_tok = extract_tokens(token)
        self._access_token = access_tok
        if refresh_token:
            self._refresh_token = refresh_token
        elif ref_tok:
            self._refresh_token = ref_tok

    async def async_refresh_token(self) -> bool:
        """Attempt to refresh OAuth access token using refresh_token."""
        if not self._refresh_token:
            _LOGGER.debug("No refresh token available to refresh access token")
            return False
        if not self._client_id:
            _LOGGER.error("No OAuth client credentials available to refresh access token")
            return False

        _LOGGER.info("Refreshing expired Google Antigravity OAuth access token...")
        payload = {
            "client_id": self._client_id,
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }
        if self._client_secret:
            payload["client_secret"] = self._client_secret
        try:
            resp = await self._session.post(
                OAUTH2_TOKEN_URL,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            )
            if not resp.ok:
                err_text = await resp.text()
                _LOGGER.error(
                    "Failed to refresh Google OAuth token (%s): %s", resp.status, err_text
                )
                return False

            res_json = await resp.json()
            new_access_token = res_json.get("access_token")
            if not new_access_token:
                _LOGGER.error("No access_token returned in token refresh response: %s", res_json)
                return False

            new_refresh_token = res_json.get("refresh_token")
            if new_refresh_token:
                self._refresh_token = str(new_refresh_token)
            self._access_token = str(new_access_token)
            expires_in = res_json.get("expires_in")
            try:
                expires_in = int(expires_in) if expires_in is not None else None
            except (TypeError, ValueError):
                expires_in = None
            _LOGGER.info("Successfully refreshed Google Antigravity OAuth access token!")

            if self.on_token_refreshed:
                try:
                    res = self.on_token_refreshed(
                        self._access_token, self._refresh_token, expires_in
                    )
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Error in on_token_refreshed callback: %s", err)

            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Exception occurred while refreshing Google OAuth token: %s", err)
            return False

    async def async_post_json(self, url: str, retry_on_auth_fail: bool = True) -> dict[str, Any]:
        """Perform an authorized POST request with auto-refresh on 401."""
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
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise GoogleAntigravityUsageApiError(f"Network connection error: {err}") from err

        if resp.status in (401, 403):
            if retry_on_auth_fail and self._refresh_token:
                _LOGGER.debug("Received %s, attempting OAuth token refresh...", resp.status)
                refreshed = await self.async_refresh_token()
                if refreshed:
                    return await self.async_post_json(url, retry_on_auth_fail=False)
            raise GoogleAntigravityUsageAuthenticationError(
                f"Authentication failed ({resp.status}): Invalid or expired token"
            )

        if not resp.ok:
            body = await resp.text()
            raise GoogleAntigravityUsageApiError(f"API request failed ({resp.status}): {body}")

        try:
            return await resp.json()
        except ValueError as err:
            raise GoogleAntigravityUsageApiError("Invalid JSON response from server") from err

    async def async_validate(self) -> dict[str, Any]:
        """Validate credentials and return basic profile info."""
        quota_data = await self.async_post_json(QUOTA_API_URL)
        tier_name = "Antigravity"
        try:
            tier_data = await self.async_post_json(CODE_ASSIST_URL)
            tier_info = tier_data.get("currentTier", {})
            if isinstance(tier_info, dict) and tier_info.get("name"):
                tier_name = tier_info["name"]
        except GoogleAntigravityUsageAuthenticationError:
            raise
        except GoogleAntigravityUsageApiError:
            pass

        return {
            "title": f"Google Antigravity ({tier_name})",
            "tier": tier_name,
            "quota_summary": quota_data,
        }

    async def async_fetch_account_info(self, retry_on_auth_fail: bool = True) -> dict[str, Any]:
        """Fetch the Google account identity associated with the token."""
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        try:
            resp = await self._session.get(
                GOOGLE_USERINFO_URL,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise GoogleAntigravityUsageApiError(f"Network connection error: {err}") from err

        if resp.status in (401, 403):
            if retry_on_auth_fail and self._refresh_token and await self.async_refresh_token():
                return await self.async_fetch_account_info(retry_on_auth_fail=False)
            raise GoogleAntigravityUsageAuthenticationError(
                f"Account identity request failed ({resp.status})"
            )

        if not resp.ok:
            body = await resp.text()
            raise GoogleAntigravityUsageApiError(
                f"Account identity request failed ({resp.status}): {body}"
            )

        try:
            data = await resp.json()
        except ValueError as err:
            raise GoogleAntigravityUsageApiError("Invalid account identity response") from err

        account_id = data.get("sub") or data.get("id")
        if not account_id:
            raise GoogleAntigravityUsageApiError("Google account identity response missing subject")
        return {
            "account_id": str(account_id),
            "account_name": data.get("name") or data.get("email"),
            "account_email": data.get("email"),
        }

    async def async_fetch_usage(self) -> dict[str, Any]:
        """Fetch all usage and quota data."""
        quota_data = await self.async_post_json(QUOTA_API_URL)

        # Ensure both Gemini and 3P quota groups are fetched if available.
        # If one endpoint only returns a subset of quota groups, merge with the fallback.
        groups = quota_data.get("groups")
        if isinstance(groups, list):
            has_gemini = any(
                "gemini" in str(b.get("bucketId", ""))
                for g in groups
                if isinstance(g, dict)
                for b in (g.get("buckets") or [])
                if isinstance(b, dict)
            )
            has_3p = any(
                "3p" in str(b.get("bucketId", ""))
                for g in groups
                if isinstance(g, dict)
                for b in (g.get("buckets") or [])
                if isinstance(b, dict)
            )
            if not (has_gemini and has_3p):
                fallback_url = f"{CLOUD_CODE_FALLBACK_API_BASE}:retrieveUserQuotaSummary"
                try:
                    fallback_data = await self.async_post_json(fallback_url)
                    fallback_groups = fallback_data.get("groups") or []
                    existing_bucket_ids = {
                        b.get("bucketId")
                        for g in groups
                        if isinstance(g, dict)
                        for b in (g.get("buckets") or [])
                        if isinstance(b, dict) and b.get("bucketId")
                    }
                    for fg in fallback_groups:
                        if not isinstance(fg, dict):
                            continue
                        new_buckets = [
                            b
                            for b in (fg.get("buckets") or [])
                            if isinstance(b, dict) and b.get("bucketId") not in existing_bucket_ids
                        ]
                        if new_buckets:
                            fg_copy = dict(fg)
                            fg_copy["buckets"] = new_buckets
                            groups.append(fg_copy)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Could not fetch fallback quota summary: %s", err)

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
        except GoogleAntigravityUsageAuthenticationError:
            raise
        except GoogleAntigravityUsageApiError as err:
            _LOGGER.debug("Could not fetch tier info: %s", err)

        try:
            user_info = await self.async_post_json(USER_INFO_URL)
            region_code = user_info.get("regionCode")
        except GoogleAntigravityUsageAuthenticationError:
            raise
        except GoogleAntigravityUsageApiError as err:
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
