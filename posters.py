"""posters.py — mirror each film's poster (the chains' own promotional art) into our bucket.

mirror(data) — for every film carrying `poster_src` (the candidate URLs the readers returned,
collected by normalize.merge), download each candidate once (cached by source-URL hash in
data/posters.json), keep the largest portrait one (height/width >= 1.2 — VOX's 940x328 hero and
Novo's banner are never picked), convert it to WebP at 342 and 684 px wide (quality 78), extract
a dominant non-grey colour for the page's ambient glow, and set

    film["poster"]       = "/posters/<fid>-<hash>-342.webp"
    film["poster_2x"]    = "/posters/<fid>-<hash>-684.webp"
    film["poster_color"] = "#rrggbb" | None

The files land in data/posters/ (out of band: not in git, not under out/). `poster_src` is
always removed from the film, so latest.json never hotlinks a chain. A download or decode
failure means no poster for that candidate (retried after RETRY_FAILED) — the site draws the
typographic tile; nothing here ever raises into refresh. Limits: http(s) only, a non-image
Content-Type or a body over MAX_BYTES (8 MB) is refused while streaming, and an image over
MAX_PIXELS (40 Mpx) is refused before decoding. Only the best candidate's bytes stay in memory.
Cache: an ok source is re-downloaded after REVALIDATE (7 days); the output name hashes URL +
content, so replaced art at the same URL gets a new name. Bump VERSION to regenerate all.

upload() — `python posters.py --upload` — a separate step: copies every local WebP not yet
uploaded to s3://<bucket>/<prefix> with a one-year immutable Cache-Control. When the bucket
does not exist yet it prints so and uploads nothing (exit 0).

CLI: python posters.py [--mirror] [--upload] [--bucket B] [--prefix P]
  --mirror  runs mirror() over data/latest.json in place (normally refresh.py does this).
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import io
import json
import os
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

try:
    from botocore.exceptions import ClientError
except ImportError:  # boto3 is only needed for --upload
    class ClientError(Exception):  # type: ignore[no-redef]
        def __init__(self, error_response=None, operation_name=None):
            super().__init__(str(error_response))
            self.response = error_response or {}

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "posters.json"
OUT_DIR = ROOT / "data" / "posters"
BUCKET = "elyoxe-cinema-574771023173"
PREFIX = "posters/"
URL_PREFIX = "/posters/"
WIDTHS = (342, 684)
QUALITY = 78
MIN_PORTRAIT = 1.2          # height / width
VERSION = 1                 # bump to regenerate every file (part of the name hash)
RETRY_FAILED = timedelta(days=1)
# An ok source is re-downloaded after REVALIDATE: the output name hashes the URL *and* the
# content (sha1), so art a chain replaces at the same URL gets a new file name, never a stale
# immutable one.
REVALIDATE = timedelta(days=7)
CACHE_CONTROL = "public, max-age=31536000, immutable"
GAP = 0.3
MAX_BYTES = 8 * 1024 * 1024     # a poster larger than this is not a poster
MAX_PIXELS = 40_000_000         # decompression-bomb ceiling (Pillow's own default is ~178 Mpx)
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
# a server that labels its images badly still gets through (Star sends application/octet-stream)
_OK_TYPES = ("image/", "application/octet-stream", "binary/octet-stream")


class Rejected(Exception):
    """A candidate that is not a usable poster: wrong scheme, not an image, too big."""


def _h(url: str, sha: str | None = None) -> str:
    key = f"{VERSION}:{url}" if not sha else f"{VERSION}:{url}:{sha}"
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def _load(path: Path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("sources", {})
    d.setdefault("films", {})
    d.setdefault("uploaded", [])
    return d


def _save(path: Path, d: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def check_url(url) -> str:
    """http(s) only — libcurl would happily read file:// or ftp://."""
    if not isinstance(url, str) or urlparse(url).scheme not in ("http", "https"):
        raise Rejected(f"not an http(s) URL: {str(url)[:80]!r}")
    return url


