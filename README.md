# Sheerr Weather — Real-Time GLM Lightning

Live lightning for Google Earth Pro. Pulls NOAA **GOES-19 GLM** flash data,
filters to **Newfoundland & Labrador**, renders a KMZ (bolt markers + counter
badge), and pushes it to Bunny CDN on a loop. You open one small NetworkLink
file in Earth Pro once, and it refreshes itself.

## How it works

Two files, and that's the whole design:

- **`frame.kml`** — open this in Google Earth Pro **once**. It has no strikes;
  it's a NetworkLink pointing at a fixed Bunny URL that re-fetches on a timer.
- **The live KMZ** — the actual markers, overwritten at that same URL every
  cycle by the generator running on your VM.

Same URL always, only the contents change — so Earth Pro never needs a
re-import. See `CLAUDE.md` for the full architecture and invariants.

## Setup

```bash
git clone <your-repo-url> sheerr-lightning-realtime
cd sheerr-lightning-realtime
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your Bunny values
```

## Test locally (no CDN needed)

```bash
python -m sheerr_lightning.generate --once --no-upload
# → writes work/glm_lightning_live.kmz — open it in Google Earth Pro
```

## Go live

1. Fill in `.env` (Bunny storage zone, password, remote path, pull URL).
2. Set a **short cache TTL** on that pull-zone path (a few seconds), or set
   `PURGE_ON_UPLOAD=true` and add `BUNNY_ACCOUNT_API_KEY`.
3. Edit `frame.kml` — set `<href>` to your `BUNNY_PULL_URL` and match
   `<refreshInterval>` to `INTERVAL_SECONDS`.
4. Run the loop:
   ```bash
   python -m sheerr_lightning.generate
   ```
5. Open `frame.kml` in Google Earth Pro. Done — it updates on its own.

## Run as a service

```bash
sudo cp -r . /opt/sheerr-lightning-realtime
sudo cp systemd/sheerr-lightning.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sheerr-lightning
journalctl -u sheerr-lightning -f
```

## Config knobs (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `WINDOW_MINUTES` | 30 | How far back each build reaches |
| `INTERVAL_SECONDS` | 45 | How often it rebuilds (match `frame.kml`) |
| `GLM_BUCKET` | noaa-goes19 | Source bucket (use noaa-goes16 pre-2025) |
| `BUNNY_STORAGE_*` | — | Storage zone, host, password, remote path |
| `BUNNY_PULL_URL` | — | Public URL the frame KML hits |
| `PURGE_ON_UPLOAD` | false | Purge instead of short TTL |

## Notes

- **This is GLM total lightning (IC + CG combined), not ground-strike data.**
  Flash locations are satellite centroids, good to ~8–10 km. For certified
  cloud-to-ground strikes (claims, disputes), use Vaisala NLDN/GLD360 instead.
- Badge times are UTC (GLM's native frame).
- One-off historical exports (a specific past window) are a separate task from
  this always-on loop; the loop stays on the rolling window.
