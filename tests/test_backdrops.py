"""steps/backdrops.py (UI redesign Task 1): score_frame, crop_letterbox, and the yt-dlp/ffmpeg
pipeline orchestrated with subprocess mocked (never a real network call in the suite -- see
conftest.py and tests/test_steps.py::test_every_real_step_honours_offline, which runs this step
for real, offline, over the sample fixture)."""
import json
import os
import sys

import pytest
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import steps.backdrops as bd  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_override_file(monkeypatch, tmp_path):
    """Every test in this file gets its own (non-existent, unless a test writes one) override path
    -- never the real repo-root backdrops_override.yaml (which has its own `sacrifice: none` entry;
    none of these tests use that fid, but isolating from real repo content is the honest default)."""
    monkeypatch.setattr(bd, "OVERRIDE_PATH", tmp_path / "backdrops_override.yaml")


# -------- score_frame

def _flat(color, size=(320, 180)):
    return Image.new("RGB", size, color)


def _gradient(size=(320, 180)):
    """A smooth vertical grayscale gradient: within the accepted luma range, but with almost no
    edges anywhere -- the baseline both the subtitle and title-card tests start from."""
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for y in range(h):
        v = 60 + round(120 * y / max(h - 1, 1))   # 60..180, comfortably inside [35, 200]
        d.line([(0, y), (w, y)], fill=(v, v, v))
    return img


def _with_bottom_band_text(img):
    """Simulates a burned-in subtitle line: a barcode-like strip of alternating bright/dark bars
    across the bottom 22% band -- dense, localised edges, exactly what a line of glyphs produces,
    without depending on a particular font being available."""
    img = img.copy()
    w, h = img.size
    d = ImageDraw.Draw(img)
    top = round(h * 0.85)
    for x in range(0, w, 6):
        d.rectangle([x, top, x + 3, top + 10], fill=(255, 255, 255))
    return img


def _with_centred_title_text(color=(20, 20, 24), size=(320, 180)):
    """Simulates a title card: a flat-coloured frame (no texture anywhere) with a dense band of
    bright bars across the vertical centre -- bold headline text on an otherwise empty background."""
    img = Image.new("RGB", size, color)
    w, h = size
    d = ImageDraw.Draw(img)
    top = round(h * 0.46)
    for x in range(0, w, 6):
        d.rectangle([x, top, x + 3, top + 14], fill=(230, 230, 230))
    return img


def test_black_frame_rejected():
    assert bd.score_frame(_flat((0, 0, 0))) is None


def test_white_frame_rejected():
    assert bd.score_frame(_flat((255, 255, 255))) is None


def test_gradient_with_bottom_band_text_rejected():
    assert bd.score_frame(_with_bottom_band_text(_gradient())) is None


def test_same_gradient_without_text_accepted():
    """Accepted: a grayscale gradient's own colourfulness is 0 (r == g == b everywhere), so this
    checks acceptance (score_frame returns a number, not None), not the score's magnitude."""
    score = bd.score_frame(_gradient())
    assert score is not None and score >= 0


def test_title_card_rejected_even_though_it_is_within_the_luma_range():
    assert bd.score_frame(_with_centred_title_text()) is None


