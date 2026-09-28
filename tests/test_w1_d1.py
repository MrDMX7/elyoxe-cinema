"""W1-D1 (legend MASTER-PLAN §1.6, §5.2): frames sharper, graded, portrait.

Every test here drives steps/backdrops.py with yt-dlp/ffprobe/ffmpeg mocked (never a real network call or
subprocess): a fake ffmpeg answers each `-ss` with a synthetic frame of a chosen source size, letterbox and
content, so the acceptance criteria are checked on the pipeline's real image code (Pillow only).
"""
import functools
import io
import json
import math
import os
import random
import re
import sys
import warnings

import pytest
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import steps.backdrops as bd  # noqa: E402

NOW = "2026-09-28T12:00:00+00:00"
HEX = re.compile(r"^#[0-9a-f]{6}$")


def _fast(monkeypatch, samples=4):
    """Orchestration tests: fewer samples, one kept frame, libwebp's quickest encode."""
    monkeypatch.setattr(bd, "SAMPLE_COUNT", samples)
    monkeypatch.setattr(bd, "KEEP", 1)
    monkeypatch.setattr(bd, "WEBP_METHOD", 0)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """No real override file, no real memory reading, no node on PATH unless a test says so."""
    monkeypatch.setattr(bd, "OVERRIDE_PATH", tmp_path / "backdrops_override.yaml")
    monkeypatch.setattr(bd, "_mem_available_mb", lambda: None)
    monkeypatch.setattr(bd.shutil, "which", lambda name: None)


# -------- synthetic trailers

