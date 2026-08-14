"""
Rendering: the bolt marker icon, the counter badge, and the KMZ assembly.
Output styling matches the Sheerr Weather GLM product — bolt markers, no
labels/popups, time-stamped points, gold-bordered counter pinned bottom-right.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import simplekml
from PIL import Image, ImageDraw, ImageFont

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def make_bolt_icon(path: Path) -> None:
    """Yellow lightning bolt on transparent — generated once, reused."""
    if path.exists():
        return
    s = 128
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bolt = [(74, 10), (38, 70), (60, 70), (46, 118), (94, 52), (66, 52), (84, 10)]
    d.polygon(bolt, fill=(255, 214, 0, 255), outline=(40, 30, 0, 255))
    img.save(path)


def make_counter(count: int, window_label: str, region: str, path: Path) -> None:
    """Dark rounded badge: big count + 'lightning flashes' + window + region."""
    w, h = 560, 150
    b = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    d.rounded_rectangle([2, 2, w - 3, h - 3], radius=22,
                        fill=(15, 23, 42, 220), outline=(255, 214, 0, 255), width=3)
    d.text((28, 20), f"{count}", font=_font(58), fill=(255, 214, 0, 255))
    num_w = d.textbbox((0, 0), f"{count}", font=_font(58))[2]
    d.text((28 + num_w + 18, 32), "lightning flashes", font=_font(28),
           fill=(255, 255, 255, 255))
    d.text((28, 96), window_label, font=_font(24), fill=(203, 213, 225, 255))
    d.text((28, 124), f"{region} \u00b7 GOES-19 GLM", font=_font(20),
           fill=(148, 163, 184, 255))
    b.save(path)


def build_kmz(records, window_label: str, region: str, workdir: Path,
              out_path: Path, icon_scale: float = 0.9) -> int:
    """
    Assemble the KMZ from flash records. Returns the flash count.
    'records' is an iterable of (lat, lon, time_iso).
    """
    workdir.mkdir(parents=True, exist_ok=True)
    bolt = workdir / "bolt.png"
    counter = workdir / "counter.png"
    make_bolt_icon(bolt)

    records = list(records)
    count = len(records)
    make_counter(count, window_label, region, counter)

    kml = simplekml.Kml()
    kml.document.name = f"GLM Lightning \u2014 {region} \u2014 {window_label}"

    style = simplekml.Style()
    style.iconstyle.icon.href = str(bolt)
    style.iconstyle.scale = icon_scale
    style.labelstyle.scale = 0  # no name labels

    for lat, lon, tstamp in records:
        p = kml.newpoint()
        p.coords = [(lon, lat)]
        p.style = style
        p.timestamp.when = tstamp  # keeps the GE Pro time slider working

    ov = kml.newscreenoverlay(name="Flash counter")
    ov.icon.href = str(counter)
    ov.overlayxy = simplekml.OverlayXY(x=1, y=0,
                                       xunits=simplekml.Units.fraction,
                                       yunits=simplekml.Units.fraction)
    ov.screenxy = simplekml.ScreenXY(x=0.99, y=0.01,
                                     xunits=simplekml.Units.fraction,
                                     yunits=simplekml.Units.fraction)

    kml.savekmz(str(out_path), format=False)
    return count


def window_label(start: dt.datetime, end: dt.datetime, minutes: int) -> str:
    """Human label for the badge, in UTC (GLM's native frame)."""
    return f"Last {minutes} min \u00b7 {start:%H:%M}\u2013{end:%H:%M} UTC"