def test_more_colourful_of_two_accepted_frames_wins():
    """Same luma (so the mid-tone weight is equal), very different saturation: a frame that is
    mostly grey vs. one built from strongly-separated red/green/blue blocks must score the colourful
    one higher -- the whole point of the colourfulness term."""
    w, h = 320, 180
    grey = Image.new("RGB", (w, h), (140, 138, 142))   # luma ~139, minimal colour

    colourful = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(colourful)
    d.rectangle([0, 0, w // 3, h], fill=(230, 30, 30))
    d.rectangle([w // 3, 0, 2 * w // 3, h], fill=(30, 230, 60))
    d.rectangle([2 * w // 3, 0, w, h], fill=(30, 60, 230))

    s_grey, s_colour = bd.score_frame(grey), bd.score_frame(colourful)
    assert s_grey is not None and s_colour is not None
    assert s_colour > s_grey


# -------- crop_letterbox

def test_crop_letterbox_removes_black_bars_top_and_bottom():
    w, content_h, bar_h = 40, 60, 12
    img = Image.new("RGB", (w, content_h + 2 * bar_h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, bar_h, w, bar_h + content_h - 1], fill=(90, 140, 200))   # PIL rectangle: inclusive corners
    cropped = bd.crop_letterbox(img)
    assert cropped.size == (w, content_h)
    assert cropped.getpixel((w // 2, content_h // 2)) == (90, 140, 200)


def test_crop_letterbox_leaves_a_frame_with_no_black_bars_unchanged():
    img = Image.new("RGB", (40, 60), (90, 140, 200))
    assert bd.crop_letterbox(img).size == (40, 60)


def test_crop_letterbox_leaves_an_all_black_frame_unchanged():
    """Nothing sane to crop to -- score_frame's own luma-range check rejects it regardless."""
    img = Image.new("RGB", (20, 20), (0, 0, 0))
    assert bd.crop_letterbox(img).size == (20, 20)


# -------- pipeline orchestration (subprocess mocked)

class _Result:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _png_bytes(color=(90, 140, 200), size=(1280, 720)):
    import io
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _fake_run_factory(video_writer, frame_color=(90, 140, 200), fail_download=False, fail_all_frames=False):
    """A stand-in for subprocess.run good enough to drive process_film() end to end: recognises
    yt-dlp (writes a tiny fake video file at the -o template), ffprobe (prints a duration) and
    ffmpeg (returns PNG bytes on stdout), so the *orchestration* (caching, the cap, cleanup) is
    tested without ever installing/reaching a real yt-dlp or ffmpeg."""
    def fake_run(cmd, **kw):
        prog = os.path.basename(str(cmd[0])).lower()
        if prog.startswith("yt-dlp"):
            if fail_download:
                return _Result(returncode=1)
            template = cmd[cmd.index("-o") + 1]
            path = template.replace("%(ext)s", "mp4")
            video_writer(path)
            return _Result(returncode=0)
        if prog.startswith("ffprobe"):
            return _Result(returncode=0, stdout="12.0\n")
        if prog.startswith("ffmpeg"):
            if fail_all_frames:
                return _Result(returncode=1)
            return _Result(returncode=0, stdout=_png_bytes(frame_color))
        raise AssertionError(f"unexpected subprocess: {cmd}")
    return fake_run


def _write_stub_video(path):
    with open(path, "wb") as f:
        f.write(b"not a real video, just needs to exist")


def _data(films=None, coming=None):
    return {"films": films or {}, "coming": coming or {}}


def test_success_writes_cache_entry_and_webp_files_and_attaches_backdrop(tmp_path, monkeypatch):
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 1, "failed": 0, "cached": 0}

    cache = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    entry = cache["film-a"]
    assert entry["trailer"] == "AAAAAAAAAAA" and "fail" not in entry
    assert (tmp_path / "posters" / os.path.basename(entry["w1280"])).is_file()
    assert (tmp_path / "posters" / os.path.basename(entry["w640"])).is_file()

    assert data["films"]["film-a"]["backdrop"]["w1280"] == entry["w1280"]
    assert data["films"]["film-a"]["backdrop"]["w640"] == entry["w640"]


def test_cache_hit_skips_the_pipeline_entirely(tmp_path, monkeypatch):
    calls = []

    def boom(cmd, **kw):
        calls.append(cmd)
        raise AssertionError("must not run any subprocess on a cache hit")

    data_dir = tmp_path
    (data_dir / "backdrops.json").write_text(json.dumps({
        "film-a": {"trailer": "AAAAAAAAAAA", "w1280": "/posters/bd-film-a-deadbeef01-1280.webp",
                   "w640": "/posters/bd-film-a-deadbeef01-640.webp", "w": 1280, "h": 720,
                   "t": 5.0, "at": "2026-09-20T12:00:00+00:00"}
    }), encoding="utf-8")
    (data_dir / "posters").mkdir()
    (data_dir / "posters" / "bd-film-a-deadbeef01-1280.webp").write_bytes(b"x")
    (data_dir / "posters" / "bd-film-a-deadbeef01-640.webp").write_bytes(b"x")

    monkeypatch.setattr(bd.subprocess, "run", boom)
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(data_dir), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 0, "failed": 0, "cached": 1}
    assert not calls
    assert data["films"]["film-a"]["backdrop"]["w1280"] == "/posters/bd-film-a-deadbeef01-1280.webp"


def test_content_rejection_is_kind_rejected_and_not_retried_within_seven_days(tmp_path, monkeypatch):
    """Every sampled frame decodes fine but scores None (a solid black frame: luma 0) -- a content
    problem, not an infra one -- so the cached failure is `kind: "rejected"` under the full 7-day
    FAIL_TTL_REJECTED (fix round 1, review Important #1)."""
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video, frame_color=(0, 0, 0)))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r1 = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r1 == {"new": 1, "failed": 1, "cached": 0}
    cache1 = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert cache1["film-a"] == {"trailer": "AAAAAAAAAAA", "fail": "2026-09-27T12:00:00+00:00", "kind": "rejected"}
    assert "backdrop" not in data["films"]["film-a"]

    def boom(cmd, **kw):
        raise AssertionError("a 'rejected' failure inside the 7-day TTL must not be retried")

    monkeypatch.setattr(bd.subprocess, "run", boom)
    data2 = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    # 7 hours later: well past the 6h transient TTL, but nowhere near the 7-day rejected one
    r2 = bd.run(data2, {"data_dir": str(tmp_path), "now": "2026-09-27T19:00:00+00:00"})
    assert r2 == {"new": 0, "failed": 0, "cached": 1}


def test_transient_failure_is_kind_transient_and_retried_after_six_hours_not_seven_days(tmp_path, monkeypatch):
    """The download itself fails (network/yt-dlp trouble) -- an infra problem, so `kind: "transient"`
    under the much shorter FAIL_TTL_TRANSIENT (fix round 1, review Important #1): the task's own real
    run hit exactly this (heart-of-the-beast, task-1-report.md Concern #2)."""
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video, fail_download=True))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r1 = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r1 == {"new": 1, "failed": 1, "cached": 0}
    cache1 = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert cache1["film-a"] == {"trailer": "AAAAAAAAAAA", "fail": "2026-09-27T12:00:00+00:00", "kind": "transient"}

    # 3 hours later: inside the 6h transient TTL, still not retried
    def boom(cmd, **kw):
        raise AssertionError("a transient failure inside its own 6h TTL must not be retried")

    monkeypatch.setattr(bd.subprocess, "run", boom)
    r2 = bd.run(_data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}}),
                {"data_dir": str(tmp_path), "now": "2026-09-27T15:00:00+00:00"})
    assert r2 == {"new": 0, "failed": 0, "cached": 1}

    # 7 hours later: past the 6h transient TTL -- retried, and this time it succeeds
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    r3 = bd.run(_data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}}),
                {"data_dir": str(tmp_path), "now": "2026-09-27T19:00:00+00:00"})
    assert r3 == {"new": 1, "failed": 0, "cached": 0}
    assert "fail" not in json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))["film-a"]


