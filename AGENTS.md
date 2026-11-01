# Agent instructions

## Project

This Home Assistant integration monitors Google Antigravity subscription quotas and rate limits and exposes usage and reset information as sensors.

## Working in this repository

- Read `README.md` before changing authentication or quota handling; it describes the setup flow and legacy-token fallback.
- Keep credential handling in Home Assistant's application-credential and config-flow mechanisms. Do not add tokens or OAuth secrets to repository files or logs.

## Validation

- Run `uvx ruff check .` and `uvx ruff format --check .` for Python changes.
- CI runs Hassfest and the shared Ruff checks; it currently has no test job.
- The shared Ruff action is maintained in [`pschmitt/ci-workflows`](https://github.com/pschmitt/ci-workflows).
