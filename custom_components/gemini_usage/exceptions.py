"""Exceptions for Google Gemini Usage integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class GeminiUsageError(HomeAssistantError):
    """Base exception for Gemini Usage."""


class GeminiUsageAuthenticationError(GeminiUsageError):
    """Exception raised when authentication fails (401/403)."""


class GeminiUsageApiError(GeminiUsageError):
    """Exception raised when an API error occurs."""