def test_failure_past_the_ttl_is_retried(tmp_path, monkeypatch):
    (tmp_path / "backdrops.json").write_text(json.dumps({
        "film-a": {"trailer": "AAAAAAAAAAA", "fail": "2026-09-01T12:00:00+00:00"}
    }), encoding="utf-8")
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 1, "failed": 0, "cached": 0}
    assert "fail" not in json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))["film-a"]


def test_old_cache_entry_with_no_kind_defaults_to_the_longer_rejected_ttl(tmp_path, monkeypatch):
    """A fail entry written before this round (no `kind` key at all) must not suddenly get hammered
    with retries the moment this ships -- it defaults to the conservative, longer TTL."""
    (tmp_path / "backdrops.json").write_text(json.dumps({
        "film-a": {"trailer": "AAAAAAAAAAA", "fail": "2026-09-27T06:00:00+00:00"}   # 6h ago, no "kind"
    }), encoding="utf-8")

    def boom(cmd, **kw):
        raise AssertionError("an unlabelled old failure must default to the 7-day ttl, not 6h")

    monkeypatch.setattr(bd.subprocess, "run", boom)
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 0, "failed": 0, "cached": 1}


def test_new_films_per_run_are_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    monkeypatch.setenv("CINEMA_BACKDROPS_MAX", "2")
    films = {f"film-{i}": {"status": "showing", "trailer": f"{'A' * 10}{i}"} for i in range(5)}
    data = _data(films=films)
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r["new"] == 2
    cache = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert len(cache) == 2   # the other 3 films are left uncached for a later run, not marked failed


