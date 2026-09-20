# ai-news-pipeline

Runs the daily AI news brief unattended. Design: `docs` link below.

- `.github/workflows/daily-brief.yml` — the daily run, Mon–Fri 07:00 Cyprus time
- `.github/workflows/weekly-healthcheck.yml` — Monday check that it's still running
- `scripts/` — everything the workflows call
- `state/ms_refresh_token.enc` — the live Microsoft refresh token, encrypted.
  Never edit by hand. Recovery steps: see the design spec.

Design spec: (copy of `docs/superpowers/specs/2026-09-20-ai-news-pipeline-design.md`
from the Talos repo — not duplicated here on purpose; ask Nick for the current copy
if this repo and Talos have drifted.)
