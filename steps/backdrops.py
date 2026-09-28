"""steps/backdrops.py — the screen's frames: a clean, graded frame from each film's YouTube trailer, a portrait
crop for phones when the source can carry one, 4 spill colours and 3 kept frames (UI redesign Task 1, then
legend W1-D1, MASTER-PLAN §1.6).

For every film currently showing (`data["films"]`, `status != "archived"`) or coming (`data["coming"]`) that
carries a trailer id, most-shown first:

1. **Download** the best video-only SDR format <= 1080p (`FORMAT`, owner default D8: once per film, cached
   forever). W1-D1's probe (2026-09-28, the Fold, tonight's top 10) found 1080p offered and downloadable for
   10 of 10, with no SABR or PO-token failure; `height<=1080` on a scope master can take a *wider* stream
   (2560x1072), which is more active picture, not less. A failed download is retried once with node as
   yt-dlp's JS runtime (the EJS n-challenge solver) when node is on PATH.
2. **Sample** SAMPLE_COUNT frames between 12% and 80% of the runtime. Each is kept only as a 640w analysis copy
   plus its row/column luma profile (the Fold has ~2.5 GB free: sixteen 1080p frames are never held at once).
3. **Find the active picture once per trailer** (`active_box`): a row or column is picture when it is lit
   (mean luma >= BAR_LUMA) in at least ACTIVE_SHARE of the frames that are not black. The old per-frame crop
   cut a dark scene down to its lit rows (resident-evil: a 1280x75 "frame"); one box per trailer can't.
4. **Reject text over the picture** (`text_score`: burned-in subtitles, credits, title cards; a white
   top-hat of max(R,G,B), with each trailer's own subtitle rows learned from its 16 frames), then **score**
   each frame's active picture with `score_frame` (unchanged rules: luma range, a dense bottom band, a title
   card on a flat ground). When no frame passes and some were only too dark, a second pass accepts frames
   down to LUMA_MIN_DARK (a dark film gets a dark frame, which the grade lifts to the night token). Keep the
   best KEEP frames at least KEPT_GAP apart (different shots) — the first is the screen, all three are
   written (for later context picks and the frame game).
5. **Grade** (`grade`, Pillow only): saturation -12 %, then a per-channel curve that lifts black to the night
   token #0F0B0C and rolls white to the screen token #F1EAE0 with square weights (1-x)^2 and x^2, so the
   warm split tone lives in the ends and mid-tones move by about 5 levels (subtle on skin).
6. **Write** per film, content-addressed (every name carries a hash of the graded pixels, because
   `posters.py --upload` ships `data/posters/*.webp` with a year-long immutable cache):
   - the landscape frame at 1280w and 640w (WebP q80), as before;
   - `bd-<fid>-<hash>-p.webp`, **only when the active height >= PORTRAIT_MIN_H (800)**: 2:3 at the source's
     own active height, never resized (so never upscaled; ~536x804 from 1080p scope, 715x1072 from a
     2560x1072 scope stream), placed over WINDOW_STEPS sliding 2:3 windows by detail (`window_x`: the
     in-focus subject) among those `score_frame` accepts, with a centre bias, or by the per-film `x` in backdrops_override.yaml. q72, stepping down to q60, <=
     PORTRAIT_MAX_BYTES; then the **sharpness check**: the variance of a Laplacian of the portrait at display
     scale (PORTRAIT_DISPLAY) must be >= SHARP_MIN_RATIO x that of the 1280w file cropped to the same box.
     A crop that fails either is not written (`p_skip` says why), and phones keep the 1280w landscape with
     `object-fit: cover` at `object-position: <x>` (the same window, so a cover crop and a portrait agree);
   - 4 spill colours from the bottom edge of the landscape frame (`spill`) and of the 2:3 window
     (`spill_p`), left to right in the image's own coordinates.

`<data_dir>/backdrops.json` (old keys kept, W1-D1 keys added):

    {fid: {"trailer", "w1280", "w640", "w": 1280, "h", "t", "at",                    <- as before
           "v": 2, "src": [w, h], "box": [x0, y0, x1, y1], "x": 0..1, "spill": [4 hex], "spill_p": [4 hex],
           "kept": [{"t", "s", "w1280", "w640", "h"}, ...<=3], "sec": <processing seconds>,
           "p", "pw", "ph", "pq", "pkb", "sharp"  |  "p_skip": <why no portrait>}}
    {fid: {"trailer", "fail": <iso>, "kind": "transient" | "rejected", "why": <reason>, "v": 2}}

The film gets `data["films"][fid]["backdrop"] = {"w1280", "w640", "w", "h", "t"}` as before, plus `"x"`,
`"spill"`, `"spill_p"` and, when written, `"p"`, `"pw"`, `"ph"` (W2-P1 serves them; `site_kit` still
validates only the landscape paths, so a consumer of `p` checks it against OUR_BACKDROP and `spill` against
HEX before it lands in markup).

Caching and retries. An entry is reused as long as the film's trailer id and its override are unchanged. A
failure retries after a TTL by `kind` ("transient": the download/ffprobe/every seek failed, 6 h;
"rejected": the video played but no frame passed, 7 days; an old entry with no kind: 7 days) — **except for
tonight's TOP_N films by show count, whose failures retry after FAIL_TTL_TOP (6 h) whatever the kind**:
those are the frames people actually see (Dubai's #1 and #2 had sat on week-long failures). Every failure
records `why` and prints it to stderr (cinema.log); the step's result carries them too (health.json). An
entry written by an older version of this step (`v` < STEP_VERSION: ungraded, <= 720p) stays attached and is
re-made after every missing film, under the same cap, so the channel converges on one look.

Limits, per run: at most CINEMA_BACKDROPS_MAX (env, default DEFAULT_MAX_NEW) films are started; none is
started once CINEMA_BACKDROPS_BUDGET_S (default 480 s, the step cap) has passed, or while the machine has
less than MIN_AVAIL_MB of memory available (Linux `/proc/meminfo`; the Fold runs one heavy process at a
time), or once YouTube has answered with a throttle («Sign in to confirm you're not a bot», HTTP 429): that
film is a transient failure and no other film is started this run. Whatever is left over is picked up by a
later run. The downloaded video is deleted after each film,
success or failure. A single film's failure never fails the step.

Manual override: `<repo root>/backdrops_override.yaml` — `none`, `<seconds>`, or `{t: <seconds>, x: <0..1>}`
(see its header). Orphaned `bd-*.webp` files (no surviving cache entry names them) are deleted after every run.

Offline (`ctx.get("offline")`): no subprocess is started at all — the test suite runs every step offline.

run(data, ctx) -> {"new", "failed", "cached"} (+ "upgraded", "portraits", "why", "mem_mb", "throttled" when set)
                 | {"new": 0, "failed": 0, "cached": n, "offline": True}
"""
from __future__ import annotations

