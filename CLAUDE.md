# CLAUDE.md

Context for Claude Code working in this repo. Read this before making changes.

## What this is

A real-time lightning feed for Google Earth Pro. It pulls NOAA GOES-19 GLM
Level-2 flash data, filters to a Newfoundland & Labrador box, renders a KMZ
with bolt markers + a counter badge, and pushes it to Bunny CDN on a loop.
Google Earth Pro opens a tiny NetworkLink file once and auto-refreshes.

Built for Sheerr Weather (sheerrweather.ca). Runs on an always-on Linux VM.

## Architecture — the two-file split

The "live" behaviour comes from separating the viewer's file from the data:

1. **`frame.kml`** — a NetworkLink the user opens ONCE in Google Earth Pro.
   Contains no strikes. Points at a fixed Bunny pull-zone URL and refreshes on
   an interval. Never changes.
2. **The live KMZ** — the actual markers, overwritten at that fixed URL every
   cycle by the generator. Same URL always; only the contents change, so Earth
   Pro never needs a re-import.

Neither URL ever changes. That's the whole trick.

## Module map (`sheerr_lightning/`)

- `config.py` — all tunables + env-sourced Bunny secrets. `CONFIG` singleton.
- `glm.py` — S3 listing, granule download, cache pruning, netCDF parsing.
  Uses the anonymous public S3 HTTPS endpoint. No boto3, no AWS creds.
- `render.py` — bolt icon, counter badge, KMZ assembly. Visual style is fixed
  here (bolt markers, `labelstyle.scale = 0` so no popups, gold counter badge).
- `upload.py` — Bunny Storage API PUT + optional pull-zone purge.
- `generate.py` — the loop. `build_once()` is one cycle; `loop()` runs forever.
  Entry point is `python -m sheerr_lightning.generate`.

## Key invariants — don't break these

- **Keep-last-good on error.** If S3 or parse or upload fails, we return -1 and
  do NOT overwrite the live file. Never push a blank map on a transient error.
- **Zero flashes is valid**, not an error. Counter shows 0; file still uploads.
- **Rolling window is recomputed every cycle** (`now - WINDOW_MINUTES`). That's
  what makes old strikes fall off. Don't cache the window across cycles.
- **Cache is reused across cycles.** Only new granules download; `prune_cache`
  trims anything outside the window. Don't wipe the whole cache each cycle.
- **GLM = total lightning (IC + CG).** Label as "flashes", not "strikes". This
  is not ground-truth CG data (that's Vaisala NLDN/GLD360). Don't relabel.
- **Granule filenames encode start time** as `_sYYYYDOYHHMMSSf`. The window
  filter relies on `glm.granule_start()`. Keep that regex in sync if touched.
- **Near the top of the hour the window spans two hour-prefixes.**
  `glm._hour_prefixes()` handles that — don't "simplify" it to one prefix.

## Data facts (verified, current)

- Bucket `noaa-goes19`, product `GLM-L2-LCFA`, prefix `.../YYYY/DOY/HH/`.
- Granules land every ~20s. S3 holds the full archive (moves to Infrequent
  Access after 30 days but stays available). GOES-19 starts 2025; use
  `noaa-goes16` for older events.
- NL box: lat 46–61, lon -68 to -52.
- Variables used: `flash_lat`, `flash_lon`, global attr `time_coverage_start`.

## Timezone note

GLM is native UTC and the KMZ badge shows UTC. Newfoundland local is NDT
(UTC-2:30) in summer, NST (UTC-3:30) in winter. Any local-time conversion for
one-off historical exports is separate from this loop — the loop stays UTC.

## Cadence & CDN caching

- `INTERVAL_SECONDS` (generator) and `frame.kml` `refreshInterval` should match,
  30-60s. Faster just re-pulls identical data.
- Bunny will serve stale copies unless you either set a SHORT PULL-ZONE TTL
  (preferred, simpler) or `PURGE_ON_UPLOAD=true` with an account API key.
  End-to-end latency ~1-2.5 min is normal (S3 lag + interval + GE refresh).

## Running / testing

- One cycle, no upload: `python -m sheerr_lightning.generate --once --no-upload`
  → writes `work/glm_lightning_live.kmz` you can open locally.
- Continuous: `python -m sheerr_lightning.generate` (needs Bunny env set).
- Deploy: `systemd/sheerr-lightning.service`.

## Likely future work

- Second window/product (e.g. a 3h view, or a CG-only feed via Vaisala).
- Tighten box to south coast on demand.
- OBS/broadcast overlay variant off the same feed.
