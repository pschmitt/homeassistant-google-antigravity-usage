# Google Antigravity Usage - Home Assistant Integration

A custom Home Assistant integration that monitors your Google Antigravity subscription quotas and rate limits.

## Sensors

- **Gemini Session Usage** - Current 5-hour session utilization for first-party Gemini models (%)
- **Gemini Session Remaining** - Remaining 5-hour quota (%)
- **Gemini Session Reset Time** - When the 5-hour session limit resets
- **Gemini Weekly Usage** - Current 7-day utilization (%)
- **Gemini Weekly Remaining** - Remaining 7-day quota (%)
- **Gemini Weekly Usage Pace** - Utilization vs time-elapsed pace (%)
- **Gemini Weekly Reset Time** - When the weekly limit resets
- **3P Models Session / Weekly Usage** - Utilization for Claude & GPT models available under your plan
- **Plan Tier** - Subscription tier (e.g. *Antigravity*, *AI Pro*, *AI Ultra*)

## Installation

### HACS
1. Add this repository to HACS as a custom repository (Integration).
2. Install **Google Antigravity Usage**.
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services > Add Integration > Google Antigravity Usage**.

### Manual
1. Copy `custom_components/google_antigravity_usage/` into `/config/custom_components/google_antigravity_usage/`.
2. Restart Home Assistant.
3. Add the integration via the UI.

## Setup

Before adding the integration, create a **Google Antigravity Usage** application
credential under **Settings > Devices & services > Application credentials**.
Enter the OAuth client ID and secret from your Google Cloud project there.
Home Assistant stores these credentials in its protected application-credential
store; they are not part of this integration repository.

The setup flow then opens the Google authorization URL used by Antigravity. After
signing in, Google redirects to a localhost URL; paste the complete redirected
URL (or its authorization code) back into Home Assistant. The flow uses PKCE
and requests offline access so the integration can refresh access tokens.

Existing installations can still use the JSON content from
`~/.gemini/antigravity-cli/antigravity-oauth-token` as a legacy fallback.

Multiple Google accounts are supported when the OAuth token exposes the Google
account identity. Entries are deduplicated by Google's stable account subject,
not by the subscription tier.

## License

GNU General Public License v3.0 (GPL-3.0)