import hashlib
import io
import json
import math
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
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parent.parent
OVERRIDE_PATH = ROOT / "backdrops_override.yaml"

YT = re.compile(r"^[A-Za-z0-9_-]{11}$")   # same shape site_kit.YT validates a trailer id against
FID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,120}$")

STEP_VERSION = 2
# the best video-only SDR stream up to 1080 rows (an HDR stream decoded without tone mapping comes out grey)
FORMAT = ("bv[height<=1080][dynamic_range!^=?HDR][ext=mp4]/bv[height<=1080][dynamic_range!^=?HDR]"
          "/bv*[height<=1080]")
SAMPLE_COUNT = 16
START_FRAC, END_FRAC = 0.12, 0.80
WIDTHS = (1280, 640)
WEBP_QUALITY = 80
WEBP_METHOD = 6          # libwebp's slowest, smallest encode: these files are fetched by every phone
DEFAULT_MAX_NEW = 4      # MASTER-PLAN §6.4: 1080p downloads, so 4 films per hourly run; the rest roll over
DEFAULT_BUDGET_S = 480   # 8 minutes of wall clock spent STARTING new films, per run
MIN_AVAIL_MB = 900       # below this (Linux only) no new film is started this run
TOP_N = 10
FAIL_TTL_TRANSIENT = timedelta(hours=6)    # download/ffprobe/ffmpeg/network trouble -- probably a blip
FAIL_TTL_REJECTED = timedelta(days=7)      # the video played fine, every sampled frame just scored None
FAIL_TTL_TOP = timedelta(hours=6)          # tonight's most-shown films: retried whatever the kind
DOWNLOAD_TIMEOUT = 240
FFPROBE_TIMEOUT = 20
FFMPEG_TIMEOUT = 30

# score_frame thresholds — see the module docstring and docs/superpowers/specs/2026-09-27-ui-redesign-design.md
LUMA_MIN, LUMA_MAX = 35, 200
LUMA_MIN_DARK = 24            # the second pass, only when every frame was rejected for being dark
EDGE_THRESHOLD = 32           # a FIND_EDGES pixel above this counts as "an edge" once binarised
BOTTOM_BAND = (0.78, 1.0)     # the bottom 22%, where a chain burns in Arabic subtitles
SUBTITLE_RATIO, SUBTITLE_FLOOR = 2.2, 0.03
CENTRE_BAND = (0.42, 0.58)    # a centred title-card headline
SURROUND_BANDS = ((0.12, 0.30), (0.70, 0.88))
CENTRE_RATIO, CENTRE_FLOOR = 2.2, 0.05
SURROUND_FLAT_MAX = 0.02      # the title-card check only fires when the surround is actually flat
SCORE_WIDTH = 320             # every measurement below is a statistic, not a coordinate: downsizing
                               # first keeps score_frame phone-cheap without changing what passes

# the active picture (letterbox and pillarbox bars), measured once per trailer
ANALYSIS_WIDTH = 640
BAR_LUMA = 12
ACTIVE_SHARE = 0.3
MIN_ACTIVE_FRAC = 0.4         # a box smaller than this in either direction is not believed: full frame

# kept frames
KEEP = 3
KEPT_GAP_FRAC, KEPT_GAP_MIN_S = 0.08, 4.0

# the house grade: the hall's own lights (MASTER-PLAN §1.5)
NIGHT = (0x0F, 0x0B, 0x0C)
SCREEN = (0xF1, 0xEA, 0xE0)
GRADE_SATURATION = 0.88

# the portrait
PORTRAIT_MIN_H = 800
PORTRAIT_QUALITIES = (72, 66, 60)
PORTRAIT_MAX_BYTES = 70_000
PORTRAIT_DISPLAY = (1080, 1620)   # the phone billboard's 2:3 box: 360 x 540 CSS px at DPR 3
SHARP_MIN_RATIO = 0.9
WINDOW_STEPS = 9
CENTRE_BIAS = 0.35            # a window at either edge counts 0.65x the same window centred
SPILL_BAND = 0.1              # the bottom 10 % of rows


