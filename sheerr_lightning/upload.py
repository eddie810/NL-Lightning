"""
Bunny CDN delivery: overwrite the live object via the Storage API, and
(optionally) purge the pull-zone cache so Google Earth sees the new file.

Prefer a short cache TTL on the pull zone over purging — it's simpler and
avoids per-cycle API calls. Purge is here for the alternative approach.
"""
from __future__ import annotations

from pathlib import Path

import requests


def upload_bunny(local_path: Path, storage_host: str, storage_zone: str,
                 storage_password: str, remote_path: str, timeout: int = 60) -> None:
    """PUT the file into the storage zone, overwriting the previous version."""
    url = f"https://{storage_host}/{storage_zone}/{remote_path.lstrip('/')}"
    headers = {
        "AccessKey": storage_password,
        "Content-Type": "application/vnd.google-earth.kmz",
    }
    with open(local_path, "rb") as fh:
        resp = requests.put(url, headers=headers, data=fh, timeout=timeout)
    resp.raise_for_status()


def purge_bunny(pull_url: str, account_api_key: str, timeout: int = 30) -> None:
    """Purge the pull-zone cache for the live URL (only if not using short TTL)."""
    resp = requests.post(
        "https://api.bunny.net/purge",
        params={"url": pull_url},
        headers={"AccessKey": account_api_key},
        timeout=timeout,
    )
    resp.raise_for_status()
