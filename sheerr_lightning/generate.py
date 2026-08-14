"""
The generator loop: every INTERVAL_SECONDS, rebuild the live KMZ for the last
WINDOW_MINUTES and push it to Bunny. Run --once for a single build (cron-style
or for testing), or as a long-running service (systemd) for continuous updates.

Design notes:
  * Rolling window is recomputed every cycle, so old strikes fall off the back.
  * The cache is reused across cycles; only new granules download each time.
  * On any fetch/parse error we KEEP the last good uploaded file rather than
    pushing a blank map. Zero flashes in-window is valid, not an error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import signal
import sys
import time

from .config import CONFIG
from . import glm, render, upload

log = logging.getLogger("sheerr.lightning")
_UTC = dt.timezone.utc
_running = True


def _handle_signal(signum, frame):
    global _running
    log.info("Signal %s received — finishing current cycle and exiting.", signum)
    _running = False


def build_once(do_upload: bool = True) -> int:
    """Run a single build cycle. Returns the flash count, or -1 on a kept-last error."""
    cfg = CONFIG
    now = dt.datetime.now(_UTC)
    start = now - dt.timedelta(minutes=cfg.window_minutes)

    try:
        keys = glm.list_keys(cfg.bucket, cfg.product, start, now)
        counts = glm.download_new(cfg.bucket, keys, cfg.cache_dir)
        removed = glm.prune_cache(cfg.cache_dir, start, now)
        records = glm.parse_flashes(cfg.cache_dir, cfg.bbox)
    except Exception as exc:
        log.warning("Fetch/parse failed (%s) — keeping last good file.", exc)
        return -1

    label = render.window_label(start, now, cfg.window_minutes)
    count = render.build_kmz(records, label, cfg.region_label,
                             cfg.workdir, cfg.kmz_path, cfg.icon_scale)
    log.info("Built %s flashes | new=%s prune=%s | %s",
             count, counts["new"], removed, label)

    if do_upload:
        cfg.validate_for_upload()
        try:
            upload.upload_bunny(cfg.kmz_path, cfg.bunny_storage_host,
                                cfg.bunny_storage_zone, cfg.bunny_storage_password,
                                cfg.bunny_remote_path)
            if cfg.purge_on_upload and cfg.bunny_account_api_key:
                upload.purge_bunny(cfg.bunny_pull_url, cfg.bunny_account_api_key)
            log.info("Uploaded -> %s", cfg.bunny_pull_url)
        except Exception as exc:
            log.warning("Upload failed (%s) — CDN keeps last good file.", exc)
            return -1
    return count


def loop(do_upload: bool = True) -> None:
    cfg = CONFIG
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    log.info("Starting loop: window=%smin interval=%ss box=%s",
             cfg.window_minutes, cfg.interval_seconds, cfg.bbox)
    while _running:
        t0 = time.monotonic()
        try:
            build_once(do_upload=do_upload)
        except Exception:
            log.exception("Unexpected error in cycle — continuing.")
        elapsed = time.monotonic() - t0
        sleep_for = max(0.0, cfg.interval_seconds - elapsed)
        for _ in range(int(sleep_for)):
            if not _running:
                break
            time.sleep(1)
    log.info("Stopped cleanly.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sheerr Weather real-time GLM lightning KMZ.")
    ap.add_argument("--once", action="store_true", help="Build a single cycle and exit.")
    ap.add_argument("--no-upload", action="store_true", help="Build locally, skip Bunny.")
    ap.add_argument("--window", type=int, help="Override window minutes.")
    ap.add_argument("--interval", type=int, help="Override interval seconds.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # Late overrides via env would be cleaner, but keep the CLI ergonomic:
    if args.window or args.interval:
        import dataclasses
        globals_cfg = dataclasses.replace(
            CONFIG,
            window_minutes=args.window or CONFIG.window_minutes,
            interval_seconds=args.interval or CONFIG.interval_seconds,
        )
        # rebind module-level CONFIG
        import sheerr_lightning.config as c
        c.CONFIG = globals_cfg
        globals()["CONFIG"] = globals_cfg

    do_upload = not args.no_upload
    if args.once:
        n = build_once(do_upload=do_upload)
        sys.exit(0 if n >= 0 else 1)
    loop(do_upload=do_upload)


if __name__ == "__main__":
    main()