def _small(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    if rgb.width <= SCORE_WIDTH:
        return rgb
    h = max(1, round(SCORE_WIDTH * rgb.height / rgb.width))
    return rgb.resize((SCORE_WIDTH, h))


def _pixels(img: Image.Image) -> list:
    """The image's pixels in row order. Pillow 12 deprecates getdata() for get_flattened_data(); an older
    Pillow (the Fold's Debian one) only has getdata() -- the one place either is called."""
    fn = getattr(img, "get_flattened_data", None)
    return list(fn() if fn else img.getdata())


def _colourfulness(rgb_small: Image.Image) -> float:
    """Hasler-Süsstrunk colourfulness metric on the already-downsized image, in Pillow's C code: rg = R-G and
    yb = (R+G)/2-B are formed as halved, offset L images (ImageChops, so each value is rounded to half a
    level) and read back through ImageStat. The Python loop it replaces cost 54 ms a frame and 25 calls a
    film on the laptop (more on the Fold); the two agree within 1 %."""
    if rgb_small.width * rgb_small.height == 0:
        return 0.0
    r, g, b = rgb_small.convert("RGB").split()
    rg = ImageStat.Stat(ImageChops.subtract(r, g, scale=2.0, offset=128))
    yb = ImageStat.Stat(ImageChops.subtract(ImageChops.add(r, g, scale=2.0), b, scale=2.0, offset=128))
    mean_rg, mean_yb = 2 * (rg.mean[0] - 128), 2 * (yb.mean[0] - 128)
    var_rg, var_yb = 4 * rg.var[0], 4 * yb.var[0]
    return (var_rg + var_yb) ** 0.5 + 0.3 * (mean_rg ** 2 + mean_yb ** 2) ** 0.5


def _judge(img: Image.Image, luma_min: float = LUMA_MIN):
    """-> (score | None, reason | None, mean luma). reason: "tiny" | "dark" | "bright" | "subtitle" | "title"."""
    small = _small(img)
    w, h = small.size
    if w < 4 or h < 4:
        return None, "tiny", 0.0
    gray = small.convert("L")
    luma_mean = ImageStat.Stat(gray).mean[0]
    if luma_mean < luma_min:
        return None, "dark", luma_mean
    if luma_mean > LUMA_MAX:
        return None, "bright", luma_mean

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
        return None, "subtitle", luma_mean   # a dense bottom strip against a quiet frame: a burned-in subtitle line

    centre = density(*CENTRE_BAND)
    surround = statistics.mean(density(*b) for b in SURROUND_BANDS)
    if surround < SURROUND_FLAT_MAX and centre > max(CENTRE_RATIO * surround, CENTRE_FLOOR):
        return None, "title", luma_mean      # bold text on an otherwise flat background: a title card, not a scene

    weight = max(0.35, 1 - abs(luma_mean - 127.5) / 127.5)
    return _colourfulness(small) * weight, None, luma_mean


def score_frame(img: Image.Image, luma_min: float = LUMA_MIN):
    """None = reject. Otherwise colourfulness x a mid-tone weight. See the module docstring for the
    three rejection rules (luma range, burned-in bottom-band subtitles, centred title-card text)."""
    return _judge(img, luma_min)[0]


def crop_letterbox(img: Image.Image) -> Image.Image:
    """Removes rows whose mean luma < 12 from the top and bottom of ONE frame. Kept for callers that hold a
    single frame; the pipeline itself measures the bars once per trailer (`active_box`), because a dark scene
    has dark rows that are picture, not bars. A frame that is black throughout is returned unchanged."""
    w, h = img.size
    if h < 3:
        return img
    col = img.convert("L").resize((1, h), Image.BOX)   # each output pixel = that row's mean luma
    row_means = _pixels(col)
    top = 0
    while top < h and row_means[top] < BAR_LUMA:
        top += 1
    bottom = h
    while bottom > top and row_means[bottom - 1] < BAR_LUMA:
        bottom -= 1
    if bottom - top < 3:
        return img
    return img.crop((0, top, w, bottom)) if (top, bottom) != (0, h) else img


# -------- the active picture, the grade, sharpness, spill, the 2:3 window

def profiles(img: Image.Image):
    """-> (row means, column means) of the frame's luma, at full resolution (BOX-averaged)."""
    g = img.convert("L")
    return _pixels(g.resize((1, g.height), Image.BOX)), _pixels(g.resize((g.width, 1), Image.BOX))


def _span(profs: list, n: int) -> tuple:
    """(start, end) of the lit span along one axis: an index is picture when it is lit (>= BAR_LUMA) in at
    least ACTIVE_SHARE of the frames that are lit anywhere. Nothing believable -> the whole axis."""
    lit_frames = [p for p in profs if p and max(p) >= BAR_LUMA]
    if not lit_frames:
        return 0, n
    need = max(1, math.ceil(ACTIVE_SHARE * len(lit_frames)))
    counts = [0] * n
    for p in lit_frames:
        for i, v in enumerate(p[:n]):
            if v >= BAR_LUMA:
                counts[i] += 1
    idx = [i for i, c in enumerate(counts) if c >= need]
    if not idx:
        return 0, n
    a, b = idx[0], idx[-1] + 1
    if (b - a) < MIN_ACTIVE_FRAC * n:
        return 0, n
    return a, b


def active_box(frame_profiles: list, size: tuple) -> tuple:
    """(x0, y0, x1, y1) of the trailer's active picture from every sampled frame's (rows, cols) profiles."""
    w, h = size
    y0, y1 = _span([r for r, _ in frame_profiles], h)
    x0, x1 = _span([c for _, c in frame_profiles], w)
    return x0, y0, x1, y1


def _grade_lut() -> list:
    lut = []
    for lo, hi in zip(NIGHT, SCREEN):
        for v in range(256):
            x = v / 255
            lut.append(max(0, min(255, round(v + lo * (1 - x) ** 2 - (255 - hi) * x ** 2))))
    return lut


GRADE_LUT = _grade_lut()


def grade(img: Image.Image) -> Image.Image:
    """The house grade (MASTER-PLAN §1.6): saturation -12 %, black -> #0F0B0C, white -> #F1EAE0. The curve
    is monotonic (its slope never drops below 0.66) and every output channel is >= the night token's."""
    return ImageEnhance.Color(img.convert("RGB")).enhance(GRADE_SATURATION).point(GRADE_LUT)


def dark_luma(img: Image.Image, frac: float = 0.05) -> float:
    """Mean luma of the darkest `frac` of the pixels: the grade's measurable floor."""
    hist = img.convert("L").histogram()
    need = max(1, round(frac * sum(hist)))
    got, total = 0, 0.0
    for v, n in enumerate(hist):
        take = min(n, need - got)
        got += take
        total += take * v
        if got >= need:
            break
    return total / need


def night_luma() -> float:
    """The night token's own luma (ITU-R 601, the weights Pillow's "L" uses), unrounded: 12.31."""
    r, g, b = NIGHT
    return 0.299 * r + 0.587 * g + 0.114 * b


# both signs of the Laplacian: Pillow's default scale for a zero-sum kernel is 1 with offset 0, which clips
# every negative response to 0 and measures half an edge
LAPLACIAN = ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)


