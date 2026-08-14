"""
Central configuration. Everything tunable lives here or in the environment.
Secrets (Bunny keys) come from the environment / .env — never commit them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key, default)
    return val.strip() if isinstance(val, str) else val


@dataclass(frozen=True)
class Config:
    # --- Source: NOAA GOES GLM on AWS Open Data (anonymous, no credentials) ---
    # GOES-19 is GOES-East from 2025 on. Use noaa-goes16 for older events.
    bucket: str = _env("GLM_BUCKET", "noaa-goes19")
    product: str = "GLM-L2-LCFA"

    # --- Coverage box: Newfoundland & Labrador ---
    lat_min: float = 46.0
    lat_max: float = 61.0
    lon_min: float = -68.0
    lon_max: float = -52.0

    # --- Rolling window & cadence ---
    # window_minutes: how far back each build reaches (the "last N minutes").
    # interval_seconds: how often the loop rebuilds. GLM granules land every
    # ~20s, so 30-60s is the sweet spot; faster just re-pulls the same data.
    window_minutes: int = int(_env("WINDOW_MINUTES", "30"))
    interval_seconds: int = int(_env("INTERVAL_SECONDS", "45"))

    # --- Local paths ---
    workdir: Path = field(default_factory=lambda: Path(_env("WORKDIR", "./work")))
    # Built KMZ before upload; also the file you'd point a local GE Pro at for testing.
    kmz_name: str = "glm_lightning_live.kmz"

    # --- Marker / badge styling ---
    icon_scale: float = 0.9
    region_label: str = "Newfoundland & Labrador"

    # --- Bunny CDN (Storage API for upload + optional purge) ---
    # Storage host is region-specific, e.g. "storage.bunnycdn.com" (default/DE),
    # "ny.storage.bunnycdn.com", "la.storage.bunnycdn.com", etc.
    bunny_storage_host: str = _env("BUNNY_STORAGE_HOST", "storage.bunnycdn.com")
    bunny_storage_zone: str | None = _env("BUNNY_STORAGE_ZONE")
    bunny_storage_password: str | None = _env("BUNNY_STORAGE_PASSWORD")
    # Path within the storage zone where the live KMZ is overwritten each cycle.
    bunny_remote_path: str = _env("BUNNY_REMOTE_PATH", "lightning/glm_lightning_live.kmz")
    # Public pull-zone URL that resolves to that same object (what the frame KML hits).
    bunny_pull_url: str | None = _env("BUNNY_PULL_URL")
    # Account API key, only needed if you purge on upload instead of using short TTL.
    bunny_account_api_key: str | None = _env("BUNNY_ACCOUNT_API_KEY")
    purge_on_upload: bool = _env("PURGE_ON_UPLOAD", "false").lower() == "true"

    @property
    def cache_dir(self) -> Path:
        return self.workdir / "nc"

    @property
    def kmz_path(self) -> Path:
        return self.workdir / self.kmz_name

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.lat_min, self.lat_max, self.lon_min, self.lon_max)

    def validate_for_upload(self) -> None:
        missing = [
            name for name, val in {
                "BUNNY_STORAGE_ZONE": self.bunny_storage_zone,
                "BUNNY_STORAGE_PASSWORD": self.bunny_storage_password,
                "BUNNY_PULL_URL": self.bunny_pull_url,
            }.items() if not val
        ]
        if missing:
            raise RuntimeError(
                "Missing env for upload: " + ", ".join(missing)
                + ". Set them (see .env.example) or run with --no-upload."
            )


CONFIG = Config()
