# The Rep Index — handoff

Personal replica-watch aggregator: collects QC/review discussion, has Claude turn
threads into findings, and ranks **versions** into three tiers. Runs as a Home
Assistant app (add-on) on the owner's HA Pi. Repo: github.com/skypager-nl/rep-aggregator
(public — never commit secrets, `data/`, `fixtures/`, or the guide sheet).

## Owner's rules (non-negotiable)

- **Nothing is sent to Claude unless the owner picks it** on the Captures page
  (`auto_analyse` option stays off). Collection is fine; analysis is manual.
- **Rep forums and dealer sites only via the NordVPN route** — never the home IP.
  On the Pi: the fail-closed SOCKS proxy (`rwi_proxy` options → `net.verify_egress`).
  From the Mac: only after the owner confirms the NordVPN app is on. Ask first.
- **RWI (forum.replica-watch.info): no automated requests.** Cloudflare challenges
  every bot (robots.txt and RSS included); admin (Trailboss) refused. No bypass,
  no queued/unattended browser crawler (declined — evasion). Only the owner's
  one-click Chrome-extension captures.
- **Real photos only** — no generated/procedural watch images.
- **Vocabulary:** a *version* = one factory's replica of one model (DB table `build`).
  Release numbers (V2, V3) are the version's history, shown only when known.
  Parallel *variants* ("Youth", "Free Sprung", "Tungsten", "Weighted") are separate
  versions and are shown. Never call versions "builds" in the UI (builds = DIY).
- **Tiers: exactly "Tier A", "Tier B", "Tier C".** No S tier, no descriptive names.
- **Commit/push only when the owner says so.** Deploys to the Pi have been OK'd per change.

## Architecture

| Path | What |
|---|---|
| `backend/src/repagg/` | Python package (FastAPI + SQLite, `uv`) |
| `web/` | React + Vite + Tailwind SPA (dark editorial design, HashRouter, relative URLs for HA ingress) |
| `extension/` | Chrome MV3 extension: captures RWI threads (walks pages in the owner's tab via `chrome.pageCapture`) and Reddit threads/wiki |
| `addon/rep_aggregator/` | HA app: `config.yaml` (options), `Dockerfile`, `run.sh` |
| `scripts/deploy.sh` | Builds web, bundles app, streams tar over SSH to `/local_apps/rep_aggregator` on host `ha-pi`, installs/updates/rebuilds |
| `scripts/rolex_photos.py` | Genuine Rolex photos from rolex.com (60 files, in `data/photos/genuine`) |
| `fixtures/` (git-ignored) | Saved RWI/RWG pages for parser tests; `fixtures/sheets/wmtb-*.xlsx` = the guide |

Key backend modules: `scoring.py` (hierarchical Bayesian; tiers on lower bound;
guide priors; release weighting), `extract.py` (Claude extraction, structured output,
`claude-opus-5` default, server-side refusal fallback, daily budget, delete-analysis,
clean-slate), `versions.py` (identity = factory × reference × variant; releases),
`guide.py` (WMTB sheet import → baseline priors), `catalogue.py`/`brands.py`/`models.py`
(69 brands, 145 models, specific references), `ingest.py` (forum/Reddit/MHTML ingest),
`rwi_parse.py`, `rwg_parse.py`, `reddit_parse.py`, `rwg.py` (RWG collector),
`telegram.py` (Telethon; broadcast channels only), `net.py` (VPN egress, fail closed),
`admin.py` (review: merge/confirm/discard factories, models, references), `api.py`.

## Data sources & status

- **Community guide (baseline):** r/RepTime "Who Makes the Best? Guide" (OneDrive xlsx,
  29 May 2026). Imported on every app start from `/app/guides/*.xlsx` (shipped by
  deploy.sh, not in git). Yellow NWBIG → Tier A, green Super Rep → Tier B, rest → C.
  Prior ≈ 4 findings of weight. ~390 versions. Niche one-model factories are tucked
  into a "Niche factories" section on the Factories page.
- **RWI:** extension captures only (see rules).
- **RWG (rwg.bz):** automated collector, public brand/review sections, VPN only,
  15–25 s between requests, 600/day, breadth-first, samples long topics (first 4 +
  last 4 pages), pauses on first 403/429/503/challenge. Enabled (`collectors.rwg: true`).
- **RepGeek:** members-only (XenForo); not collected. Plan was extension capture;
  owner offered login — do NOT automate a logged-in crawler.
- **Reddit:** extension capture works (no usernames stored). Official API request
  submitted (`docs/reddit-api-request.md`); collector not built yet.
- **Telegram:** connected; 5 dealer channels followed. Analysis only on request.
- **Dealer catalogues:** theonewatches brand/model categories were used to curate
  `models.py`; mirotime returned 403 (not bypassed).

## Running & deploying

```bash
cd backend && uv run repagg serve --port 8765          # local API + built site
cd web && npm run dev                                    # Vite on 5173 (proxies /api to 8099)
./scripts/deploy.sh                                      # to the HA Pi (bump version in config.yaml first)
```
CLI (`uv run repagg …`): `seed-catalogue`, `import-guide FILE`, `extract THREAD --source S`,
`clean-slate`, `purge-demo`, `egress-check`, `ingest-file`, `score`.
One-shot actions on the Pi (no shell into the container): touch
`/share/rep_aggregator/{clean-slate,purge-demo,probe}.request` over `ssh ha-pi`,
then redeploy/restart; results land next to it. DB backups: `/data/repagg.pre-*.db`.

Access: HA sidebar (ingress, trusted) or directly at `http://<pi-ip>:8766/` with the
`web_password` login. LAN port otherwise only accepts token-authed extension
captures (`/api/capture*`) and `/api/health`.

## Gotchas learned the hard way

- **SQLite locking:** never hold a write transaction across network I/O. Telegram's
  connection is autocommit for this reason; `db.connect` waits 60 s for locks.
- Status endpoints must not write (schema init runs once per process).
- Chrome on macOS needed Local Network permission (`ERR_ADDRESS_UNREACHABLE`);
  `homeassistant.local` resolves IPv6-only on the Mac — use the Pi's IPv4 in the extension.
- `ha apps logs` keeps lines from previous containers — check timing before blaming a new build.
- Nord's Amsterdam SOCKS host rotates exit IPs; `verify_egress` only checks "not home".
- XenForo/Invision/Reddit markup notes are in the respective `*_parse.py` docstrings.

## Open items / ideas

- Reddit API collector once Reddit approves the request.
- RepGeek via extension capture (reuse the XenForo parser).
- Coverage view (which references/factories lack data) to guide reading.
- Review queue UX for new models/references created by analysis.
- Local persistent memory also lives in `~/.claude/projects/-Users-mac-Developer-rep-aggregator/memory/`.