def sharpness(img: Image.Image, size: tuple = PORTRAIT_DISPLAY) -> float:
    """Variance of the Laplacian of `img` drawn at `size` (display scale). Pillow leaves a 3x3 kernel's outer
    ring of pixels unfiltered (raw luma, not 128 +- an edge), so that ring is cut off before measuring: left
    in, it adds a floor that tracks the picture's brightness, not its detail."""
    g = img.convert("L").resize(size, Image.BICUBIC)
    lap = g.filter(LAPLACIAN)
    return ImageStat.Stat(lap.crop((1, 1, lap.width - 1, lap.height - 1))).var[0]


def spill(img: Image.Image, x0: int = 0, x1: int | None = None) -> list:
    """4 colours of the bottom edge between x0 and x1, left to right, as #rrggbb."""
    w, h = img.size
    x1 = w if x1 is None else x1
    top = min(h - 1, int(h * (1 - SPILL_BAND)))
    out = []
    for i in range(4):
        a = x0 + (x1 - x0) * i // 4
        b = max(a + 1, x0 + (x1 - x0) * (i + 1) // 4)
        r, g, bl = (round(c) for c in ImageStat.Stat(img.crop((a, top, b, h)).convert("RGB")).mean)
        out.append(f"#{r:02x}{g:02x}{bl:02x}")
    return out


def window_x(img: Image.Image, luma_min: float = LUMA_MIN):
    """-> (x, detail | None): where the phone's 2:3 window (full height) sits, x in 0..1 along its travel
    (0 = the image's left edge). Among WINDOW_STEPS positions that `score_frame` accepts (no text band, not
    too dark), the one with the most **detail** (mean FIND_EDGES of a 320 px copy: films keep their subject in
    focus and let the rest go soft), times a centre bias (an edge window counts 1 - CENTRE_BIAS). Detail, not
    colourfulness: on W1-D1's 13 real frames the most colourful window was fire beside Spider-Man's face, the
    teal wall beside the crawlers' spider and the LED wall beside shish-dou's lead. No window passes ->
    (0.5, None)."""
    w, h = img.size
    ww = max(1, round(h * 2 / 3))
    if ww >= w:
        return 0.5, None
    g = img.convert("L")
    if g.width > SCORE_WIDTH:
        g = g.resize((SCORE_WIDTH, max(3, round(g.height * SCORE_WIDTH / g.width))), Image.BOX)
    edges = g.filter(ImageFilter.FIND_EDGES)
    edges = edges.crop((1, 1, edges.width - 1, edges.height - 1))   # the kernel's unfiltered outer ring
    k = edges.width / w
    best = None
    for i in range(WINDOW_STEPS):
        x = i / (WINDOW_STEPS - 1)
        left = round(x * (w - ww))
        if score_frame(img.crop((left, 0, left + ww, h)), luma_min) is None:
            continue
        a, b = round(left * k), max(round(left * k) + 1, round((left + ww) * k))
        d = ImageStat.Stat(edges.crop((a, 0, min(b, edges.width), edges.height))).mean[0]
        d *= 1 - CENTRE_BIAS * abs(x - 0.5) * 2
        key = (d, -abs(x - 0.5))
        if best is None or key > best[0]:
            best = (key, x, d)
    return (0.5, None) if best is None else (best[1], best[2])


# -------- pipeline (subprocess calls are patched in tests via steps.backdrops.subprocess.run)

def _text(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v or ""


def _last_line(s) -> str:
    lines = [ln.strip() for ln in _text(s).splitlines() if ln.strip()]
    errs = [ln for ln in lines if ln.startswith("ERROR")]
    return ((errs or lines or [""])[-1])[:200]


# YouTube's own "slow down" answers: the address is being rate-limited or bot-checked. Retrying (or starting the
# next film) only deepens it, so the run stops starting films for this hour (W1-D1: the laptop was bot-checked
# at 07:01 after ~75 trailer downloads in 70 minutes).
YT_THROTTLED = re.compile(r"not a bot|HTTP Error 429|Too Many Requests|rate.limit", re.I)
THROTTLED_WHY = "download: YouTube is throttling this address"


def _yt_dlp_download(trailer_id: str, work_dir: Path, fid: str, run=None):
    """-> (video path | None, why | None). FORMAT first; on failure once more with node as the JS runtime
    when node is on PATH (yt-dlp enables only deno by default) -- unless YouTube answered with a throttle
    (YT_THROTTLED), which no runtime fixes. yt-dlp's stderr is read as UTF-8 with replacement: on Windows it
    carries cp1252 bytes (a curly apostrophe in «Sign in to confirm you're not a bot»), which crashed
    subprocess's reader thread under text=True and lost the reason."""
    run = run or subprocess.run
    template = work_dir / f"{fid}.%(ext)s"
    url = f"https://www.youtube.com/watch?v={trailer_id}"
    base = ["-f", FORMAT, "--no-playlist", "--no-progress", "-o", str(template), url]
    attempts = [["yt-dlp", *base]]
    if shutil.which("node"):
        attempts.append(["yt-dlp", "--js-runtimes", "node", *base])
    why = None
    for cmd in attempts:
        try:
            r = run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=DOWNLOAD_TIMEOUT)
        except subprocess.TimeoutExpired:
            why = f"download: timed out after {DOWNLOAD_TIMEOUT}s"
            continue
        except (OSError, subprocess.SubprocessError) as e:
            why = f"download: {type(e).__name__}: {e}"[:200]
            continue
        if getattr(r, "returncode", 1) != 0:
            err = _last_line(getattr(r, "stderr", ""))
            why = "download: " + (err or f"yt-dlp exit {getattr(r, 'returncode', '?')}")
            if YT_THROTTLED.search(_text(getattr(r, "stderr", ""))):
                return None, f"{THROTTLED_WHY} ({err[:120]})"
            continue
        matches = sorted(p for p in work_dir.glob(f"{fid}.*") if not p.name.endswith((".part", ".ytdl")))
        if matches:
            return matches[0], None
        why = "download: yt-dlp exited 0 but wrote no file"
    return None, why


def _ffprobe_duration(video: Path, run=None):
    run = run or subprocess.run
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(video)]
    try:
        r = run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=FFPROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return float(_text(r.stdout).strip())
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