def test_downloaded_video_is_deleted_after_each_film_success_and_failure(tmp_path, monkeypatch):
    written = []

    def writer(path):
        _write_stub_video(path)
        written.append(path)

    work_dir = tmp_path / "backdrops_work"
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(writer))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert written and not os.path.exists(written[0])
    assert not work_dir.exists()   # run() clears its whole scratch dir when it's done

    written.clear()
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(writer, fail_all_frames=True))
    data2 = _data(films={"film-b": {"status": "showing", "trailer": "BBBBBBBBBBB"}})
    bd.run(data2, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert written and not os.path.exists(written[0])


def test_a_films_failure_never_raises_out_of_run(tmp_path, monkeypatch):
    def boom(cmd, **kw):
        raise OSError("yt-dlp not found")

    monkeypatch.setattr(bd.subprocess, "run", boom)
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 1, "failed": 1, "cached": 0}


def test_archived_films_and_films_without_a_trailer_are_never_candidates(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(bd.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or _Result(1))
    data = _data(films={
        "archived-film": {"status": "archived", "trailer": "AAAAAAAAAAA"},
        "no-trailer": {"status": "showing"},
        "bad-trailer": {"status": "showing", "trailer": "not-a-valid-id!!"},
    })
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 0, "failed": 0, "cached": 0}
    assert not calls


def test_offline_never_starts_a_subprocess(tmp_path, monkeypatch):
    def boom(cmd, **kw):
        raise AssertionError("offline must never start yt-dlp/ffmpeg")

    monkeypatch.setattr(bd.subprocess, "run", boom)
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "offline": True, "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 0, "failed": 0, "cached": 0, "offline": True}


