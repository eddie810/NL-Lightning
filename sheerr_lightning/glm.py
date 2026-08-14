"""
GLM data access: list, download, prune, and parse GOES GLM L2 granules.

Uses the anonymous public S3 HTTPS endpoint — no AWS credentials, no boto3.
Granules are ~20s each; filenames encode the scan start time as _sYYYYDOYHHMMSSf.
"""
from __future__ import annotations

import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

_START_RE = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})")
_KEY_RE = re.compile(r"(?<=<Key>)[^<]+")
_UTC = dt.timezone.utc


def granule_start(name: str) -> dt.datetime | None:
    """Parse the scan start time out of a GLM key/filename."""
    m = _START_RE.search(name)
    if not m:
        return None
    y, doy, hh, mm, ss = map(int, m.groups())
    return dt.datetime(y, 1, 1, tzinfo=_UTC) + dt.timedelta(
        days=doy - 1, hours=hh, minutes=mm, seconds=ss
    )


def _hour_prefixes(bucket_product: str, start: dt.datetime, end: dt.datetime):
    """Every YYYY/DOY/HH prefix the window touches (spans 2 hours near the top)."""
    seen = set()
    t = start.replace(minute=0, second=0, microsecond=0)
    while t <= end:
        key = (t.year, t.timetuple().tm_yday, t.hour)
        if key not in seen:
            seen.add(key)
            y, doy, hh = key
            yield f"{bucket_product}/{y}/{doy:03d}/{hh:02d}/"
        t += dt.timedelta(hours=1)


def list_keys(bucket: str, product: str, start: dt.datetime, end: dt.datetime,
              timeout: int = 30) -> list[str]:
    """List granule keys whose scan start falls within [start, end]."""
    keys: list[str] = []
    for prefix in _hour_prefixes(product, start, end):
        url = f"https://{bucket}.s3.amazonaws.com/?list-type=2&prefix={prefix}"
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        keys += _KEY_RE.findall(resp.text)
    return sorted(
        k for k in keys
        if (t := granule_start(k)) and start <= t <= end
    )


def download_new(bucket: str, keys: list[str], cache_dir: Path,
                 workers: int = 16, timeout: int = 60) -> dict[str, int]:
    """Download any keys not already cached. Returns counts by outcome."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    counts = {"new": 0, "have": 0, "fail": 0}

    def _dl(key: str) -> str:
        dest = cache_dir / Path(key).name
        if dest.exists():
            return "have"
        try:
            r = requests.get(f"https://{bucket}.s3.amazonaws.com/{key}",
                             timeout=timeout)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return "new"
        except Exception:
            return "fail"

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for outcome in ex.map(_dl, keys):
            counts[outcome] += 1
    return counts


def prune_cache(cache_dir: Path, start: dt.datetime, end: dt.datetime) -> int:
    """Delete cached granules outside the current window. Returns count removed."""
    if not cache_dir.exists():
        return 0
    removed = 0
    for f in cache_dir.glob("*.nc"):
        t = granule_start(f.name)
        if t is None or not (start <= t <= end):
            f.unlink(missing_ok=True)
            removed += 1
    return removed


def parse_flashes(cache_dir: Path, bbox: tuple[float, float, float, float]):
    """
    Read cached granules and yield (lat, lon, time_iso) for every flash whose
    centroid falls inside the bounding box. netCDF4 is imported lazily so the
    rest of the module stays importable without it.
    """
    import netCDF4 as nc  # lazy

    lat_min, lat_max, lon_min, lon_max = bbox
    records: list[tuple[float, float, str]] = []
    for f in sorted(cache_dir.glob("*.nc")):
        try:
            ds = nc.Dataset(f)
            lats = ds.variables["flash_lat"][:]
            lons = ds.variables["flash_lon"][:]
            tstamp = ds.time_coverage_start
            ds.close()
        except Exception:
            continue
        for la, lo in zip(lats, lons):
            la, lo = float(la), float(lo)
            if lat_min <= la <= lat_max and lon_min <= lo <= lon_max:
                records.append((la, lo, tstamp))
    return records
