# Google Gemini Usage - Home Assistant Integration

A custom Home Assistant integration that monitors your Google Gemini and Antigravity subscription quotas and rate limits.

## Sensors

- **Gemini Session Usage** - Current 5-hour session utilization (%)
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
2. Install **Google Gemini Usage**.
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services > Add Integration > Google Gemini Usage**.

### Manual
1. Copy `custom_components/gemini_usage/` into `/config/custom_components/gemini_usage/`.
2. Restart Home Assistant.
3. Add the integration via the UI.

## Setup

Enter your Google OAuth access token or the JSON content from `~/.gemini/antigravity-cli/antigravity-oauth-token`.

## License

MIT License