def test_coming_films_are_processed_and_cached_but_never_attached_to_data_coming(tmp_path, monkeypatch):
    """pages/coming.py never calls Kit.backdrop() -- the cache entry is still written so the frame is
    ready the day the film starts showing, but nothing is attached onto data["coming"][fid]."""
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    data = _data(coming={"soon-film": {"title": "Soon", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 1, "failed": 0, "cached": 0}
    cache = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert cache["soon-film"]["trailer"] == "AAAAAAAAAAA"
    assert "backdrop" not in data["coming"]["soon-film"]


def test_trailer_id_change_invalidates_the_old_cache_entry(tmp_path, monkeypatch):
    (tmp_path / "backdrops.json").write_text(json.dumps({
        "film-a": {"trailer": "OLDOLDOLDOL", "w1280": "/posters/bd-film-a-oldold0001-1280.webp",
                   "w640": "/posters/bd-film-a-oldold0001-640.webp", "w": 1280, "h": 720,
                   "t": 5.0, "at": "2026-09-01T12:00:00+00:00"}
    }), encoding="utf-8")
    (tmp_path / "posters").mkdir()
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    data = _data(films={"film-a": {"status": "showing", "trailer": "NEWNEWNEWNE"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r["new"] == 1
    cache = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert cache["film-a"]["trailer"] == "NEWNEWNEWNE"


# -------- fix round 1: wall-clock budget (review Minor #2)

def test_new_films_stop_starting_once_the_budget_is_spent(tmp_path, monkeypatch):
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    monkeypatch.setenv("CINEMA_BACKDROPS_BUDGET_S", "0")   # already "spent" before the first attempt
    films = {f"film-{i}": {"status": "showing", "trailer": f"{'A' * 10}{i}"} for i in range(3)}
    data = _data(films=films)
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 0, "failed": 0, "cached": 0}
    cache_path = tmp_path / "backdrops.json"
    assert not cache_path.exists() or json.loads(cache_path.read_text(encoding="utf-8")) == {}


def test_budget_default_is_generous_enough_for_a_normal_run(tmp_path, monkeypatch):
    """No env override: the default (480s) must not itself block a normal, fast (mocked) run."""
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 1, "failed": 0, "cached": 0}


# -------- fix round 1: manual override (review Important #2)

def test_override_none_is_never_attempted_and_never_attached(tmp_path, monkeypatch):
    (tmp_path / "backdrops_override.yaml").write_text("film-a: none\n", encoding="utf-8")
    monkeypatch.setattr(bd, "OVERRIDE_PATH", tmp_path / "backdrops_override.yaml")

    def boom(cmd, **kw):
        raise AssertionError("an fid overridden to 'none' must never start a subprocess")

    monkeypatch.setattr(bd.subprocess, "run", boom)
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 0, "failed": 0, "cached": 1}
    assert "backdrop" not in data["films"]["film-a"]
    cache = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert cache["film-a"] == {"trailer": "AAAAAAAAAAA", "override": "none"}


def test_override_none_hides_an_already_good_cached_backdrop(tmp_path, monkeypatch):
    """An override added AFTER a clean frame was already cached still wins -- a human overriding a
    frame they've now looked at and don't like takes priority over whatever's on disk."""
    (tmp_path / "backdrops.json").write_text(json.dumps({
        "film-a": {"trailer": "AAAAAAAAAAA", "w1280": "/posters/bd-film-a-deadbeef01-1280.webp",
                   "w640": "/posters/bd-film-a-deadbeef01-640.webp", "w": 1280, "h": 720,
                   "t": 5.0, "at": "2026-09-20T12:00:00+00:00"}
    }), encoding="utf-8")
    (tmp_path / "posters").mkdir()
    (tmp_path / "posters" / "bd-film-a-deadbeef01-1280.webp").write_bytes(b"x")
    (tmp_path / "posters" / "bd-film-a-deadbeef01-640.webp").write_bytes(b"x")
    (tmp_path / "backdrops_override.yaml").write_text("film-a: none\n", encoding="utf-8")
    monkeypatch.setattr(bd, "OVERRIDE_PATH", tmp_path / "backdrops_override.yaml")
    monkeypatch.setattr(bd.subprocess, "run", lambda cmd, **kw: (_ for _ in ()).throw(
        AssertionError("must not reprocess just because of an override")))

    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 0, "failed": 0, "cached": 1}
    assert "backdrop" not in data["films"]["film-a"]
    # and the now-orphaned webp files are pruned, since nothing wants them any more
    assert not (tmp_path / "posters" / "bd-film-a-deadbeef01-1280.webp").exists()
    assert not (tmp_path / "posters" / "bd-film-a-deadbeef01-640.webp").exists()


def test_override_seconds_skips_scoring_and_re_extracts_when_the_value_changes(tmp_path, monkeypatch):
    """The frame color returned by the fake ffmpeg is BLACK -- score_frame would reject it outright
    (luma < 35) -- so a successful save here proves the override path never calls score_frame at
    all. Changing the override value must re-extract (a different `override_t` never matches a
    cached one), which this test proves by checking the cache's `t` moves with it."""
    override_path = tmp_path / "backdrops_override.yaml"
    override_path.write_text("film-a: 10\n", encoding="utf-8")
    monkeypatch.setattr(bd, "OVERRIDE_PATH", override_path)
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video, frame_color=(0, 0, 0)))

    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r1 = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r1 == {"new": 1, "failed": 0, "cached": 0}
    cache1 = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert cache1["film-a"]["t"] == 10.0 and cache1["film-a"]["override_t"] == 10.0

    # same value again: a cache hit, no subprocess call at all
    monkeypatch.setattr(bd.subprocess, "run", lambda cmd, **kw: (_ for _ in ()).throw(
        AssertionError("the override value did not change -- must not reprocess")))
    data2 = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r2 = bd.run(data2, {"data_dir": str(tmp_path), "now": "2026-09-27T13:00:00+00:00"})
    assert r2 == {"new": 0, "failed": 0, "cached": 1}

    # the value changes: re-extracted, even though nothing else about the film changed
    override_path.write_text("film-a: 40\n", encoding="utf-8")
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video, frame_color=(0, 0, 0)))
    data3 = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r3 = bd.run(data3, {"data_dir": str(tmp_path), "now": "2026-09-27T14:00:00+00:00"})
    assert r3 == {"new": 1, "failed": 0, "cached": 0}
    cache3 = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert cache3["film-a"]["t"] == 40.0 and cache3["film-a"]["override_t"] == 40.0
    assert data3["films"]["film-a"]["backdrop"]["t"] == 40.0


