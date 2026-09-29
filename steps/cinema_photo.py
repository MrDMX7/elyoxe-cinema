"""steps/cinema_photo.py — thin wrapper around cinema_photos.mirror() (see that module's docstring):
attaches cinema["photo"] from data/cinema_photos.json (or a fresh, capped download) for every cid in
cinema_photos.yaml. --offline: cap=0 so no network is ever attempted, but a cinema already mirrored on
an earlier run still gets its cached photo applied (the cache read, never a download, decides it)."""
from __future__ import annotations

from pathlib import Path


def run(data, ctx):
    import cinema_photos as cp

    ddir = Path(ctx.get("data_dir") or Path(__file__).resolve().parent.parent / "data")
    cap = 0 if ctx.get("offline") else cp.CHECK_CAP
    return cp.mirror(data, cache_path=ddir / "cinema_photos.json", out_dir=ddir / "posters", cap=cap)
