"""Constants for Google Gemini Usage integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "gemini_usage"

# Endpoints
QUOTA_API_URL = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
CODE_ASSIST_URL = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
USER_INFO_URL = "https://cloudcode-pa.googleapis.com/v1internal:fetchUserInfo"

# Configuration
CONF_TOKEN = "token"
CONF_ACCOUNT_ID = "account_id"
CONF_ACCOUNT_NAME = "account_name"
CONF_TIER = "tier"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 300  # seconds
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 3600

# Known Bucket Identifiers
BUCKET_GEMINI_5H = "gemini-5h"
BUCKET_GEMINI_WEEKLY = "gemini-weekly"
BUCKET_3P_5H = "3p-5h"
BUCKET_3P_WEEKLY = "3p-weekly"

# Windows in seconds
WINDOW_5H_SECONDS = 5 * 3600  # 18,000s
WINDOW_WEEKLY_SECONDS = 7 * 24 * 3600  # 604,800s

RESET_TIME_JITTER_TOLERANCE = timedelta(seconds=61)
RESET_TIME_JITTER_CONFIRMATIONS = 2
