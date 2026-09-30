"""cinema_photos.py — mirror one real photo per cinema from its official (chain) site into our bucket, for the
cinema page's hero background (like the film page's trailer frame, kit/media.py's `backdrop`).

Source: cinema_photos.yaml, {cid: <official photo URL>} — the owner's (or a future automation's) own
curated mapping, never guessed by this module: a cid missing here or with a broken URL simply gets no
photo, and the cinema page renders exactly as it did before (pages/_core/places.py's cinema_head checks
for `photo` and leaves the head plain when it is absent). MASTER-PLAN's honesty rule («لا أرقام ولا
مخططات مُخترعة») applies the same way to images: nothing here is stock art or a different cinema's
photo standing in for this one.

mirror(data) — for every cid in data["cinemas"] with a source URL: download once (cached by URL hash in
data/cinema_photos.json, revalidated after REVALIDATE like posters.py), resize to WebP at 640/1280 px
wide (the long edge; a very tall source is skipped — MIN_LANDSCAPE — since the darkened top-of-page band
this fills is landscape, unlike the poster's portrait card), and set

    cinema["photo"] = {"w1280": "/posters/cin-<cid>-<hash>-1280.webp", "w640": "…-640.webp", "w", "h"}

Budget (the owner's phone, one heavy process at a time): CHECK_CAP fresh downloads a run — a cinema
already mirrored costs nothing until REVALIDATE is up, and a failed one waits RETRY_FAILED before trying
again. Reuses posters.py's own http client, decode guards (MAX_BYTES/MAX_PIXELS) and S3 uploader — the
files land in data/posters/ and go up to the SAME bucket/prefix (s3://…/posters/) film posters do, so
`python posters.py --upload` (or a call to this module's own upload()) ships both in one pass. Never
raises into the publish; the step (steps/cinema_photo.py) wraps this the same way steps/backdrops.py
wraps its own network calls."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

import posters as pm

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "cinema_photos.json"
OUT_DIR = ROOT / "data" / "posters"          # same directory (and so the same S3 prefix) as posters.py
SOURCES_PATH = ROOT / "cinema_photos.yaml"
WIDTHS = (640, 1280)
MIN_LANDSCAPE = 0.9   # width / height must be at least this — a portrait/square source is skipped
CHECK_CAP = 3         # fresh network downloads a run (the owner's phone: one heavy process, capped)


def load_sources(path=SOURCES_PATH) -> dict:
    if not path.exists():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: v for k, v in (doc.get("cinemas") or {}).items() if isinstance(v, str) and v}


def mirror(data: dict, sources_path=None, cache_path=None, out_dir=None,
           fetch=None, cap=None) -> dict:
    """See the module docstring. Returns {"cinemas", "with_photo", "downloaded", "failed", "skipped_cap"}.
    Every path/cap defaults to this module's own globals, looked up at call time (not bound as a default
    argument) so a test's `monkeypatch.setattr(cph, "SOURCES_PATH", ...)` is honoured even through
    steps/cinema_photo.py's own call, which never names sources_path itself."""
    sources_path = sources_path if sources_path is not None else SOURCES_PATH
    cache_path = cache_path if cache_path is not None else CACHE_PATH
    out_dir = out_dir if out_dir is not None else OUT_DIR
    cap = CHECK_CAP if cap is None else cap
    fetch = fetch or pm._default_fetch
    cache_path, out_dir = Path(cache_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = pm._load(cache_path)
    cache.setdefault("cinemas", {})
    sources = load_sources(sources_path)
    stats = {"cinemas": 0, "with_photo": 0, "downloaded": 0, "failed": 0, "skipped_cap": 0}
    budget = cap

    for cid, c in (data.get("cinemas") or {}).items():
        c.pop("photo", None)
        url = sources.get(cid)
        if not url:
            continue
        stats["cinemas"] += 1
        key = pm._h(url)
        src = cache["sources"].get(key)
        due = not (src and ((src.get("ok") and pm._age_under(src, pm.REVALIDATE))
                            or (not src.get("ok") and pm._age_under(src, pm.RETRY_FAILED))))
        if due and budget <= 0:
            stats["skipped_cap"] += 1
            continue
        try:
            if due:
                blob = fetch(pm.check_url(url))
                img = pm._open(blob)
                budget -= 1
                if img.width < MIN_LANDSCAPE * img.height:
                    raise pm.Rejected(f"not landscape enough: {img.width}x{img.height}")
                import hashlib
                sha = hashlib.sha1(blob).hexdigest()[:12]
                src = {"url": url, "ok": True, "w": img.width, "h": img.height, "at": pm.datetime.now(pm.timezone.utc).isoformat(), "sha": sha}
                cache["sources"][key] = src
                base = f"cin-{cid}-{pm._h(url, sha)}"
                names = [f"{base}-{w}.webp" for w in WIDTHS]
                for w, n in zip(WIDTHS, names):
                    h = round(img.height * w / img.width)
                    img.resize((w, h), pm.Image.LANCZOS).save(out_dir / n, "WEBP", quality=pm.QUALITY, method=6)
                img.close()
                cache["cinemas"][cid] = {"src": url, "files": names, "w": src["w"], "h": src["h"], "at": src["at"]}
                stats["downloaded"] += 1
            entry = cache["cinemas"].get(cid)
            if not entry or not all((out_dir / n).exists() for n in entry.get("files") or []):
                continue
            names = entry["files"]
            c["photo"] = {"w1280": pm.URL_PREFIX + names[1], "w640": pm.URL_PREFIX + names[0],
                          "w": entry["w"], "h": entry["h"]}
            stats["with_photo"] += 1
        except Exception as e:  # noqa: BLE001 - a bad/missing cinema photo is no photo, never a crash
            if due:
                cache["sources"][key] = {"url": url, "ok": False, "err": str(e)[:200],
                                          "at": pm.datetime.now(pm.timezone.utc).isoformat()}
                stats["failed"] += 1
            print(f"cinema_photos: {cid}: {e}", file=sys.stderr)
    pm._save(cache_path, cache)
    return stats


def upload(cache_path=CACHE_PATH, out_dir=OUT_DIR, bucket: str = pm.BUCKET, prefix: str = pm.PREFIX,
           client=None) -> int:
    """Ships every local cinema photo not yet uploaded to the SAME bucket/prefix posters.py uses
    (s3://…/posters/cin-*.webp), by delegating straight to posters.upload() with our own cache/out_dir —
    it is already generic over any *.webp files in `out_dir` not in its own "uploaded" list."""
    return pm.upload(cache_path=cache_path, out_dir=out_dir, bucket=bucket, prefix=prefix, client=client)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mirror", action="store_true", help="mirror cinema photos for data/latest.json in place")
    ap.add_argument("--upload", action="store_true", help="upload local cinema WebPs to the bucket")
    a = ap.parse_args(argv)
    if not (a.mirror or a.upload):
        ap.print_help()
        return 0
    if a.mirror:
        latest = ROOT / "data" / "latest.json"
        data = json.loads(latest.read_text(encoding="utf-8"))
        print(mirror(data))
        tmp = latest.with_name(latest.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, latest)
    if a.upload:
        upload()
    return 0


if __name__ == "__main__":
    sys.exit(main())