def _decode(blob):
    try:
        img = Image.open(io.BytesIO(blob))
        img.load()
        return img.convert("RGB")
    except Exception:   # noqa: BLE001 - a truncated/corrupt frame is simply not a candidate
        return None


def _frame_at(video: Path, t: float, run=None):
    blob = _extract_frame(video, t, run=run)
    return _decode(blob) if blob else None


def _times(duration) -> list:
    lo, hi = START_FRAC * duration, END_FRAC * duration
    if hi <= lo:
        hi = lo + 0.5
    step = (hi - lo) / (SAMPLE_COUNT - 1) if SAMPLE_COUNT > 1 else 0
    return [lo + step * i for i in range(SAMPLE_COUNT)]


def _sample(video: Path, times: list, run=None) -> list:
    """Each decodable frame as {"t", "size", "prof", "small"}: only a 640w copy and the luma profiles are
    kept, never the full frame."""
    out = []
    for t in times:
        img = _frame_at(video, t, run=run)
        if img is None:
            continue
        sw = min(ANALYSIS_WIDTH, img.width)
        small = img.resize((sw, max(1, round(img.height * sw / img.width))), Image.BOX) if sw != img.width else img
        out.append({"t": t, "size": img.size, "prof": profiles(img), "small": small})
        del img
    return out


def _encode_webp(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=quality, method=WEBP_METHOD)
    return buf.getvalue()


def _hash(img: Image.Image) -> str:
    """Content address of the graded pixels (a JPEG of them, as the first version named its files)."""
    jbuf = io.BytesIO()
    img.save(jbuf, "JPEG", quality=90)
    return hashlib.sha1(jbuf.getvalue()).hexdigest()[:10]


def _save_webp(img: Image.Image, out_dir: Path, fid: str):
    """Writes the 1280w/640w WebPs of an (already graded) frame, named by a hash of its pixels. Returns
    (hash, {1280: name, 640: name}, height of the 1280w file, the 1280w file's bytes)."""
    h = _hash(img)
    names, h1280, b1280 = {}, None, None
    for w in WIDTHS:
        target_h = max(1, round(img.height * w / img.width))
        resized = img.resize((w, target_h), Image.LANCZOS) if img.width != w else img
        name = f"bd-{fid}-{h}-{w}.webp"
        blob = _encode_webp(resized, WEBP_QUALITY)
        (out_dir / name).write_bytes(blob)
        names[w] = name
        if w == 1280:
            h1280, b1280 = target_h, blob
    return h, names, h1280, b1280


def portrait(full: Image.Image, x: float, land1280: Image.Image):
    """-> (image, webp bytes, quality, sharpness ratio, None) | (None, None, None, ratio|None, why).

    `full` is the graded active picture at the source's own resolution. The crop is 2:3 at its full
    height and is never resized, so it can't be upscaled. `land1280` is the decoded 1280w file, the thing a
    phone would otherwise stretch over the same box."""
    w, h = full.size
    if h < PORTRAIT_MIN_H:
        return None, None, None, None, f"active height {h} < {PORTRAIT_MIN_H}"
    pw = round(h * 2 / 3)
    if pw > w:
        return None, None, None, None, f"active picture {w}x{h} is narrower than 2:3"
    left = round(x * (w - pw))
    crop = full.crop((left, 0, left + pw, h))
    s = land1280.width / w
    lbox = (round(left * s), 0, round((left + pw) * s), land1280.height)
    base = sharpness(land1280.crop(lbox))
    for q in PORTRAIT_QUALITIES:
        blob = _encode_webp(crop, q)
        if len(blob) > PORTRAIT_MAX_BYTES:
            continue
        ratio = sharpness(_decode(blob)) / base if base > 0 else float("inf")
        if ratio >= SHARP_MIN_RATIO:
            return crop, blob, q, ratio, None
        return None, None, None, ratio, f"soft: {ratio:.2f}x the 1280w crop at q{q}"
    return None, None, None, None, f"over {PORTRAIT_MAX_BYTES} B even at q{PORTRAIT_QUALITIES[-1]}"


# -------- text laid over the picture: burned-in subtitles, credits, title cards
# Measured on W1-D1's 192 sampled frames from tonight's 12 most-shown trailers (7 of them carry Arabic
# subtitles burned in by the regional distributor): score_frame's bottom-band edge test missed most of them on
# a busy frame (heart-of-the-beast's chosen frame had a subtitle), and a title card over a dark scene passed
# the flat-surround rule (resident-evil's «مخرج "ويبونز"» card). Text is a thin stroke much brighter than
# what is 2 px around it, in any colour: a white top-hat of the frame's max(R,G,B) at 5 px finds it. A
# trailer's subtitles sit on the same rows in every frame, so rows lit by strokes in >= SUB_FRAMES frames
# become that trailer's subtitle rows, and there a much fainter line counts.
TEXT_KERNEL, TEXT_STROKE = 5, 56
TEXT_BINS = 50                    # row bins of 2 % of the active height
SUB_FROM = 0.75                   # subtitles live in the bottom quarter
SUB_STRONG, SUB_FRAMES, SUB_FLAG = 0.03, 3, 0.012
TITLE_FLAG, BOTTOM_FLAG = 0.035, 0.025
TEXT_PENALTY = 10                 # a frame that passes is still ranked down by its text-likeness


