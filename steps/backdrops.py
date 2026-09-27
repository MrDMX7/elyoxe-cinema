"""steps/backdrops.py — a clean backdrop frame from each film's YouTube trailer (UI redesign Task 1,
docs/superpowers/specs/2026-09-27-ui-redesign-design.md "Backdrops").

For every film currently showing (`data["films"]`, `status != "archived"`) or coming
(`data["coming"]`) that carries a trailer id: download <=720p video-only with yt-dlp, sample
SAMPLE_COUNT candidate frames between 12% and 80% of the trailer's runtime, crop letterbox bars
(`crop_letterbox`), score each frame (`score_frame` — reject near-black/near-white frames, burned-in
subtitles in the bottom band, and title-card text in a centred band on an otherwise flat frame;
otherwise colourfulness x mid-tone weight) and keep the best. The chosen frame is saved as two WebPs
(1280w, 640w) into `<data_dir>/posters/` — the SAME directory posters.py mirrors real posters into and
`posters.py --upload` reads from, so run.sh's existing `python posters.py --upload` ships these too
with no separate wiring — and recorded in `<data_dir>/backdrops.json`:

    {fid: {"trailer": <yt id>, "w1280": "/posters/bd-<fid>-<hash>-1280.webp",
           "w640": "/posters/bd-<fid>-<hash>-640.webp", "w": 1280, "h": <int>, "t": <seconds>, "at": <iso>}}
    {fid: {"trailer": <yt id>, "fail": <iso>, "kind": "transient" | "rejected"}}

("w"/"h" — the pixel size of the 1280w file — are an addition beyond the brief's own schema sketch,
kept because Kit.backdrop() needs *some* width/height to draw an `<img>` without a layout shift, and a
letterbox-cropped trailer frame is not reliably 16:9.)

A cache entry is reused forever as long as the film's trailer id hasn't changed (a chain that swaps a
teaser for the real trailer gets a fresh frame). A failure is retried after a TTL that depends on
its `kind` (fix round 1, review Important #1): "transient" (the download/ffprobe/every ffmpeg seek
itself failed — network, yt-dlp, a missing binary, a timeout) retries after FAIL_TTL_TRANSIENT (6h);
"rejected" (the video was read fine, every sampled frame was just scored None) retries after the
full FAIL_TTL_REJECTED (7 days) — a one-off hiccup shouldn't sit behind a week-long delay the way a
genuinely unusable trailer should. At most CINEMA_BACKDROPS_MAX (env, default DEFAULT_MAX_NEW=8)
films with NO usable cache entry are attempted per run, AND no NEW film is started once
CINEMA_BACKDROPS_BUDGET_S (env, default DEFAULT_BUDGET_S=480s/8min) of wall-clock time has passed
since `run()` began (fix round 1, review Minor #2) — the phone this runs on has one heavy process at
a time and nothing here is worth blocking an hourly refresh over; a film left over either limit is
simply picked up by a later run (nothing about it is written, so it is not "cached" either way). The
downloaded video is deleted after each film whether it succeeded or failed (`process_film`'s
`finally`), so nothing here grows `data/` across runs. A single film's failure never fails the step,
same convention as og.py/posters.py: caught in `run()`'s per-film loop and recorded as a cache
failure.

Manual override (fix round 1, review Important #2): `<repo root>/backdrops_override.yaml` —
`{fid: "none"}` forces the poster-blur fallback forever (the film is skipped entirely, and any
existing cache entry/files for it are dropped); `{fid: <seconds>}` skips scoring and takes exactly
that timestamp instead (still letterbox-cropped and encoded normally) — changing the number
re-extracts, since the cache entry records which override value produced it (`"override_t"`).
Malformed entries/fids are ignored, never an error. See backdrops_override.yaml's own header for the
full contract and the `sacrifice` example this round's real-run false-accept prompted.

Orphaned `bd-*.webp` pruning (fix round 1, review Minor #3): after every run, any cache entry for a
fid that is no longer showing/coming, or whose `trailer` no longer matches that film's CURRENT
trailer, is dropped from the cache, and any `bd-*.webp` file in `<data_dir>/posters/` not named by a
surviving cache entry is deleted — the same "collect what's still wanted, remove whatever else is on
disk" convention `steps/og.py` already uses for `data/og/`.

Offline (`ctx.get("offline")`): no subprocess is started at all — the step returns immediately. Not a
courtesy: run_steps() runs every `steps/*.py` (including this one) with `--offline` in the test suite,
and a real yt-dlp/ffmpeg call there would be exactly the network reach that suite forbids.

Every cache entry whose trailer id still matches the film's CURRENT trailer, and whose files still
exist on disk, is copied onto `data["films"][fid]["backdrop"]` (never `data["coming"][fid]` —
pages/coming.py never calls Kit.backdrop(); the cache entry still sits there ready for the day the
film starts showing, so it costs nothing to have fetched it early) for site_kit.Kit.backdrop() to
prefer over the poster-blur fallback. A film overridden to "none" is never attached, however stale a
cache entry from before the override existed.

run(data, ctx) -> {"new": n, "failed": n, "cached": n} | {"new": 0, "failed": 0, "cached": 0, "offline": True}
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from PIL import Image, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parent.parent
OVERRIDE_PATH = ROOT / "backdrops_override.yaml"

YT = re.compile(r"^[A-Za-z0-9_-]{11}$")   # same shape site_kit.YT validates a trailer id against
FID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,120}$")

SAMPLE_COUNT = 16
START_FRAC, END_FRAC = 0.12, 0.80
WIDTHS = (1280, 640)
WEBP_QUALITY = 80
DEFAULT_MAX_NEW = 8
DEFAULT_BUDGET_S = 480   # 8 minutes of wall clock spent STARTING new films, per run (fix round 1)
FAIL_TTL_TRANSIENT = timedelta(hours=6)    # download/ffprobe/ffmpeg/network trouble -- probably a blip
FAIL_TTL_REJECTED = timedelta(days=7)      # the video played fine, every sampled frame just scored None
DOWNLOAD_TIMEOUT = 240
FFPROBE_TIMEOUT = 20
FFMPEG_TIMEOUT = 30

# score_frame thresholds — see the module docstring and docs/superpowers/specs/2026-09-27-ui-redesign-design.md
LUMA_MIN, LUMA_MAX = 35, 200
EDGE_THRESHOLD = 32           # a FIND_EDGES pixel above this counts as "an edge" once binarised
BOTTOM_BAND = (0.78, 1.0)     # the bottom 22%, where a chain burns in Arabic subtitles
SUBTITLE_RATIO, SUBTITLE_FLOOR = 2.2, 0.03
CENTRE_BAND = (0.42, 0.58)    # a centred title-card headline
SURROUND_BANDS = ((0.12, 0.30), (0.70, 0.88))
CENTRE_RATIO, CENTRE_FLOOR = 2.2, 0.05
SURROUND_FLAT_MAX = 0.02      # the title-card check only fires when the surround is actually flat
SCORE_WIDTH = 320             # every measurement below is a statistic, not a coordinate: downsizing
                               # first keeps score_frame phone-cheap without changing what passes


def _small(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    if rgb.width <= SCORE_WIDTH:
        return rgb
    h = max(1, round(SCORE_WIDTH * rgb.height / rgb.width))
    return rgb.resize((SCORE_WIDTH, h))


def _pixels(img: Image.Image) -> list:
    """The image's pixels in row order. Pillow 12 deprecates getdata() for get_flattened_data(); an older Pillow
    (the Fold's Debian one) only has getdata()."""
    fn = getattr(img, "get_flattened_data", None)
    return list(fn() if fn else img.getdata())


def _colourfulness(rgb_small: Image.Image) -> float:
    """Hasler-Süsstrunk colourfulness metric on the already-downsized image."""
    data = _pixels(rgb_small)
    n = len(data)
    if not n:
        return 0.0
    rg = [r - g for r, g, _ in data]
    yb = [0.5 * (r + g) - b for r, g, b in data]
    mean_rg, mean_yb = sum(rg) / n, sum(yb) / n
    var_rg = sum((v - mean_rg) ** 2 for v in rg) / n
    var_yb = sum((v - mean_yb) ** 2 for v in yb) / n
    return (var_rg + var_yb) ** 0.5 + 0.3 * (mean_rg ** 2 + mean_yb ** 2) ** 0.5


def score_frame(img: Image.Image):
    """None = reject. Otherwise colourfulness x a mid-tone weight. See the module docstring for the
    three rejection rules (luma range, burned-in bottom-band subtitles, centred title-card text)."""
    small = _small(img)
    w, h = small.size
    if w < 4 or h < 4:
        return None
    gray = small.convert("L")
    luma_mean = ImageStat.Stat(gray).mean[0]
    if luma_mean < LUMA_MIN or luma_mean > LUMA_MAX:
        return None

    # FIND_EDGES sees the image's own top/bottom row as a hard drop to nothing, so a perfectly
    # smooth gradient (zero real edges) still lights up a false, uniform edge band right at those
    # two borders -- exactly where BOTTOM_BAND and the outer bands look. Replicate-pad by one row
    # top and bottom first (the row above row 0 is row 0 again) so the filter sees the interior's
    # own smoothness there instead of a fabricated cliff, then crop the padding back off.
    padded = Image.new("L", (w, h + 2))
    padded.paste(gray.crop((0, 0, w, 1)), (0, 0))
    padded.paste(gray, (0, 1))
    padded.paste(gray.crop((0, h - 1, w, h)), (0, h + 1))
    edges = padded.filter(ImageFilter.FIND_EDGES).crop((0, 1, w, h + 1)).point(lambda p: 255 if p > EDGE_THRESHOLD else 0)

    def density(top_frac, bot_frac):
        top = max(0, min(h - 1, int(h * top_frac)))
        bot = max(top + 1, min(h, int(h * bot_frac)))
        return ImageStat.Stat(edges.crop((0, top, w, bot))).mean[0] / 255.0

    bottom = density(*BOTTOM_BAND)
    bands = [density(i / 8, (i + 1) / 8) for i in range(8)]
    median_band = statistics.median(bands)
    if bottom > max(SUBTITLE_RATIO * median_band, SUBTITLE_FLOOR):
        return None   # a dense bottom strip against a quiet frame: a burned-in subtitle line

    centre = density(*CENTRE_BAND)
    surround = statistics.mean(density(*b) for b in SURROUND_BANDS)
    if surround < SURROUND_FLAT_MAX and centre > max(CENTRE_RATIO * surround, CENTRE_FLOOR):
        return None   # bold text on an otherwise flat background: a title card, not a scene

    weight = max(0.35, 1 - abs(luma_mean - 127.5) / 127.5)
    return _colourfulness(small) * weight


def crop_letterbox(img: Image.Image) -> Image.Image:
    """Removes rows whose mean luma < 12 from the top and bottom (the black bars of a cinemascope
    trailer inside a 16:9 container). A frame that is black throughout is returned unchanged --
    score_frame rejects it on luma anyway, and there is nothing sane left to crop to."""
    w, h = img.size
    if h < 3:
        return img
    col = img.convert("L").resize((1, h), Image.BOX)   # each output pixel = that row's mean luma
    row_means = _pixels(col)
    top = 0
    while top < h and row_means[top] < 12:
        top += 1
    bottom = h
    while bottom > top and row_means[bottom - 1] < 12:
        bottom -= 1
    if bottom - top < 3:
        return img
    return img.crop((0, top, w, bottom)) if (top, bottom) != (0, h) else img


# -------- pipeline (subprocess calls are patched in tests via steps.backdrops.subprocess.run)

def _yt_dlp_download(trailer_id: str, work_dir: Path, fid: str, run=None) -> Path | None:
    run = run or subprocess.run
    template = work_dir / f"{fid}.%(ext)s"
    url = f"https://www.youtube.com/watch?v={trailer_id}"
    cmd = ["yt-dlp", "-f", "bv*[height<=720][ext=mp4]/bv*[height<=720]", "--no-playlist",
           "-o", str(template), url]
    try:
        r = run(cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    if getattr(r, "returncode", 1) != 0:
        return None
    matches = sorted(work_dir.glob(f"{fid}.*"))
    return matches[0] if matches else None


def _ffprobe_duration(video: Path, run=None):
    run = run or subprocess.run
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(video)]
    try:
        r = run(cmd, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return float((r.stdout or "").strip())
    except (TypeError, ValueError):
        return None


def _extract_frame(video: Path, t: float, run=None):
    run = run or subprocess.run
    cmd = ["ffmpeg", "-y", "-ss", f"{max(t, 0):.2f}", "-i", str(video),
           "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"]
    try:
        r = run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    out = getattr(r, "stdout", None)
    if getattr(r, "returncode", 1) != 0 or not out:
        return None
    return out


def _pick_best_frame(video: Path, duration, run=None):
    """-> (best, any_extracted). `best` is (score, PIL.Image, t) for the highest-scoring of
    SAMPLE_COUNT candidates, or None if none scored. `any_extracted` is True as soon as even one
    frame was successfully pulled off the video and decoded -- it is what lets the caller tell
    "every seek itself failed" (transient: ffmpeg/the video is the problem) apart from "frames came
    back fine but score_frame rejected all of them" (rejected: the content is the problem) -- fix
    round 1, review Important #1."""
    if not duration or duration <= 0:
        return None, False
    lo, hi = START_FRAC * duration, END_FRAC * duration
    if hi <= lo:
        hi = lo + 0.5
    step = (hi - lo) / (SAMPLE_COUNT - 1) if SAMPLE_COUNT > 1 else 0
    best = None
    any_extracted = False
    for i in range(SAMPLE_COUNT):
        t = lo + step * i
        blob = _extract_frame(video, t, run=run)
        if not blob:
            continue
        try:
            img = Image.open(io.BytesIO(blob))
            img.load()
            img = img.convert("RGB")
        except Exception:   # noqa: BLE001 - a truncated/corrupt frame is simply not a candidate
            continue
        any_extracted = True
        img = crop_letterbox(img)
        s = score_frame(img)
        if s is None:
            continue
        if best is None or s > best[0]:
            best = (s, img, t)
    return best, any_extracted


def _save_webp(img: Image.Image, out_dir: Path, fid: str):
    """Writes the 1280w/640w WebPs, named by a hash of the chosen frame's JPEG bytes (the brief's own
    convention — a stable, content-addressed name, JPEG chosen only because it is what hashing "the
    chosen frame" means here; the files actually written are WebP). Returns (hash, {1280: name, 640:
    name}, height_of_the_1280w_file)."""
    jbuf = io.BytesIO()
    img.save(jbuf, "JPEG", quality=90)
    h = hashlib.sha1(jbuf.getvalue()).hexdigest()[:10]
    names, h1280 = {}, None
    for w in WIDTHS:
        target_h = max(1, round(img.height * w / img.width))
        resized = img.resize((w, target_h), Image.LANCZOS) if img.width != w else img
        name = f"bd-{fid}-{h}-{w}.webp"
        resized.save(out_dir / name, "WEBP", quality=WEBP_QUALITY, method=6)
        names[w] = name
        if w == 1280:
            h1280 = target_h
    return h, names, h1280


def process_film(fid: str, trailer_id: str, work_dir: Path, out_dir: Path, run=None, forced_t=None):
    """-> ({"trailer", "w1280", "w640", "w", "h", "t"}, None) on success, else (None, kind) where
    kind is "transient" (download/ffprobe failed, or every ffmpeg seek itself failed) or "rejected"
    (frames came back fine, score_frame rejected all of them) -- see the module docstring and
    run()'s use of this to pick a retry TTL. Always deletes whatever it downloaded for this fid,
    success or failure (the caller decides what None means: a cached failure, never a crash — see
    run()).

    `forced_t`, when given (backdrops_override.yaml's `fid: <seconds>` form), skips ffprobe and the
    16-sample scoring loop entirely: exactly that one timestamp is extracted, still letterbox-cropped
    and encoded the normal way, but never scored/rejected -- a human already decided it's clean."""
    work_dir.mkdir(parents=True, exist_ok=True)
    video = None
    try:
        video = _yt_dlp_download(trailer_id, work_dir, fid, run=run)
        if not video or not video.is_file():
            return None, "transient"

        if forced_t is not None:
            blob = _extract_frame(video, forced_t, run=run)
            if not blob:
                return None, "transient"
            try:
                img = Image.open(io.BytesIO(blob))
                img.load()
                img = img.convert("RGB")
            except Exception:   # noqa: BLE001 - a truncated/corrupt frame at the forced timestamp
                return None, "transient"
            img = crop_letterbox(img)
            t = forced_t
        else:
            duration = _ffprobe_duration(video, run=run)
            if not duration or duration <= 0:
                return None, "transient"
            best, any_extracted = _pick_best_frame(video, duration, run=run)
            if not best:
                return None, ("rejected" if any_extracted else "transient")
            _, img, t = best

        h, names, h1280 = _save_webp(img, out_dir, fid)
        return {"trailer": trailer_id, "w1280": f"/posters/{names[1280]}", "w640": f"/posters/{names[640]}",
                "w": 1280, "h": h1280, "t": round(t, 1)}, None
    finally:
        for p in work_dir.glob(f"{fid}.*"):   # the finished file plus any yt-dlp .part/.ytdl leftovers
            try:
                p.unlink()
            except OSError:
                pass


# -------- cache + orchestration

def _load(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _save(path: Path, d: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _parse_iso(s):
    try:
        d = datetime.fromisoformat(str(s))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _fail_is_stale(entry: dict, now_dt) -> bool:
    """A `fail` entry's TTL depends on its `kind` (fix round 1): "transient" retries after 6h, a
    genuine content "rejected" (or an old entry from before this fix, with no `kind` at all) keeps
    the full 7-day TTL -- defaulting an unlabelled entry to the LONGER ttl is the conservative
    choice, so a pre-fix cache never gets hammered by an unintended mass-retry the moment this
    ships."""
    at = _parse_iso(entry.get("fail"))
    ttl = FAIL_TTL_TRANSIENT if entry.get("kind") == "transient" else FAIL_TTL_REJECTED
    return at is None or now_dt - at >= ttl


def _load_overrides(path: Path | None = None) -> dict:
    """fid -> None ("none": force the poster-blur fallback, never attempt this film) | float
    (seconds: skip scoring, take exactly this frame). See backdrops_override.yaml's own header.
    A missing file, unparsable YAML, or a malformed entry is never an error -- just ignored/empty.

    `path` defaults to the MODULE-LEVEL `OVERRIDE_PATH`, read here (not as this function's own
    default argument value, which Python would bind once at import time) so a test's
    `monkeypatch.setattr(steps.backdrops, "OVERRIDE_PATH", ...)` is actually honoured."""
    path = OVERRIDE_PATH if path is None else path
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for fid, v in raw.items():
        if not FID.match(str(fid)):
            continue
        if isinstance(v, str) and v.strip().lower() == "none":
            out[fid] = None
            continue
        try:
            t = float(v)
        except (TypeError, ValueError):
            continue
        if t >= 0:
            out[fid] = t
    return out


def _candidates(data: dict) -> dict:
    """fid -> trailer id, for every film currently showing or coming with a syntactically valid
    trailer id -- `data["films"]` wins a fid collision with `data["coming"]` (the same film showing
    somewhere already has the more current record)."""
    out = {}
    for fid, f in (data.get("films") or {}).items():
        if not FID.match(str(fid)) or f.get("status") == "archived":
            continue
        tid = f.get("trailer")
        if tid and YT.match(str(tid)):
            out[fid] = str(tid)
    for fid, f in (data.get("coming") or {}).items():
        if fid in out or not FID.match(str(fid)):
            continue
        tid = f.get("trailer")
        if tid and YT.match(str(tid)):
            out[fid] = str(tid)
    return out


def run(data: dict, ctx: dict | None = None) -> dict:
    ctx = ctx or {}
    data_dir = Path(ctx.get("data_dir") or (ROOT / "data"))
    cache_path = data_dir / "backdrops.json"

    if ctx.get("offline"):
        # never start yt-dlp/ffmpeg offline -- see the module docstring (the test suite runs every
        # steps/*.py with --offline and forbids reaching the network).
        return {"new": 0, "failed": 0, "cached": len(_load(cache_path)), "offline": True}

    out_dir = data_dir / "posters"
    work_dir = data_dir / "backdrops_work"
    out_dir.mkdir(parents=True, exist_ok=True)

    max_new = DEFAULT_MAX_NEW
    try:
        max_new = int(os.environ.get("CINEMA_BACKDROPS_MAX", DEFAULT_MAX_NEW))
    except ValueError:
        pass
    budget_s = DEFAULT_BUDGET_S
    try:
        budget_s = float(os.environ.get("CINEMA_BACKDROPS_BUDGET_S", DEFAULT_BUDGET_S))
    except ValueError:
        pass

    now_iso = ctx.get("now") or datetime.now(timezone.utc).isoformat()
    now_dt = _parse_iso(now_iso) or datetime.now(timezone.utc)
    cache = _load(cache_path)
    candidates = _candidates(data)
    overrides = _load_overrides()
    t_start = time.monotonic()

    def over_budget() -> bool:
        return (time.monotonic() - t_start) >= budget_s

    new_count = failed = cached = 0
    try:
        for fid, trailer in candidates.items():
            if fid in overrides and overrides[fid] is None:
                # "none": never show a backdrop for this film -- no attempt, no retry, and the
                # marker itself is enough for the prune step below to keep any stale files off disk.
                cache[fid] = {"trailer": trailer, "override": "none"}
                cached += 1
                continue

            forced_t = overrides.get(fid)   # a float here means "take exactly this second"
            entry = cache.get(fid)

            if forced_t is not None:
                if (isinstance(entry, dict) and entry.get("trailer") == trailer
                        and entry.get("override_t") == forced_t and entry.get("w1280")):
                    cached += 1
                    continue   # already extracted at this exact override value
            elif isinstance(entry, dict) and entry.get("trailer") == trailer and entry.get("override") != "none":
                if entry.get("fail"):
                    if not _fail_is_stale(entry, now_dt):
                        cached += 1
                        continue
                    # stale failure: falls through to a fresh attempt below, still subject to the
                    # cap/budget
                elif entry.get("w1280"):
                    cached += 1
                    continue
                # else: a malformed/partial entry (e.g. a leftover "none" marker whose override was
                # just removed) -- fall through and reprocess normally

            if new_count >= max_new or over_budget():
                continue   # left uncached on purpose -- a later run picks it up (the brief's cap/budget)
            new_count += 1
            try:
                result, kind = process_film(fid, trailer, work_dir, out_dir, forced_t=forced_t)
            except Exception as e:   # noqa: BLE001 - one film's failure must never fail the step
                result, kind = None, "transient"   # an unhandled exception is an infra problem, not a content one
                print(f"backdrops: {fid}: {e}", file=sys.stderr)
            if result:
                cache[fid] = {**result, "at": now_iso, **({"override_t": forced_t} if forced_t is not None else {})}
            else:
                cache[fid] = {"trailer": trailer, "fail": now_iso, "kind": kind or "transient",
                              **({"override_t": forced_t} if forced_t is not None else {})}
                failed += 1
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        _save(cache_path, cache)

    # prune: a cache entry for a fid no longer showing/coming, or whose trailer has moved on since
    # this entry was written, is dropped -- and with it, any bd-*.webp file nothing else still wants
    # (same "collect what's kept, delete whatever else is on disk" convention as steps/og.py's own
    # out_dir prune) -- fix round 1, review Minor #3.
    keep_names = set()
    for fid in list(cache):
        entry = cache[fid]
        if not isinstance(entry, dict):
            del cache[fid]
            continue
        current_trailer = candidates.get(fid)
        if current_trailer is None or entry.get("trailer") != current_trailer:
            del cache[fid]
            continue
        for key in ("w1280", "w640"):
            name = entry.get(key)
            if name:
                keep_names.add(os.path.basename(name))
    for p in out_dir.glob("bd-*.webp"):
        if p.name not in keep_names:
            try:
                p.unlink()
            except OSError:
                pass
    _save(cache_path, cache)

    # attach a still-valid, still-on-disk entry onto the film for Kit.backdrop() to read this build
    for fid, f in (data.get("films") or {}).items():
        if fid in overrides and overrides[fid] is None:
            continue   # forced no-backdrop: never attach, however stale a pre-override entry is
        entry = cache.get(fid)
        if not isinstance(entry, dict) or entry.get("fail") or not entry.get("w1280"):
            continue
        if entry.get("trailer") != f.get("trailer"):
            continue   # the trailer changed since this frame was cached: not this film's backdrop any more
        if not ((out_dir / os.path.basename(entry["w1280"])).is_file()
                and (out_dir / os.path.basename(entry["w640"])).is_file()):
            continue   # the cache says so but the file is gone (e.g. VERSION bump, manual cleanup)
        f["backdrop"] = {"w1280": entry["w1280"], "w640": entry["w640"],
                          "w": entry.get("w"), "h": entry.get("h"), "t": entry.get("t")}

    return {"new": new_count, "failed": failed, "cached": cached}
