"""Exceptions for Google Antigravity Usage integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class GoogleAntigravityUsageError(HomeAssistantError):
    """Base exception for Antigravity Usage."""


class GoogleAntigravityUsageAuthenticationError(GoogleAntigravityUsageError):
    """Exception raised when authentication fails (401/403)."""


class GoogleAntigravityUsageApiError(GoogleAntigravityUsageError):
    """Exception raised when an API error occurs."""