def stroke_profile(img: Image.Image) -> list:
    """Share of stroke pixels in each of TEXT_BINS row bins."""
    r, g, b = img.convert("RGB").split()
    v = ImageChops.lighter(ImageChops.lighter(r, g), b)
    opened = v
    for f in [ImageFilter.MinFilter(3)] * (TEXT_KERNEL // 2) + [ImageFilter.MaxFilter(3)] * (TEXT_KERNEL // 2):
        opened = opened.filter(f)   # a 5x5 opening as two 3x3 passes each way: the same image, 40 % faster
    strokes = ImageChops.subtract(v, opened).point(lambda p: 255 if p >= TEXT_STROKE else 0)
    return [p / 255 for p in _pixels(strokes.resize((1, TEXT_BINS), Image.BOX))]


def text_band(prof: list, hb: int = 2) -> tuple:
    """-> (score, y): the densest band of `hb` bins minus twice its neighbourhood (a line of text is dense
    where the rows around it are not), and where it is (0 top .. 1 bottom)."""
    n = len(prof)
    best = (0.0, 0.0)
    for y in range(0, n - hb + 1):
        d = sum(prof[y:y + hb]) / hb
        around = prof[max(0, y - 2 * hb):max(0, y - hb)] + prof[min(n, y + 2 * hb):min(n, y + 3 * hb)]
        s = d - 2 * (sum(around) / len(around) if around else 0)
        if s > best[0]:
            best = (s, (y + hb / 2) / n)
    return best


def subtitle_rows(profs: list) -> set:
    n = TEXT_BINS
    lo = int(SUB_FROM * n)
    rows = {i for i in range(lo, n) if sum(1 for p in profs if p[i] >= SUB_STRONG) >= SUB_FRAMES}
    return rows | {i + d for i in rows for d in (-1, 1) if lo <= i + d < n}


def text_score(prof: list, rows: set) -> tuple:
    """-> (text-likeness for ranking, reason when it is text, else None)."""
    sub = max((prof[i] for i in rows), default=0.0)
    band, y = text_band(prof)
    if rows and sub >= SUB_FLAG:
        return sub, "subtitle"
    if band >= TITLE_FLAG or (y >= SUB_FROM - 0.05 and band >= BOTTOM_FLAG):
        return band, "text"
    return max(sub, band), None


def _pick(samples: list, duration) -> tuple:
    """-> (ranked [(score, sample)], luma floor used, rejection summary). Text over the picture is rejected
    first (`text_score`); then score_frame; a dark trailer gets a second pass at LUMA_MIN_DARK."""
    profs = [stroke_profile(s["crop"]) for s in samples]
    rows = subtitle_rows(profs)
    judged = []
    for s, prof in zip(samples, profs):
        texty, why = text_score(prof, rows)
        s["texty"] = texty
        if why:
            judged.append((s, None, why, ImageStat.Stat(_small(s["crop"]).convert("L")).mean[0]))
        else:
            judged.append((s, *_judge(s["crop"])))
    penalty = lambda s: max(0.5, 1 - TEXT_PENALTY * s["texty"])
    ok = [(sc * penalty(s), s) for s, sc, _, _ in judged if sc is not None]
    floor = LUMA_MIN
    if not ok and any(reason == "dark" for _, _, reason, _ in judged):
        # every other rule still applies in this pass: only the luma floor moves
        floor = LUMA_MIN_DARK
        ok = [(sc * penalty(s), s) for s, _, reason, _ in judged if reason == "dark"
              for sc in [score_frame(s["crop"], LUMA_MIN_DARK)] if sc is not None]
    ok.sort(key=lambda p: (-p[0], p[1]["t"]))
    gap = max(KEPT_GAP_MIN_S, KEPT_GAP_FRAC * (duration or 0))
    kept = []
    for sc, s in ok:
        if all(abs(s["t"] - k["t"]) >= gap for _, k in kept):
            kept.append((sc, s))
        if len(kept) == KEEP:
            break
    summary = None
    if not ok:
        by = {}
        for _, _, reason, luma in judged:
            by.setdefault(reason, []).append(luma)
        parts = []
        for reason, lumas in sorted(by.items(), key=lambda kv: -len(kv[1])):
            label = {"dark": "too dark", "bright": "too bright", "subtitle": "subtitles",
                     "title": "title card", "text": "text over the picture", "tiny": "tiny"}.get(reason, reason)
            if reason in ("dark", "bright"):
                label += f" (mean luma {min(lumas):.0f}-{max(lumas):.0f})"
            parts.append(f"{len(lumas)} {label}")
        summary = f"all {len(judged)} frames rejected: " + ", ".join(parts)
    return kept, floor, summary


def process_film(fid: str, trailer_id: str, work_dir: Path, out_dir: Path, run=None, forced_t=None, forced_x=None):
    """-> (entry, None, None) on success, else (None, kind, why): kind "transient" (download/ffprobe failed,
    or every ffmpeg seek failed) or "rejected" (frames came back fine, every one was rejected). Always deletes
    whatever it downloaded for this fid.

    `forced_t` (backdrops_override.yaml) skips scoring: exactly that timestamp is the screen, still cropped to
    the trailer's active box (measured on 6 more frames) and graded, never rejected. `forced_x` places the
    portrait window by hand."""
    t0 = time.monotonic()
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        video, why = _yt_dlp_download(trailer_id, work_dir, fid, run=run)
        if not video or not video.is_file():
            return None, "transient", why or "download: no file"
        duration = _ffprobe_duration(video, run=run)

        if forced_t is None:
            if not duration or duration <= 0:
                return None, "transient", "ffprobe: no duration"
            times = _times(duration)
        else:
            times = [forced_t] + ([duration * (START_FRAC + (END_FRAC - START_FRAC) * i / 5) for i in range(6)]
                                  if duration and duration > 0 else [])
        samples = _sample(video, times, run=run)
        if forced_t is not None and (not samples or samples[0]["t"] != forced_t):
            return None, "transient", f"ffmpeg: no frame at the override time {forced_t}s"
        if not samples:
            return None, "transient", f"ffmpeg: no frame decoded at any of {len(times)} seeks"

        size = samples[0]["size"]
        same = [s for s in samples if s["size"] == size]
        box = active_box([s["prof"] for s in same], size)
        for s in samples:
            k = s["small"].width / s["size"][0]
            x0, y0, x1, y1 = (round(v * k) for v in (box if s["size"] == size else (0, 0, *s["size"])))
            s["crop"] = s["small"].crop((x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)))

        if forced_t is not None:
            kept, floor = [(None, samples[0])], LUMA_MIN
        else:
            kept, floor, summary = _pick(samples, duration)
            if not kept:
                return None, "rejected", summary

        entry, extras = None, []
        for sc, s in kept:
            full = _frame_at(video, s["t"], run=run)
            if full is None:
                continue
            if full.size != size:
                full = full.resize(size, Image.LANCZOS)
            full = grade(full.crop(box))
            h, names, h1280, b1280 = _save_webp(full, out_dir, fid)
            rec = {"t": round(s["t"], 1), "s": None if sc is None else round(sc, 1),
                   "w1280": f"/posters/{names[1280]}", "w640": f"/posters/{names[640]}", "h": h1280}
            if entry is not None:
                extras.append(rec)
                del full
                continue
            land = _decode(b1280)
            if forced_x is not None:
                x = forced_x
            else:
                # on the graded 1280w file, the picture a phone is shown: on the ungraded analysis copy the
                # highlights the grade rolls off (shish-dou's LED strip) out-voted the lead (Fold, 07:33)
                x, _ = window_x(land, floor)
            ww = round(land.height * 2 / 3)
            left = round(x * max(0, land.width - ww))
            entry = {"trailer": trailer_id, "w1280": rec["w1280"], "w640": rec["w640"], "w": 1280, "h": h1280,
                     "t": rec["t"], "v": STEP_VERSION, "src": list(size), "box": list(box), "x": round(x, 3),
                     "spill": spill(land), "spill_p": spill(land, left, min(land.width, left + ww))}
            if floor == LUMA_MIN_DARK:
                entry["dark"] = True   # chosen in the dark-trailer pass
            pimg, pblob, q, ratio, skip = portrait(full, x, land)
            if pblob:
                pname = f"bd-{fid}-{_hash(pimg)}-p.webp"
                (out_dir / pname).write_bytes(pblob)
                entry.update({"p": f"/posters/{pname}", "pw": pimg.width, "ph": pimg.height, "pq": q,
                              "pkb": round(len(pblob) / 1000, 1), "sharp": round(ratio, 2)})
            else:
                entry["p_skip"] = skip
                if ratio is not None:
                    entry["sharp"] = round(ratio, 2)
            extras.append(rec)
            del full
        if entry is None:
            return None, "transient", "ffmpeg: the chosen frames could not be decoded again"
        entry["kept"] = extras
        entry["sec"] = round(time.monotonic() - t0, 1)
        return entry, None, None
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