def check_headers(headers) -> None:
    """Reject on the response headers alone: a non-image Content-Type, or a declared size over MAX_BYTES."""
    ctype = (headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype and not ctype.startswith(_OK_TYPES):
        raise Rejected(f"content-type {ctype}")
    try:
        size = int(headers.get("content-length") or 0)
    except ValueError:
        size = 0
    if size > MAX_BYTES:
        raise Rejected(f"content-length {size} > {MAX_BYTES}")


_last = [0.0]


def _default_fetch(url: str) -> bytes:
    """One streamed GET with Chrome's TLS fingerprint (Roxy/VOX asset hosts sit behind Akamai),
    stopped at MAX_BYTES."""
    from curl_cffi import requests as cr

    check_url(url)
    wait = GAP - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    r = cr.get(url, impersonate="chrome", timeout=30, stream=True)
    try:
        if r.status_code != 200:
            raise OSError(f"HTTP {r.status_code}")
        check_headers(r.headers)
        buf = bytearray()
        for chunk in r.iter_content():
            buf.extend(chunk)
            if len(buf) > MAX_BYTES:
                raise Rejected(f"body over {MAX_BYTES} bytes")
        return bytes(buf)
    finally:
        r.close()


def _open(blob: bytes) -> Image.Image:
    if len(blob) > MAX_BYTES:
        raise Rejected(f"body over {MAX_BYTES} bytes")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        img = Image.open(io.BytesIO(blob))
        if img.width * img.height > MAX_PIXELS:
            raise Rejected(f"{img.width}x{img.height} over {MAX_PIXELS} px")
        img.load()
    return img.convert("RGB")


def dominant_color(img: Image.Image) -> str | None:
    """The most common saturated hue of the image, as #rrggbb (the mean colour of that hue
    bucket); None when the image is essentially grey/black/white."""
    small = img.convert("RGB").resize((64, 64))
    buckets: dict[int, list] = {}
    raw = small.tobytes()
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s < 0.25 or v < 0.15 or v > 0.97:
            continue
        acc = buckets.setdefault(int(h * 24) % 24, [0.0, 0, 0, 0, 0])
        acc[0] += s * v
        acc[1] += r
        acc[2] += g
        acc[3] += b
        acc[4] += 1
    if not buckets:
        return None
    best = max(buckets.values(), key=lambda a: a[0])
    if best[4] < 64 * 64 * 0.02:
        return None
    n = best[4]
    return "#{:02x}{:02x}{:02x}".format(round(best[1] / n), round(best[2] / n), round(best[3] / n))


def _age_under(src: dict, ttl: timedelta) -> bool:
    try:
        at = datetime.fromisoformat(src.get("at") or "")
    except ValueError:
        return False
    return datetime.now(timezone.utc) - at < ttl


def mirror(data: dict, bucket: str = BUCKET, prefix: str = PREFIX, cache_path=CACHE_PATH,
           out_dir=OUT_DIR, fetch=None) -> dict:
    """See the module docstring. `bucket`/`prefix` name where upload() will put the files (the
    URLs are site-root relative, /posters/...). `fetch(url) -> bytes` is injectable for tests.
    Only the current best candidate's bytes are held in memory, one film at a time.
    Returns {"films", "with_poster", "downloaded", "failed"}."""
    fetch = fetch or _default_fetch
    cache_path, out_dir = Path(cache_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = _load(cache_path)
    stats = {"films": 0, "with_poster": 0, "downloaded": 0, "failed": 0}
    now = datetime.now(timezone.utc).isoformat()

    def probe(url: str):
        """-> (source record, bytes or None). Bytes only when downloaded in this call."""
        key = _h(url)
        src = cache["sources"].get(key)
        if src and ((src.get("ok") and _age_under(src, REVALIDATE))
                    or (not src.get("ok") and _age_under(src, RETRY_FAILED))):
            return src, None
        try:
            blob = fetch(check_url(url))
            img = _open(blob)
            src = {"url": url, "ok": True, "w": img.width, "h": img.height, "at": now,
                   "sha": hashlib.sha1(blob).hexdigest()[:12]}
            img.close()
            stats["downloaded"] += 1
        except Exception as e:  # noqa: BLE001 - a bad poster is no poster, never a crash
            src, blob = {"url": url, "ok": False, "err": str(e)[:200], "at": now}, None
            stats["failed"] += 1
        cache["sources"][key] = src
        return src, blob

    for fid, film in (data.get("films") or {}).items():
        cands = film.pop("poster_src", None) or []
        if not cands:
            continue
        stats["films"] += 1
        try:
            best, best_blob = None, None
            for url in cands:
                src, blob = probe(url)
                if not src.get("ok") or src["h"] < MIN_PORTRAIT * src["w"]:
                    continue
                if best is None or src["w"] * src["h"] > best["w"] * best["h"]:
                    best, best_blob = src, blob   # the previous best's bytes are dropped here
            if best is None:
                continue
            url = best["url"]
            base = f"{fid}-{_h(url, best.get('sha'))}"
            names = [f"{base}-{w}.webp" for w in WIDTHS]
            done = cache["films"].get(fid) or {}
            if not (done.get("files") == names and all((out_dir / n).exists() for n in names)):
                img = _open(best_blob if best_blob is not None else fetch(check_url(url)))
                for w, n in zip(WIDTHS, names):
                    h = round(img.height * w / img.width)
                    img.resize((w, h), Image.LANCZOS).save(out_dir / n, "WEBP", quality=QUALITY, method=6)
                done = {"src": url, "files": names, "color": dominant_color(img), "at": now}
                cache["films"][fid] = done
            film["poster"] = URL_PREFIX + names[0]
            film["poster_2x"] = URL_PREFIX + names[1]
            film["poster_color"] = done.get("color")
            stats["with_poster"] += 1
        except Exception as e:  # noqa: BLE001
            stats["failed"] += 1
            print(f"posters: {fid}: {e}", file=sys.stderr)
    _save(cache_path, cache)
    return stats


def upload(cache_path=CACHE_PATH, out_dir=OUT_DIR, bucket: str = BUCKET, prefix: str = PREFIX,
           client=None) -> int:
    """Upload local WebPs not yet in the bucket. Returns how many were uploaded (0 and a
    message when the bucket does not exist yet)."""
    if client is None:
        import boto3

        client = boto3.client("s3")
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as e:
        code = str((getattr(e, "response", {}) or {}).get("Error", {}).get("Code", ""))
        if code in ("404", "NoSuchBucket", "NotFound"):
            print(f"posters: bucket {bucket} does not exist yet — nothing uploaded; the WebPs wait in {out_dir}")
            return 0
        raise
    cache_path, out_dir = Path(cache_path), Path(out_dir)
    cache = _load(cache_path)
    done = set(cache["uploaded"])
    n = 0
    for p in sorted(out_dir.glob("*.webp")):
        if p.name in done:
            continue
        client.upload_file(str(p), bucket, prefix + p.name,
                           ExtraArgs={"ContentType": "image/webp", "CacheControl": CACHE_CONTROL})
        done.add(p.name)
        n += 1
    cache["uploaded"] = sorted(done)
    _save(cache_path, cache)
    print(f"posters: uploaded {n} file(s) to s3://{bucket}/{prefix}")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mirror", action="store_true", help="mirror posters for data/latest.json in place")
    ap.add_argument("--upload", action="store_true", help="upload local WebPs to the bucket")
    ap.add_argument("--bucket", default=BUCKET)
    ap.add_argument("--prefix", default=PREFIX)
    a = ap.parse_args(argv)
    if not (a.mirror or a.upload):
        ap.print_help()
        return 0
    if a.mirror:
        latest = ROOT / "data" / "latest.json"
        data = json.loads(latest.read_text(encoding="utf-8"))
        print(mirror(data, a.bucket, a.prefix))
        tmp = latest.with_name(latest.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, latest)
    if a.upload:
        upload(bucket=a.bucket, prefix=a.prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