def test_malformed_override_entries_are_ignored(tmp_path, monkeypatch):
    override_path = tmp_path / "backdrops_override.yaml"
    override_path.write_text("film-a: not-a-number-or-none\nBAD FID !!: 5\n", encoding="utf-8")
    monkeypatch.setattr(bd, "OVERRIDE_PATH", override_path)
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    r = bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert r == {"new": 1, "failed": 0, "cached": 0}   # processed normally -- the bad override line was ignored


# -------- fix round 1: orphaned bd-*.webp pruning, og.py's own convention (review Minor #3)

def test_a_films_own_poster_mirror_files_are_never_touched_by_pruning(tmp_path, monkeypatch):
    (tmp_path / "posters").mkdir()
    real_poster = tmp_path / "posters" / "film-a-abc1234567-342.webp"
    real_poster.write_bytes(b"a real poster, not a backdrop")
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    assert real_poster.exists()   # the prune glob is "bd-*.webp" only


def test_orphaned_backdrop_is_pruned_when_the_film_leaves_showing_and_coming(tmp_path, monkeypatch):
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    cache = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    old_names = [os.path.basename(cache["film-a"]["w1280"]), os.path.basename(cache["film-a"]["w640"])]
    for n in old_names:
        assert (tmp_path / "posters" / n).exists()

    # the film is archived this run (no longer showing or coming) -- nothing should reprocess it,
    # but its now-unwanted cache entry and files must be pruned
    data2 = _data(films={"film-a": {"status": "archived", "trailer": "AAAAAAAAAAA"}})
    r2 = bd.run(data2, {"data_dir": str(tmp_path), "now": "2026-09-27T13:00:00+00:00"})
    assert r2 == {"new": 0, "failed": 0, "cached": 0}
    cache2 = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert "film-a" not in cache2
    for n in old_names:
        assert not (tmp_path / "posters" / n).exists()


def test_orphaned_backdrop_is_pruned_when_the_trailer_id_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video, frame_color=(90, 140, 200)))
    data = _data(films={"film-a": {"status": "showing", "trailer": "AAAAAAAAAAA"}})
    bd.run(data, {"data_dir": str(tmp_path), "now": "2026-09-27T12:00:00+00:00"})
    cache = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    old_names = [os.path.basename(cache["film-a"]["w1280"]), os.path.basename(cache["film-a"]["w640"])]

    monkeypatch.setattr(bd.subprocess, "run", _fake_run_factory(_write_stub_video, frame_color=(30, 200, 60)))
    data2 = _data(films={"film-a": {"status": "showing", "trailer": "BBBBBBBBBBB"}})
    r2 = bd.run(data2, {"data_dir": str(tmp_path), "now": "2026-09-27T13:00:00+00:00"})
    assert r2["new"] == 1
    for n in old_names:
        assert not (tmp_path / "posters" / n).exists()   # the old trailer's frame is gone
    cache2 = json.loads((tmp_path / "backdrops.json").read_text(encoding="utf-8"))
    assert cache2["film-a"]["trailer"] == "BBBBBBBBBBB"
    new_names = [os.path.basename(cache2["film-a"]["w1280"]), os.path.basename(cache2["film-a"]["w640"])]
    for n in new_names:
        assert (tmp_path / "posters" / n).exists()


def test_real_step_is_quick_and_offline_over_the_sample_fixture():
    """The same guard tests/test_steps.py runs across every real steps/*.py: this one specifically,
    standalone, so a failure here names backdrops.py instead of the whole suite."""
    import time

    data = json.load(open(os.path.join(ROOT, "fixtures", "sample_latest.json"), encoding="utf-8"))
    t0 = time.monotonic()
    r = bd.run(data, {"offline": True, "now": data["generated"], "data_dir": os.path.join(ROOT, "data")})
    assert r["offline"] is True
    assert time.monotonic() - t0 < 2
