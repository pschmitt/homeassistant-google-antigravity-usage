"""Constants for Google Antigravity Usage integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "google_antigravity_usage"

# Endpoints
# Antigravity uses the daily quota backend. The non-daily endpoint can return
# a different quota snapshot for the same account.
CLOUD_CODE_API_BASE = "https://daily-cloudcode-pa.googleapis.com/v1internal"
QUOTA_API_URL = f"{CLOUD_CODE_API_BASE}:retrieveUserQuotaSummary"
CODE_ASSIST_URL = f"{CLOUD_CODE_API_BASE}:loadCodeAssist"
USER_INFO_URL = f"{CLOUD_CODE_API_BASE}:fetchUserInfo"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo?alt=json"
OAUTH2_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_REDIRECT_URI = "http://localhost:51121/oauth-callback"

# These are the credentials currently used by the Antigravity CLI token format
# accepted by this integration.
OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/cclog "
    "https://www.googleapis.com/auth/experimentsandconfigs"
)

# Configuration
CONF_AUTH_IMPLEMENTATION = "auth_implementation"
CONF_TOKEN = "token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"
CONF_ACCOUNT_ID = "account_id"
CONF_ACCOUNT_NAME = "account_name"
CONF_ACCOUNT_EMAIL = "account_email"
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