@functools.lru_cache(maxsize=None)
def _scene(w, h, seed, luma=1.0):
    """A photographic-ish frame: a two-colour gradient, large blobs, and small blobs a little lighter or
    darker than what they sit on (texture that survives WebP, like leaves or fabric; never a bright speck,
    which is what a stroke of text is made of) -- detail at every
    scale, and no thin bright strokes (so it is not text)."""
    rnd = random.Random(seed)
    top = tuple(rnd.randrange(40, 200) for _ in range(3))
    bot = tuple(rnd.randrange(40, 200) for _ in range(3))
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * k) for a, b in zip(top, bot)))
    for _ in range(40):
        cx, cy, r = rnd.randrange(w), rnd.randrange(h), rnd.randrange(w // 30, w // 8)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(rnd.randrange(30, 220) for _ in range(3)))
    s = max(1, w // 192)
    for _ in range(w * h // (60 * s * s)):
        cx, cy, r = rnd.randrange(w), rnd.randrange(h), rnd.randrange(2 * s, 6 * s)
        f = rnd.choice((0.78, 0.9, 1.1))   # at most ~50 levels from its ground: under TEXT_STROKE
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=tuple(max(0, min(255, round(v * f))) for v in img.getpixel((cx, cy))))
    if luma != 1.0:
        img = img.point(lambda v: round(v * luma))
    return img


@functools.lru_cache(maxsize=None)
def _frame_png(w, h, bar, seed, luma=1.0, subtitle=False):
    """A frame of a (w x h) container with `bar` black rows top and bottom (a scope picture), as PNG bytes."""
    canvas = Image.new("RGB", (w, h), (0, 0, 0))
    pic = _scene(w, h - 2 * bar, seed, luma)
    if subtitle:
        pic = _with_subtitle(pic)
    canvas.paste(pic, (0, bar))
    buf = io.BytesIO()
    canvas.save(buf, "PNG", compress_level=1)
    return buf.getvalue()


def _land(full):
    """The 1280w file as the pipeline writes and reads it back: LANCZOS, WebP q80, decoded."""
    small = full.resize((1280, round(full.height * 1280 / full.width)), Image.LANCZOS)
    return bd._decode(bd._encode_webp(small, bd.WEBP_QUALITY))


def _busy(img):
    """A chain-link fence in front of the scene: dark 1 px lines every 6 px, edges on every row."""
    img = img.copy()
    d = ImageDraw.Draw(img)
    w, h = img.size
    for x in range(0, w, 6):
        d.line([(x, 0), (x, h)], fill=(25, 25, 25))
    for y in range(0, h, 6):
        d.line([(0, y), (w, y)], fill=(25, 25, 25))
    return img


def _with_subtitle(img, rows=(0.86, 0.93), colour=(245, 245, 245)):
    """A burned-in subtitle line: glyph-like 2 px white strokes in a centred band near the bottom."""
    img = img.copy()
    w, h = img.size
    d = ImageDraw.Draw(img)
    y0, y1 = round(h * rows[0]), round(h * rows[1])
    sw = max(2, w // 320)
    for x in range(round(w * 0.25), round(w * 0.75), sw * 4):
        d.rectangle([x, y0, x + sw - 1, y1], fill=colour)
        d.rectangle([x, (y0 + y1) // 2, x + sw * 3, (y0 + y1) // 2 + sw - 1], fill=colour)
    return img


class _Result:
    def __init__(self, returncode=0, stdout=b"", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _fake(size=(1920, 1080), bar=138, luma=1.0, duration=100.0, subtitled=(), fail_download=0, calls=None):
    """A stand-in for subprocess.run: yt-dlp writes a stub video (failing the first `fail_download` calls),
    ffprobe prints `duration`, ffmpeg answers `-ss t` with a synthetic frame (one scene per whole second,
    subtitles on the seconds in `subtitled`)."""
    state = {"dl": 0}

    def run(cmd, **kw):
        if calls is not None:
            calls.append(list(cmd))
        prog = os.path.basename(str(cmd[0])).lower()
        if prog.startswith("yt-dlp"):
            state["dl"] += 1
            if state["dl"] <= fail_download:
                return _Result(1, stderr="WARNING: x\nERROR: [youtube] abc: Requested format is not available")
            path = cmd[cmd.index("-o") + 1].replace("%(ext)s", "mp4")
            with open(path, "wb") as f:
                f.write(b"stub")
            return _Result(0)
        if prog.startswith("ffprobe"):
            return _Result(0, stdout=f"{duration}\n")
        if prog.startswith("ffmpeg"):
            t = float(cmd[cmd.index("-ss") + 1])
            sec = int(t)
            return _Result(0, stdout=_frame_png(size[0], size[1], bar, sec, luma, sec in subtitled))
        raise AssertionError(f"unexpected subprocess {cmd}")
    return run


def _films(*fids, shows=None):
    data = {"films": {f: {"status": "showing", "trailer": (f.upper().replace("-", "") + "X" * 11)[:11]}
                      for f in fids}, "coming": {}, "shows": []}
    for fid, n in (shows or {}).items():
        data["shows"] += [{"film": fid}] * n
    return data


def _run(tmp_path, data, now=NOW):
    return bd.run(data, {"data_dir": str(tmp_path), "now": now})


def _cache(tmp_path):
    return json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))


def _file(tmp_path, url):
    return tmp_path / "posters" / os.path.basename(url)


# -------- 1. the selector (D8), and the node retry

def test_selector_asks_for_the_best_sdr_video_only_stream_up_to_1080(tmp_path, monkeypatch):
    calls = []
    _fast(monkeypatch)
    monkeypatch.setattr(bd.subprocess, "run", _fake(size=(640, 360), bar=0, calls=calls))
    _run(tmp_path, _films("film-a"))
    dl = next(c for c in calls if os.path.basename(c[0]).startswith("yt-dlp"))
    fmt = dl[dl.index("-f") + 1]
    assert fmt == bd.FORMAT
    assert fmt.startswith("bv[height<=1080]") and "dynamic_range!^=?HDR" in fmt and "720" not in fmt


def test_a_failed_download_is_retried_once_with_node_as_the_js_runtime(tmp_path, monkeypatch):
    calls = []
    _fast(monkeypatch)
    monkeypatch.setattr(bd.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    monkeypatch.setattr(bd.subprocess, "run", _fake(size=(640, 360), bar=0, fail_download=1, calls=calls))
    r = _run(tmp_path, _films("film-a"))
    assert r["new"] == 1 and r["failed"] == 0
    dls = [c for c in calls if os.path.basename(c[0]).startswith("yt-dlp")]
    assert len(dls) == 2 and "--js-runtimes" not in dls[0] and dls[1][1:3] == ["--js-runtimes", "node"]


def test_without_node_a_failed_download_logs_yt_dlps_own_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bd.subprocess, "run", _fake(fail_download=5))
    r = _run(tmp_path, _films("film-a"))
    why = "download: ERROR: [youtube] abc: Requested format is not available"
    assert r["why"] == {"film-a": why}
    assert _cache(tmp_path)["film-a"]["why"] == why and _cache(tmp_path)["film-a"]["kind"] == "transient"
    assert f"backdrops: film-a: {why}" in capsys.readouterr().err


def test_a_youtube_throttle_stops_the_run_and_skips_the_node_retry(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(bd.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)

    def run(cmd, **kw):
        calls.append(list(cmd))
        return _Result(1, stderr="ERROR: [youtube] abc: Sign in to confirm you’re not a bot. Use --cookies")
    monkeypatch.setattr(bd.subprocess, "run", run)
    r = _run(tmp_path, _films("film-a", "film-b", shows={"film-a": 9, "film-b": 3}))
    assert r["new"] == 1 and r["failed"] == 1 and r["throttled"] is True
    assert r["why"]["film-a"].startswith(bd.THROTTLED_WHY)
    assert len(calls) == 1                                   # no node retry, no second film
    assert _cache(tmp_path)["film-a"]["kind"] == "transient" and "film-b" not in _cache(tmp_path)


def test_a_timed_out_download_is_not_retried_with_node(tmp_path, monkeypatch):
    """Review M4: no JS runtime fixes a slow link, and a second 240 s wait held one film for 480 s."""
    import subprocess as sp
    calls = []
    monkeypatch.setattr(bd.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)

    def run(cmd, **kw):
        calls.append(list(cmd))
        raise sp.TimeoutExpired(cmd, kw.get("timeout"))
    video, why = bd._yt_dlp_download("AAAAAAAAAAA", tmp_path, "film-a", run=run)
    assert video is None and why == f"download: timed out after {bd.DOWNLOAD_TIMEOUT}s" and len(calls) == 1


def test_when_both_attempts_fail_the_first_reason_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(bd.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    errs = iter(["ERROR: [youtube] abc: Requested format is not available", "ERROR: node exploded"])
    video, why = bd._yt_dlp_download("AAAAAAAAAAA", tmp_path, "film-a",
                                     run=lambda cmd, **kw: _Result(1, stderr=next(errs)))
    assert video is None and why == "download: ERROR: [youtube] abc: Requested format is not available"


def test_yt_dlps_non_utf8_stderr_is_read_not_lost(tmp_path):
    """On Windows yt-dlp writes cp1252 (0x92, a curly apostrophe): text=True alone crashed subprocess's reader
    thread and the reason came back empty. A real child process writes those bytes here."""
    import subprocess as sp
    script = r"import sys; sys.stderr.buffer.write(b'ERROR: [youtube] x: you\x92re not a bot\n'); sys.exit(1)"
    real = lambda cmd, **kw: sp.run([sys.executable, "-c", script], **kw)
    video, why = bd._yt_dlp_download("AAAAAAAAAAA", tmp_path, "film-a", run=real)
    assert video is None and why.startswith(bd.THROTTLED_WHY) and "not a bot" in why


# -------- 2-5. the fixture run: landscape, spill, kept, and a portrait only from >= 800 active rows

@pytest.fixture(scope="module")
def fixture_run(tmp_path_factory):
    """Two trailers: 1080p scope (1920x1080, 138-row bars: 804 active rows) and 720p scope (1280x720,
    92-row bars: 536 active rows)."""
    out = {}
    for name, size, bar in (("film-1080", (1920, 1080), 138), ("film-720", (1280, 720), 92)):
        tmp = tmp_path_factory.mktemp(name)
        mp = pytest.MonkeyPatch()
        try:   # a raise inside run() must not leave subprocess.run and shutil.which faked for the session
            mp.setattr(bd, "OVERRIDE_PATH", tmp / "none.yaml")
            mp.setattr(bd, "_mem_available_mb", lambda: None)
            mp.setattr(bd.shutil, "which", lambda n: None)
            mp.setattr(bd.subprocess, "run", _fake(size=size, bar=bar))
            mp.setattr(bd, "SAMPLE_COUNT", 8)
            data = _films(name)
            r = bd.run(data, {"data_dir": str(tmp), "now": NOW})
        finally:
            mp.undo()
        out[name] = (tmp, data, r, json.loads((tmp / "backdrops.json").read_text(encoding="utf-8"))[name])
    return out


def test_fixture_run_writes_landscape_spill_and_kept_frames_for_every_film(fixture_run):
    for name, (tmp, data, r, e) in fixture_run.items():
        assert r["new"] == 1 and r["failed"] == 0
        assert e["v"] == bd.STEP_VERSION
        for key in ("w1280", "w640"):
            assert _file(tmp, e[key]).is_file()
        with Image.open(_file(tmp, e["w1280"])) as im:
            assert im.size == (1280, e["h"])
        assert len(e["spill"]) == 4 and all(HEX.match(c) for c in e["spill"])
        assert len(e["spill_p"]) == 4 and all(HEX.match(c) for c in e["spill_p"])
        assert 1 <= len(e["kept"]) <= bd.KEEP and e["kept"][0]["w1280"] == e["w1280"]
        ts = [k["t"] for k in e["kept"]]
        gap = max(bd.KEPT_GAP_MIN_S, bd.KEPT_GAP_FRAC * 100.0)
        assert all(abs(a - b) >= gap - 0.1 for i, a in enumerate(ts) for b in ts[i + 1:])   # different shots
        for k in e["kept"]:
            assert _file(tmp, k["w1280"]).is_file() and _file(tmp, k["w640"]).is_file()
            assert k["d"] > 0   # its detail against the trailer's median, the rank's third factor
        assert 0 <= e["x"] <= 1


def test_the_active_box_is_the_scope_picture_not_the_container(fixture_run):
    assert fixture_run["film-1080"][3]["box"] == [0, 138, 1920, 942]
    assert fixture_run["film-720"][3]["box"] == [0, 92, 1280, 628]
    assert fixture_run["film-1080"][3]["h"] == 536   # 1280 * 804 / 1920


def test_a_portrait_only_from_a_source_with_at_least_800_active_rows(fixture_run):
    tmp, data, r, e = fixture_run["film-1080"]
    assert r["portraits"] == 1
    assert (e["pw"], e["ph"]) == (536, 804) and _file(tmp, e["p"]).is_file()
    with Image.open(_file(tmp, e["p"])) as im:
        assert im.size == (536, 804)
    assert re.match(r"^/posters/bd-film-1080-[0-9a-f]{10}-p\.webp$", e["p"])
    bdk = data["films"]["film-1080"]["backdrop"]
    assert (bdk["p"], bdk["pw"], bdk["ph"]) == (e["p"], 536, 804)

    tmp, data, r, e = fixture_run["film-720"]
    assert "portraits" not in r and "p" not in e and "p" not in data["films"]["film-720"]["backdrop"]
    assert e["p_skip"] == "active height 536 < 800"
    assert not list((tmp / "posters").glob("*-p.webp"))


def test_the_portrait_is_never_upscaled():
    """Whatever the source, the portrait is 2:3 at exactly the active height: a crop, never a resize."""
    for w, h in ((1920, 800), (1920, 804), (2560, 1072), (1920, 1080)):
        full = bd.grade(_scene(w, h, 7))
        img, blob, q, ratio, why = bd.portrait(full, 0.5, _land(full))
        assert why is None, (w, h, why)
        assert img.size == (round(h * 2 / 3), h) and img.height <= h
        with Image.open(io.BytesIO(blob)) as dec:
            assert dec.size == img.size
    img, blob, _, _, why = bd.portrait(bd.grade(_scene(1280, 536, 7)), 0.5, _scene(1280, 536, 7))
    assert img is None and blob is None and why == "active height 536 < 800"


def test_the_portrait_is_at_most_70_kb(fixture_run):
    tmp, _, _, e = fixture_run["film-1080"]
    assert _file(tmp, e["p"]).stat().st_size <= bd.PORTRAIT_MAX_BYTES == 70_000
    assert e["pq"] == 72
    # an incompressible source steps down in quality and, still too big, writes nothing
    noise = Image.merge("RGB", [Image.effect_noise((720, 1080), 120) for _ in range(3)])
    img, blob, q, ratio, why = bd.portrait(noise, 0.5, noise.resize((1280, 1080)))
    assert img is None and why == "over 70000 B even at q60"


def test_the_window_goes_to_the_subject_in_focus_not_the_most_colourful_patch():
    """Left: a soft, saturated glow (fire, a teal wall); right: the textured subject. The colour-ranked window
    chose the glow on 3 of W1-D1's 13 real frames; detail chooses the subject."""
    w, h = 1280, 536
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for x in range(w // 2):
        d.line([(x, 0), (x, h)], fill=(230, 120 + x * 80 // (w // 2), 30))
    img.paste(_scene(w // 2, h, 21).convert("L").convert("RGB"), (w // 2, 0))   # a grey, detailed subject
    x, detail = bd.window_x(img)
    assert x >= 0.625 and detail > 0
    left = bd.score_frame(img.crop((0, 0, 357, h)))
    right = bd.score_frame(img.crop((w - 357, 0, w, h)))
    assert left > right   # what the colour ranking would have chosen


def _haze(w=640, h=268):
    """A saturated, soft glow: a warm gradient with nothing in focus (a dust field, a fire flare)."""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for x in range(w):
        d.line([(x, 0), (x, h)], fill=(225, 150 + x * 60 // w, 40))
    return img.filter(ImageFilter.GaussianBlur(6))


def _bold_credit(img):
    """A credit in a heavy face («EDITING VIVEK HARSHAN»): yellow letters with 7 px stems, 34 px tall."""
    img = img.copy()
    d = ImageDraw.Draw(img)
    for x in range(120, 520, 26):
        d.rectangle([x, 150, x + 6, 184], fill=(240, 200, 40))
        d.rectangle([x, 150, x + 16, 156], fill=(240, 200, 40))
    return img


def test_the_screen_is_the_frame_in_focus_not_the_most_colourful_haze():
    """Review I1: colour x mid-tone alone ranked a saturated soft haze above a detailed frame of the same
    trailer (Dubai's #1 got a yellow dust field with a tenth of the detail of its own second frame). The rank
    now carries the frame's detail against the trailer's median, and bold type stays a gate."""
    haze, subject = _haze(), ImageEnhance.Color(_scene(640, 268, 12)).enhance(0.3)
    credit = _bold_credit(ImageEnhance.Color(_scene(640, 268, 13)).enhance(1.4))
    assert bd.score_frame(haze) > 1.3 * bd.score_frame(subject)      # what colour alone would choose
    assert bd.score_frame(credit) > bd.score_frame(subject) and bd.detail(credit) > bd.detail(subject)
    frames = [haze, subject, credit, haze, subject, haze]
    samples = [{"t": 10.0 + 12 * i, "crop": img} for i, img in enumerate(frames)]
    kept, floor, why = bd._pick(samples, 100.0)
    assert floor == bd.LUMA_MIN and why is None
    assert kept[0][1]["crop"] is subject                              # the screen is in focus
    assert all(s["crop"] is not credit for _, s in kept)             # bold type is never kept
    assert kept[0][1]["rel"] > 1 > min(s["rel"] for s in samples)


def test_bold_type_is_text_though_the_thin_stroke_top_hat_misses_it():
    """Review M2: a heavy credit's stems are wider than the 5 px opening, so only their corners were strokes.
    The row-wise opening sees the stems; a bright horizontal bar (a car's chrome, a sill), which a wide
    square opening mistakes for a line of text, is not type to it."""
    credit = _bold_credit(ImageEnhance.Brightness(_scene(640, 268, 9)).enhance(0.6))
    assert bd.text_score(bd.stroke_profile(credit), set())[1] is None
    assert bd.text_score(bd.stroke_profile(credit), set(), bd.bold_profile(credit))[1] == "text"
    chrome = _scene(640, 268, 9).copy()
    ImageDraw.Draw(chrome).rectangle([0, 120, 639, 126], fill=(245, 245, 245))
    assert bd.text_score(bd.stroke_profile(chrome), set(), bd.bold_profile(chrome))[1] is None
    assert all(bd.text_band(bd.bold_profile(_scene(640, 268, s)))[0] < bd.BOLD_FLAG / 3 for s in range(8))


# -------- sharpness

def test_sharpness_is_the_variance_of_a_two_sided_laplacian():
    flat = Image.new("RGB", (300, 450), (120, 120, 120))
    assert bd.sharpness(flat) < 1   # only the filter's own border
    sharp, soft = _scene(720, 1080, 3), _scene(720, 1080, 3).filter(ImageFilter.GaussianBlur(3))
    assert bd.sharpness(sharp) > 2 * bd.sharpness(soft)


def test_a_soft_crop_fails_the_sharpness_check_and_is_not_written(tmp_path, monkeypatch):
    sharp = bd.grade(_scene(1920, 804, 11))
    land = _land(sharp)
    img, blob, q, ratio, why = bd.portrait(sharp, 0.5, land)
    assert img is not None and ratio >= bd.SHARP_MIN_RATIO
    soft = sharp.filter(ImageFilter.GaussianBlur(4))
    img, blob, q, ratio, why = bd.portrait(soft, 0.5, land)
    assert img is None and blob is None and ratio < bd.SHARP_MIN_RATIO and why.startswith("soft: ")

    # end to end: the check refuses, so no -p file exists and the film keeps the landscape frame
    _fast(monkeypatch, 6)
    monkeypatch.setattr(bd, "SHARP_MIN_RATIO", 1e9)
    monkeypatch.setattr(bd.subprocess, "run", _fake())
    r = _run(tmp_path, _films("film-a"))
    e = _cache(tmp_path)["film-a"]
    assert r["new"] == 1 and "p" not in e and e["p_skip"].startswith("soft: ")
    assert not list((tmp_path / "posters").glob("*-p.webp"))
    assert "p" not in r and _file(tmp_path, e["w1280"]).is_file()


def test_the_real_portrait_is_sharper_than_the_1280w_file_stretched_over_the_same_box(fixture_run):
    """The acceptance measured on the fixture: variance of the Laplacian at display scale >= 0.9x."""
    tmp, _, _, e = fixture_run["film-1080"]
    with Image.open(_file(tmp, e["p"])) as p, Image.open(_file(tmp, e["w1280"])) as land:
        p, land = p.convert("RGB"), land.convert("RGB")
        s = land.width / 1920
        left = round(e["x"] * (1920 - 536))
        box = (round(left * s), 0, round((left + 536) * s), land.height)
        ratio = bd.sharpness(p) / bd.sharpness(land.crop(box))
    assert ratio >= 0.9 and abs(ratio - e["sharp"]) < 0.02


# -------- the grade

def test_the_grade_maps_black_to_night_and_white_to_screen_and_is_monotonic():
    assert bd.grade(Image.new("RGB", (4, 4), (0, 0, 0))).getpixel((0, 0)) == bd.NIGHT
    assert bd.grade(Image.new("RGB", (4, 4), (255, 255, 255))).getpixel((0, 0)) == bd.SCREEN
    for c in range(3):
        ch = bd.GRADE_LUT[c * 256:(c + 1) * 256]
        assert all(b >= a for a, b in zip(ch, ch[1:]))
        assert min(ch) == bd.NIGHT[c]


def test_the_grade_is_subtle_in_the_mid_tones():
    """Skin and mid-grey move by a few levels; the warmth lives in the ends."""
    for rgb in ((128, 128, 128), (200, 150, 120), (160, 120, 100)):
        out = bd.grade(Image.new("RGB", (1, 1), rgb)).getpixel((0, 0))
        grey = sum(rgb) / 3
        desat = tuple(grey + (v - grey) * bd.GRADE_SATURATION for v in rgb)
        assert all(abs(o - d) <= 9 for o, d in zip(out, desat)), (rgb, out)


def test_the_grade_is_measurable_on_the_written_files(fixture_run, tmp_path, monkeypatch):
    """Mean luma of the darkest 5 % of every written file >= the night token's luma (12.31) -- on the
    fixture, and on a trailer that is nearly black."""
    night = bd.night_luma()
    assert abs(night - 12.31) < 0.01
    for tmp, _, _, e in fixture_run.values():
        for url in [e["w1280"], e["w640"], *([e["p"]] if e.get("p") else [])]:
            with Image.open(_file(tmp, url)) as im:
                assert bd.dark_luma(im.convert("RGB")) >= night, url
    _fast(monkeypatch, 6)
    monkeypatch.setattr(bd.subprocess, "run", _fake(luma=0.25))   # a dark film, taken in the dark pass
    _run(tmp_path, _films("dark-film"))
    e = _cache(tmp_path)["dark-film"]
    assert e["dark"] is True
    with Image.open(_file(tmp_path, e["w1280"])) as im:
        assert bd.dark_luma(im.convert("RGB")) >= night


# -------- the active picture, measured once per trailer

def test_the_active_box_ignores_a_dark_scene_that_the_per_frame_crop_cuts_down():
    w, h, bar = 640, 360, 45
    frames = []
    for seed in range(6):
        c = Image.new("RGB", (w, h))
        c.paste(_scene(w, h - 2 * bar, seed), (0, bar))
        frames.append(c)
    dark = Image.new("RGB", (w, h))
    pic = Image.new("RGB", (w, h - 2 * bar), (6, 6, 6))
    ImageDraw.Draw(pic).rectangle([200, 120, 440, 150], fill=(120, 110, 100))   # one lit object mid-frame
    dark.paste(pic, (0, bar))
    frames.append(dark)
    assert bd.crop_letterbox(dark).height < 60   # the old per-frame crop keeps only the lit rows
    box = bd.active_box([bd.profiles(f) for f in frames], (w, h))
    assert box == (0, bar, w, h - bar)


def test_one_full_frame_card_does_not_widen_the_box():
    w, h, bar = 640, 360, 45
    frames = []
    for seed in range(9):
        c = Image.new("RGB", (w, h))
        c.paste(_scene(w, h - 2 * bar, seed), (0, bar))
        frames.append(c)
    frames.append(_scene(w, h, 99))   # a distributor card drawn over the whole 16:9 container
    assert bd.active_box([bd.profiles(f) for f in frames], (w, h)) == (0, bar, w, h - bar)
    assert bd.active_box([bd.profiles(Image.new("RGB", (w, h)))], (w, h)) == (0, 0, w, h)


# -------- text over the picture

def test_a_burned_in_subtitle_on_a_busy_frame_is_text_though_score_frame_accepts_it():
    busy = _busy(_scene(640, 268, 5))
    img = _with_subtitle(busy)
    assert bd.score_frame(img) is not None          # the old bottom-band edge rule is blind on a busy frame
    texty, why = bd.text_score(bd.stroke_profile(img), set())
    assert why == "text"
    assert bd.text_score(bd.stroke_profile(busy), set())[1] is None


def test_a_coloured_title_over_a_dark_scene_is_text():
    img = _scene(640, 268, 8, luma=0.3)
    d = ImageDraw.Draw(img)
    for x in range(180, 460, 12):                    # a line of red letters: 3 px stems and bars, 16 px tall
        d.rectangle([x, 120, x + 2, 136], fill=(210, 30, 30))
        d.rectangle([x, 120, x + 8, 122], fill=(210, 30, 30))
    assert bd.text_score(bd.stroke_profile(img), set())[1] == "text"


def test_a_trailers_subtitle_rows_catch_a_fainter_line_there():
    subbed = [bd.stroke_profile(_with_subtitle(_scene(640, 268, s))) for s in range(4)]
    clean = [bd.stroke_profile(_scene(640, 268, s)) for s in range(10, 16)]
    rows = bd.subtitle_rows(subbed + clean)
    assert rows and min(rows) >= int(bd.SUB_FROM * bd.TEXT_BINS)
    # one short word («حسنا»): too little ink for the frame-level rule, caught on the trailer's own rows
    short = _scene(640, 268, 30).copy()
    d = ImageDraw.Draw(short)
    for x in range(292, 348, 8):
        d.rectangle([x, 236, x + 1, 248], fill=(245, 245, 245))
    faint = bd.stroke_profile(short)
    assert bd.text_score(faint, set())[1] is None
    assert bd.text_score(faint, rows)[1] == "subtitle"
    assert all(bd.text_score(p, rows)[1] is None for p in clean)
    assert bd.subtitle_rows(clean) == set()


def test_subtitled_frames_are_never_the_screen(tmp_path, monkeypatch):
    monkeypatch.setattr(bd.subprocess, "run", _fake(size=(1280, 720), bar=92, subtitled=set(range(0, 100, 2))))
    r = _run(tmp_path, _films("film-a"))
    e = _cache(tmp_path)["film-a"]
    assert r["failed"] == 0
    assert all(int(k["t"]) % 2 == 1 for k in e["kept"]), [k["t"] for k in e["kept"]]


# -------- a dark trailer, and the reason every failure gives

def test_a_dark_trailer_gets_a_dark_frame_instead_of_a_week_long_failure(tmp_path, monkeypatch):
    _fast(monkeypatch, 6)
    monkeypatch.setattr(bd.subprocess, "run", _fake(luma=0.25))   # mean luma ~31 < LUMA_MIN 35
    r = _run(tmp_path, _films("film-a"))
    e = _cache(tmp_path)["film-a"]
    assert r["failed"] == 0 and e["dark"] is True and _file(tmp_path, e["w1280"]).is_file()


def test_a_black_trailer_fails_with_the_reason_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(bd.subprocess, "run", _fake(luma=0.02))
    r = _run(tmp_path, _films("film-a"))
    assert re.match(r"^all 16 frames rejected: 16 too dark \(mean luma \d+-\d+\)$", r["why"]["film-a"])
    assert _cache(tmp_path)["film-a"]["kind"] == "rejected"


# -------- order, the top-10 retry, the cap

def test_the_most_shown_film_goes_first_under_the_cap(tmp_path, monkeypatch):
    _fast(monkeypatch)
    monkeypatch.setenv("CINEMA_BACKDROPS_MAX", "1")
    monkeypatch.setattr(bd.subprocess, "run", _fake(size=(640, 360), bar=0))
    _run(tmp_path, _films("aaa-film", "zzz-film", shows={"aaa-film": 3, "zzz-film": 40}))
    assert list(_cache(tmp_path)) == ["zzz-film"]


def test_top_10_failures_retry_after_6_hours(tmp_path, monkeypatch):
    """Entries written before this version (no `v`, like Dubai's #1 and #2), whatever their kind."""
    fids = [f"film-{i:02d}" for i in range(11)]
    shows = {f: 100 - i for i, f in enumerate(fids)}   # film-10 is the 11th: not in tonight's top 10
    stale = "2026-09-28T05:00:00+00:00"                  # 7 h before NOW: past 6 h, far inside 7 days
    (tmp_path / "backdrops.json").write_text(json.dumps({
        f: {"trailer": _films(f)["films"][f]["trailer"], "fail": stale, "kind": "rejected"} for f in fids
    }), encoding="utf-8")
    _fast(monkeypatch)
    monkeypatch.setenv("CINEMA_BACKDROPS_MAX", "20")
    monkeypatch.setattr(bd.subprocess, "run", _fake(size=(640, 360), bar=0))
    r = _run(tmp_path, _films(*fids, shows=shows))
    cache = _cache(tmp_path)
    assert r["new"] == 10 and r["cached"] == 1
    assert all("w1280" in cache[f] for f in fids[:10]) and cache["film-10"]["fail"] == stale


def test_a_settled_rejection_of_a_top_film_waits_its_week(tmp_path, monkeypatch):
    """Review M1: a "rejected" failure written by this version is the same code on the same samples, so the
    6 h top-10 retry re-downloaded it 29 times a week for the same answer. A transient failure, or a
    rejection by an older version, still retries after 6 h."""
    fids = ["film-a", "film-b", "film-c"]
    stale = "2026-09-28T05:00:00+00:00"                  # 7 h before NOW
    t = {f: _films(f)["films"][f]["trailer"] for f in fids}
    (tmp_path / "backdrops.json").write_text(json.dumps({
        "film-a": {"trailer": t["film-a"], "fail": stale, "kind": "rejected", "v": bd.STEP_VERSION},
        "film-b": {"trailer": t["film-b"], "fail": stale, "kind": "transient", "v": bd.STEP_VERSION},
        "film-c": {"trailer": t["film-c"], "fail": stale, "kind": "rejected", "v": 1},
    }), encoding="utf-8")
    _fast(monkeypatch)
    monkeypatch.setattr(bd.subprocess, "run", _fake(size=(640, 360), bar=0))
    r = _run(tmp_path, _films(*fids, shows={"film-a": 30, "film-b": 20, "film-c": 10}))
    cache = _cache(tmp_path)
    assert r["new"] == 2 and r["cached"] == 1
    assert cache["film-a"]["fail"] == stale and "w1280" in cache["film-b"] and "w1280" in cache["film-c"]
    r = _run(tmp_path, _films(*fids, shows={"film-a": 30}), now="2026-10-05T06:00:00+00:00")   # 7 days on
    assert r["new"] == 1 and "w1280" in _cache(tmp_path)["film-a"]


# -------- an older version's frame is re-made, and stays up until then

def _v1_entry(tmp_path, fid, trailer):
    (tmp_path / "posters").mkdir(exist_ok=True)
    for w in (1280, 640):
        Image.new("RGB", (w, w * 9 // 16), (90, 20, 20)).save(tmp_path / "posters" / f"bd-{fid}-0123456789-{w}.webp")
    return {"trailer": trailer, "w1280": f"/posters/bd-{fid}-0123456789-1280.webp",
            "w640": f"/posters/bd-{fid}-0123456789-640.webp", "w": 1280, "h": 720, "t": 5.0,
            "at": "2026-09-26T22:56:36+04:00"}


def test_a_version_1_frame_stays_attached_until_it_is_re_made(tmp_path, monkeypatch):
    data = _films("film-a")
    trailer = data["films"]["film-a"]["trailer"]
    (tmp_path / "backdrops.json").write_text(json.dumps({"film-a": _v1_entry(tmp_path, "film-a", trailer)}),
                                             encoding="utf-8")
    monkeypatch.setenv("CINEMA_BACKDROPS_MAX", "0")
    monkeypatch.setattr(bd.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("capped")))
    r = _run(tmp_path, data)
    assert r == {"new": 0, "failed": 0, "cached": 1}
    assert data["films"]["film-a"]["backdrop"]["w1280"].endswith("0123456789-1280.webp")

    monkeypatch.setenv("CINEMA_BACKDROPS_MAX", "4")
    _fast(monkeypatch)
    monkeypatch.setattr(bd.subprocess, "run", _fake(size=(640, 360), bar=0))
    data = _films("film-a")
    r = _run(tmp_path, data)
    e = _cache(tmp_path)["film-a"]
    assert r["upgraded"] == 1 and e["v"] == bd.STEP_VERSION and "0123456789" not in e["w1280"]
    assert not (tmp_path / "posters" / "bd-film-a-0123456789-1280.webp").exists()   # pruned
    assert data["films"]["film-a"]["backdrop"]["w1280"] == e["w1280"]


def test_a_failed_upgrade_keeps_the_old_frame_and_waits_its_ttl(tmp_path, monkeypatch):
    data = _films("film-a")
    trailer = data["films"]["film-a"]["trailer"]
    (tmp_path / "backdrops.json").write_text(json.dumps({"film-a": _v1_entry(tmp_path, "film-a", trailer)}),
                                             encoding="utf-8")
    monkeypatch.setattr(bd.subprocess, "run", _fake(fail_download=9))
    r = _run(tmp_path, data)
    e = _cache(tmp_path)["film-a"]
    assert r["failed"] == 1 and e["up_kind"] == "transient" and e["w1280"].endswith("0123456789-1280.webp")
    assert data["films"]["film-a"]["backdrop"]["w1280"] == e["w1280"]
    monkeypatch.setattr(bd.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("in ttl")))
    r = _run(tmp_path, _films("film-a"), now="2026-09-28T13:00:00+00:00")
    assert r == {"new": 0, "failed": 0, "cached": 1}


# -------- the override's window, the memory guard, backward compatibility, prune

def test_the_override_x_places_the_portrait_window(tmp_path, monkeypatch):
    (tmp_path / "backdrops_override.yaml").write_text("film-a: {t: 42.5, x: 0}\nfilm-b: {x: 1}\n", encoding="utf-8")
    assert bd._load_overrides() == {"film-a": {"t": 42.5, "x": 0.0}, "film-b": {"t": None, "x": 1.0}}
    _fast(monkeypatch, 6)
    monkeypatch.setattr(bd.subprocess, "run", _fake())
    _run(tmp_path, _films("film-a", "film-b"))
    a, b = _cache(tmp_path)["film-a"], _cache(tmp_path)["film-b"]
    assert (a["t"], a["x"], a["override_t"], a["override_x"]) == (42.5, 0.0, 42.5, 0.0)
    assert (b["x"], b["override_x"]) == (1.0, 1.0) and "override_t" not in b
    with Image.open(_file(tmp_path, a["w1280"])) as land:
        assert a["spill_p"] == bd.spill(land.convert("RGB"), 0, round(land.height * 2 / 3))


def test_an_override_change_keeps_the_frame_until_the_re_make_succeeds(tmp_path, monkeypatch):
    """Review M3: a changed `x`/`t` made the film "work", so a failed re-make replaced a good frame with a
    `fail` entry and prune deleted its files. It is re-made like an older version's frame now."""
    _fast(monkeypatch, 6)
    monkeypatch.setattr(bd.subprocess, "run", _fake())
    _run(tmp_path, _films("film-a"))
    first = _cache(tmp_path)["film-a"]

    (tmp_path / "backdrops_override.yaml").write_text("film-a: {x: 0.2}\n", encoding="utf-8")
    monkeypatch.setattr(bd.subprocess, "run", _fake(fail_download=9))
    data = _films("film-a")
    r = _run(tmp_path, data, now="2026-09-28T13:00:00+00:00")
    e = _cache(tmp_path)["film-a"]
    assert r["failed"] == 1 and "fail" not in e and e["w1280"] == first["w1280"]
    assert (e["up_kind"], e["up_override_x"]) == ("transient", 0.2)
    assert _file(tmp_path, e["w1280"]).is_file() and _file(tmp_path, e["p"]).is_file()
    assert data["films"]["film-a"]["backdrop"]["w1280"] == first["w1280"]

    # the same value again inside its TTL: not retried
    monkeypatch.setattr(bd.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("in ttl")))
    r = _run(tmp_path, _films("film-a"), now="2026-09-28T14:00:00+00:00")
    assert (r["new"], r["failed"], r["cached"], r.get("portraits")) == (0, 0, 1, 1)

    # another value: tried at once, and on success it replaces the frame
    (tmp_path / "backdrops_override.yaml").write_text("film-a: {x: 0.8}\n", encoding="utf-8")
    monkeypatch.setattr(bd.subprocess, "run", _fake())
    r = _run(tmp_path, _films("film-a"), now="2026-09-28T14:30:00+00:00")
    e = _cache(tmp_path)["film-a"]
    assert r["upgraded"] == 1 and (e["x"], e["override_x"]) == (0.8, 0.8)
    assert not any(k.startswith("up_") for k in e)


def test_the_memory_guard_starts_no_film_below_the_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(bd, "_mem_available_mb", lambda: 512)
    monkeypatch.setattr(bd.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no room")))
    r = _run(tmp_path, _films("film-a"))
    assert r == {"new": 0, "failed": 0, "cached": 0, "mem_mb": 512}


def test_backdrops_json_and_the_film_keep_every_old_key(fixture_run):
    import site_kit
    for name, (tmp, data, r, e) in fixture_run.items():
        assert {"trailer", "w1280", "w640", "w", "h", "t", "at"} <= set(e)
        assert e["w"] == 1280 and isinstance(e["h"], int)
        b = data["films"][name]["backdrop"]
        assert {"w1280", "w640", "w", "h", "t", "x", "spill", "spill_p"} <= set(b)
        for key in ("w1280", "w640", "p"):
            if key in b:
                assert site_kit.OUR_BACKDROP.match(b[key])


def test_prune_keeps_the_portrait_and_kept_frames_and_drops_them_with_the_film(tmp_path, monkeypatch):
    _fast(monkeypatch, 6)
    monkeypatch.setattr(bd.subprocess, "run", _fake())
    _run(tmp_path, _films("film-a"))
    e = _cache(tmp_path)["film-a"]
    names = {os.path.basename(u) for u in [e["w1280"], e["w640"], e["p"]] +
             [k[w] for k in e["kept"] for w in ("w1280", "w640")]}
    assert names == {p.name for p in (tmp_path / "posters").glob("bd-*.webp")}
    data = _films("film-a")
    data["films"]["film-a"]["status"] = "archived"
    _run(tmp_path, data)
    assert not list((tmp_path / "posters").glob("bd-*.webp"))


# -------- Pillow only, no deprecated call, the same colourfulness

def test_requirements_are_unchanged_and_the_step_is_pillow_only():
    req = open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read().lower()
    assert "numpy" not in req and "opencv" not in req
    src = open(os.path.join(ROOT, "steps", "backdrops.py"), encoding="utf-8").read()
    assert not re.search(r"^\s*(import|from)\s+(numpy|cv2)\b", src, re.M)
    assert ".getdata(" not in src.replace("img.getdata()", "")   # only _pixels' fallback for an old Pillow


def test_no_pillow_deprecation_warning_on_a_full_run(tmp_path, monkeypatch):
    _fast(monkeypatch)
    monkeypatch.setattr(bd.subprocess, "run", _fake(size=(1280, 720), bar=92))
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        r = _run(tmp_path, _films("film-a"))
    assert r["new"] == 1 and r["failed"] == 0


def _colourfulness_reference(img):
    data = list(img.convert("RGB").get_flattened_data()) if hasattr(img, "get_flattened_data") else list(img.convert("RGB").getdata())
    n = len(data)
    rg = [r - g for r, g, _ in data]
    yb = [0.5 * (r + g) - b for r, g, b in data]
    mr, my = sum(rg) / n, sum(yb) / n
    vr = sum((v - mr) ** 2 for v in rg) / n
    vy = sum((v - my) ** 2 for v in yb) / n
    return math.sqrt(vr + vy) + 0.3 * math.sqrt(mr ** 2 + my ** 2)


def test_the_fast_colourfulness_matches_the_reference_formula():
    for seed in range(4):
        img = _scene(320, 134, seed)
        ref = _colourfulness_reference(img)
        assert abs(bd._colourfulness(img) - ref) <= 0.02 * ref
