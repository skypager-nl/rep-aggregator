# Rep Index

A personal, private dashboard that aggregates community quality-control discussion about
replica watches (Rolex references first) into per-build scores, known defects and tiers.

- **Collectors** (read-only): Reddit via the official Data API, forums, and dealer Telegram
  channels. All are disabled by default and polled at low volume.
- **Extraction:** post text is sent to Anthropic's Claude API to pull out structured
  opinions per watch aspect (dial, bezel, movement…) and QC verdicts (GL/RL). No data is
  used for model training.
- **Scoring:** hierarchical Bayesian averages weighted by source trust, author reputation,
  evidence and recency. Tiers are set on the conservative lower bound.
- **Site:** React + FastAPI + SQLite, packaged as a Home Assistant app behind HA's login.
  Nothing is public.

## Layout

| Path | What |
|---|---|
| `backend/` | Python package `repagg`: schema, scoring, API, CLI |
| `web/` | Frontend (Vite, React, Tailwind) |
| `addon/rep_aggregator/` | Home Assistant app packaging |
| `scripts/` | Deploy script, genuine reference photo fetcher |

## Run locally

```bash
cd backend && uv run repagg demo && uv run repagg serve --port 8099
cd web && npm install && npm run dev
```

Demo data is synthetic and flagged as such in the UI. Genuine reference photos are not
included in this repository.