def _fail_is_stale(entry: dict, now_dt, top: bool = False, at_key: str = "fail", kind_key: str = "kind") -> bool:
    """A failure's TTL: tonight's top films retry after FAIL_TTL_TOP whatever the kind; otherwise
    "transient" after 6 h, and "rejected" (or an old entry with no kind: the conservative default, so an old
    cache is never hammered) after 7 days."""
    at = _parse_iso(entry.get(at_key))
    if top:
        ttl = FAIL_TTL_TOP
    else:
        ttl = FAIL_TTL_TRANSIENT if entry.get(kind_key) == "transient" else FAIL_TTL_REJECTED
    return at is None or now_dt - at >= ttl


def _load_overrides(path: Path | None = None) -> dict:
    """fid -> None ("none": no backdrop, never attempted) | {"t": seconds | None, "x": 0..1 | None}. See
    backdrops_override.yaml's own header. A missing file, unparsable YAML or a malformed entry is never an
    error, just ignored.

    `path` defaults to the MODULE-LEVEL `OVERRIDE_PATH`, read here (not as a default argument value, which
    Python would bind once at import time) so a test's monkeypatch is honoured."""
    path = OVERRIDE_PATH if path is None else path
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(raw, dict):
        return {}

    def num(v, lo, hi):
        if isinstance(v, bool):
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if lo <= f <= hi else None

    out = {}
    for fid, v in raw.items():
        if not FID.match(str(fid)):
            continue
        if isinstance(v, str) and v.strip().lower() == "none":
            out[fid] = None
        elif isinstance(v, dict):
            t, x = num(v.get("t"), 0, math.inf), num(v.get("x"), 0, 1)
            if t is not None or x is not None:
                out[fid] = {"t": t, "x": x}
        else:
            t = num(v, 0, math.inf)
            if t is not None:
                out[fid] = {"t": t, "x": None}
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


def show_counts(data: dict) -> dict:
    counts = {}
    for s in data.get("shows") or []:
        fid = s.get("film") if isinstance(s, dict) else None
        if fid:
            counts[fid] = counts.get(fid, 0) + 1
    return counts


def _mem_available_mb():
    """MemAvailable from /proc/meminfo in MB, or None where there is no such file (Windows, macOS)."""
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _state(entry, trailer: str, ov, now_dt, top: bool) -> str:
    """'hit' (use as is) | 'work' (nothing usable: make it) | 'upgrade' (usable, made by an older version)."""
    if not isinstance(entry, dict) or entry.get("trailer") != trailer or entry.get("override") == "none":
        return "work"
    want_t, want_x = (ov or {}).get("t"), (ov or {}).get("x")
    if entry.get("override_t") != want_t or entry.get("override_x") != want_x:
        return "work"
    if entry.get("fail"):
        return "work" if _fail_is_stale(entry, now_dt, top) else "hit"
    if not entry.get("w1280"):
        return "work"
    if (entry.get("v") or 1) < STEP_VERSION:
        if entry.get("up_fail") and not _fail_is_stale(entry, now_dt, top, "up_fail", "up_kind"):
            return "hit"
        return "upgrade"
    return "hit"


def _entry_names(entry: dict) -> set:
    names = set()
    for key in ("w1280", "w640", "p"):
        if entry.get(key):
            names.add(os.path.basename(str(entry[key])))
    for k in entry.get("kept") or []:
        if isinstance(k, dict):
            for key in ("w1280", "w640"):
                if k.get(key):
                    names.add(os.path.basename(str(k[key])))
    return names


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
    counts = show_counts(data)
    films = data.get("films") or {}
    order = sorted(candidates, key=lambda f: (-counts.get(f, 0), f))
    top = set(sorted((f for f in candidates if f in films and counts.get(f)),
                     key=lambda f: (-counts[f], f))[:TOP_N])
    t_start = time.monotonic()

    new_count = failed = cached = upgraded = 0
    why, mem_mb = {}, None
    work, upgrades = [], []
    for fid in order:
        trailer = candidates[fid]
        if fid in overrides and overrides[fid] is None:
            # "none": never show a backdrop for this film -- no attempt, no retry, and the marker itself is
            # enough for the prune step below to keep any stale files off disk.
            cache[fid] = {"trailer": trailer, "override": "none"}
            cached += 1
            continue
        state = _state(cache.get(fid), trailer, overrides.get(fid), now_dt, fid in top)
        if state == "hit":
            cached += 1
        elif state == "work":
            work.append(fid)
        else:
            upgrades.append(fid)

    throttled = False

    def blocked() -> bool:
        nonlocal mem_mb
        if throttled or new_count >= max_new or (time.monotonic() - t_start) >= budget_s:
            return True
        avail = _mem_available_mb()
        if avail is not None and avail < MIN_AVAIL_MB:
            mem_mb = avail
            return True
        return False

    try:
        for fid, is_upgrade in [(f, False) for f in work] + [(f, True) for f in upgrades]:
            if blocked():
                if is_upgrade:
                    cached += 1   # its older frame stays attached; a later run re-makes it
                continue          # left uncached on purpose -- a later run picks it up
            trailer = candidates[fid]
            ov = overrides.get(fid) or {}
            new_count += 1
            try:
                result, kind, reason = process_film(fid, trailer, work_dir, out_dir,
                                                    forced_t=ov.get("t"), forced_x=ov.get("x"))
            except Exception as e:   # noqa: BLE001 - one film's failure must never fail the step
                result, kind, reason = None, "transient", f"exception: {type(e).__name__}: {e}"[:200]
            marks = {k: v for k, v in (("override_t", ov.get("t")), ("override_x", ov.get("x"))) if v is not None}
            if result:
                cache[fid] = {**result, "at": now_iso, **marks}
                upgraded += is_upgrade
                continue
            failed += 1
            why[fid] = reason
            throttled = throttled or str(reason).startswith(THROTTLED_WHY)
            print(f"backdrops: {fid}: {reason}", file=sys.stderr)
            if is_upgrade:
                cache[fid] = {**cache[fid], "up_fail": now_iso, "up_kind": kind or "transient", "up_why": reason}
            else:
                cache[fid] = {"trailer": trailer, "fail": now_iso, "kind": kind or "transient", "why": reason,
                              "v": STEP_VERSION, **marks}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        _save(cache_path, cache)

    # prune: a cache entry for a fid no longer showing/coming, or whose trailer has moved on since this entry
    # was written, is dropped -- and with it every bd-*.webp file no surviving entry names (the landscape
    # pair, the portrait and the kept frames), the "collect what's kept, delete the rest" convention of
    # steps/og.py.
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
        keep_names |= _entry_names(entry)
    for p in out_dir.glob("bd-*.webp"):
        if p.name not in keep_names:
            try:
                p.unlink()
            except OSError:
                pass
    _save(cache_path, cache)

    # attach a still-valid, still-on-disk entry onto the film for Kit.backdrop() to read this build
    portraits = 0
    for fid, f in films.items():
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
        bd = {"w1280": entry["w1280"], "w640": entry["w640"], "w": entry.get("w"), "h": entry.get("h"),
              "t": entry.get("t")}
        for key in ("x", "spill", "spill_p"):
            if entry.get(key) is not None:
                bd[key] = entry[key]
        if entry.get("p") and (out_dir / os.path.basename(entry["p"])).is_file():
            bd.update({"p": entry["p"], "pw": entry.get("pw"), "ph": entry.get("ph")})
            portraits += 1
        f["backdrop"] = bd

    out = {"new": new_count, "failed": failed, "cached": cached}
    if upgraded:
        out["upgraded"] = upgraded
    if portraits:
        out["portraits"] = portraits
    if why:
        out["why"] = why
    if mem_mb is not None:
        out["mem_mb"] = mem_mb
    if throttled:
        out["throttled"] = True
    return out
