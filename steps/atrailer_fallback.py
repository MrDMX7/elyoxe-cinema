"""steps/atrailer_fallback.py — a replacement trailer when a film's own one has gone dead.

Runs before steps/backdrops.py (name sorts first: "atrailer_fallback" < "backdrops", both match
refresh.run_steps' `[a-z]*.py` glob), so a replacement id is already in `film["trailer"]` by the
time the screen's frame is picked.

For every film currently showing or coming with a syntactically valid trailer id (site_kit.YT,
the same check backdrops.py uses), the id's own health is checked with a light `yt-dlp
--simulate --skip-download` call. When it comes back "unavailable" (private, removed, blocked,
copyright-claimed — never a plain network hiccup, YT_UNAVAILABLE below), a replacement is
searched with `yt-dlp ytsearch<N>:"<title> <year> official trailer"`, the first result whose
runtime is 60–240 s and whose title/channel reads as an official trailer is kept.

Budget (owner's phone, one heavy process at a time): CHECK_CAP fresh network calls a run — a
`--simulate` probe or a search, each counted once. A film already known ok, or already known dead
with a replacement on file, costs nothing until its RECHECK_DAYS/RECHECK_DAYS_DEAD are up. Cache
at data/trailer_fallback.json (corruption-safe, statefile.py):

    {fid: {"orig": <11-char id>, "checked_at": <iso>,
           "status": "ok" | "dead" | "unknown",   # "unknown": the probe itself failed/timed out
           "replacement": <11-char id> | None, "why": <str> | None}}

`film["trailer"]` is overwritten with the cached replacement every run it applies (enrich.py sets
it back to the chain's own id each run, from film_trailer/TMDB — this step's cache is the thing
that persists across runs, not the field itself). Never raises into the publish; a probe/search
subprocess failure just leaves the film on its original id for next run to retry.

--offline: no subprocess is ever run (tests/test_steps.py's guard fails on any attempt); the step
still applies whatever is already cached, exercising the caching/apply logic without a network.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

YT = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHECK_CAP = 4                      # fresh yt-dlp calls (probe + search combined) per run
RECHECK_DAYS = 21                  # re-probe a trailer last confirmed ok this long ago
RECHECK_DAYS_DEAD = 45             # re-probe (in case the original came back) once this stale, but
                                    # only once a replacement is actually on file (see RECHECK_DAYS_NO_REPLACEMENT)
RECHECK_DAYS_NO_REPLACEMENT = 1    # a dead trailer with NO replacement found retries roughly daily,
                                    # not 45 days -- a transient search failure (or budget exhaustion)
                                    # must not lock the film out of a fix for a month and a half
SEARCH_COUNT = 6                   # ytsearch<N>: results asked for
DUR_MIN, DUR_MAX = 60, 240         # an official trailer's plausible runtime, seconds
PROBE_TIMEOUT = 25.0
SEARCH_TIMEOUT = 40.0
TITLE_HINT = re.compile(r"official trailer|trailer #?\d*$", re.I)
# a candidate is rejected outright when its title or channel names it as not-official footage --
# fan edits and reaction/concept videos regularly satisfy the duration+"trailer" checks otherwise
BAD_HINT = re.compile(r"fan[\s-]?made|fanmade|reaction|concept\s*trailer|parody|leak(ed)?|\bedit\b|fan\s*edit", re.I)
OFFICIAL_CHANNEL_HINT = re.compile(r"official|pictures|studios?|entertainment|films?\b", re.I)
_STRIP = re.compile(r"[^a-z0-9؀-ۿ\s]")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", _STRIP.sub(" ", (s or "").lower())).strip()
# a probe error naming the video itself as gone — never a throttle/network wobble, which must not
# trigger a search (retried plain next run instead, same as backdrops.py's own "transient" class)
YT_UNAVAILABLE = re.compile(
    r"video (is )?(private|unavailable)|has been removed|account (has been|is) terminated|"
    r"copyright|this video is no longer available|content is not available|not available in your country",
    re.I,
)


def _text(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v or ""


def _probe(trailer_id: str, run=None) -> str:
    """"ok" | "dead" | "unknown" (a non-availability failure: throttle, timeout, no yt-dlp)."""
    run = run or subprocess.run
    url = f"https://www.youtube.com/watch?v={trailer_id}"
    try:
        r = run(["yt-dlp", "--simulate", "--skip-download", "--no-warnings", url],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if getattr(r, "returncode", 1) == 0:
        return "ok"
    err = _text(getattr(r, "stderr", "")) + _text(getattr(r, "stdout", ""))
    return "dead" if YT_UNAVAILABLE.search(err) else "unknown"


def _search(title: str, year, run=None):
    """-> (id, why) | (None, why). Asks yt-dlp for SEARCH_COUNT candidates' id/title/channel/duration,
    rejects any that read as fan-made/reaction/concept, requires the film's own (normalised) title to
    appear in the video's title -- a generic query like "Him official trailer" can otherwise surface
    a different film or a reaction video entirely -- then, among what's left, prefers a result whose
    channel reads as an official studio/distributor over the search's own relevance order."""
    run = run or subprocess.run
    q = f"{title} {year} official trailer".strip() if year else f"{title} official trailer"
    query = f"ytsearch{SEARCH_COUNT}:{q}"
    fmt = "%(id)s\t%(duration)s\t%(channel)s\t%(title)s"
    try:
        r = run(["yt-dlp", "--flat-playlist", "--print", fmt, "--no-warnings", query],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=SEARCH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"search: {type(e).__name__}: {e}"[:200]
    if getattr(r, "returncode", 1) != 0:
        return None, f"search: yt-dlp exit {getattr(r, 'returncode', '?')}"
    title_norm = _norm(title)
    candidates = []
    for line in _text(getattr(r, "stdout", "")).splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        vid, dur, channel, vtitle = parts
        if not YT.match(vid):
            continue
        try:
            dur_s = float(dur)
        except ValueError:
            continue
        if not (DUR_MIN <= dur_s <= DUR_MAX):
            continue
        if BAD_HINT.search(vtitle) or BAD_HINT.search(channel):
            continue
        if not (TITLE_HINT.search(vtitle) or TITLE_HINT.search(channel) or "trailer" in vtitle.lower()):
            continue
        if title_norm and title_norm not in _norm(vtitle):
            continue
        candidates.append((vid, channel))
    if not candidates:
        return None, "search: no candidate matched duration/title/channel"
    for vid, channel in candidates:
        if OFFICIAL_CHANNEL_HINT.search(channel):
            return vid, None
    return candidates[0][0], None


def _candidates(data: dict) -> dict[str, dict]:
    """fid -> film dict, for every film currently showing (status != archived) or coming, whose own
    `trailer` is a syntactically valid id -- films win a fid collision with coming (same shape as
    steps/backdrops.py's own _candidates)."""
    out: dict[str, dict] = {}
    for fid, f in (data.get("coming") or {}).items():
        tid = f.get("trailer")
        if isinstance(tid, str) and YT.match(tid):
            out[fid] = f
    for fid, f in (data.get("films") or {}).items():
        if f.get("status") == "archived":
            continue
        tid = f.get("trailer")
        if isinstance(tid, str) and YT.match(tid):
            out[fid] = f
    return out


def _due(entry: dict | None, now: datetime, orig: str) -> bool:
    if not isinstance(entry, dict) or entry.get("orig") != orig:
        return True
    at = entry.get("checked_at")
    try:
        checked = datetime.fromisoformat(at) if at else None
    except (TypeError, ValueError):
        checked = None
    if checked is None:
        return True
    if entry.get("status") == "dead":
        # a dead trailer WITH a replacement on file is stable -- re-probe rarely, in case the
        # original came back. One with NO replacement is not fixed at all, so it must not wait
        # the same 45 days: a transient search failure or a budget-starved run gets retried daily.
        ttl = timedelta(days=RECHECK_DAYS_DEAD if entry.get("replacement") else RECHECK_DAYS_NO_REPLACEMENT)
    else:
        ttl = timedelta(days=RECHECK_DAYS)
    return now - checked >= ttl


def run(data, ctx):
    import statefile

    ddir = Path(ctx.get("data_dir") or Path(__file__).resolve().parent.parent / "data")
    path = ddir / "trailer_fallback.json"
    cache, _status = statefile.load_state_json(path, path.with_name(path.name + ".bak"))
    cache = dict(cache) if isinstance(cache, dict) else {}

    try:
        now = datetime.fromisoformat(ctx.get("now")) if ctx.get("now") else datetime.now()
    except (TypeError, ValueError):
        now = datetime.now()

    candidates = _candidates(data)
    checked_ids = {fid for fid, f in candidates.items()}
    # prune fids no longer showing/coming
    cache = {fid: v for fid, v in cache.items() if fid in checked_ids}

    budget = CHECK_CAP
    probed = replaced = searched = 0
    offline = bool(ctx.get("offline"))

    for fid, f in candidates.items():
        orig = f["trailer"]
        entry = cache.get(fid)
        if not offline and budget > 0 and _due(entry, now, orig):
            status = _probe(orig)
            probed += 1
            budget -= 1
            if status == "ok":
                cache[fid] = {"orig": orig, "checked_at": now.isoformat(), "status": "ok",
                              "replacement": None, "why": None}
            elif status == "dead":
                if budget <= 0:
                    repl, why = None, "search skipped: no budget left"
                else:
                    repl, why = _search(f.get("title") or f.get("title_ar") or fid, f.get("year"))
                    searched += 1
                    budget -= 1               # the call itself costs budget, found or not
                cache[fid] = {"orig": orig, "checked_at": now.isoformat(), "status": "dead",
                              "replacement": repl, "why": why}
            else:  # unknown: transient, kept as-is, retried plain next run (checked_at not written)
                cache.setdefault(fid, {"orig": orig, "checked_at": None, "status": "unknown",
                                        "replacement": None, "why": "probe: transient/inconclusive"})
        entry = cache.get(fid)
        if entry and entry.get("orig") == orig and entry.get("status") == "dead" and entry.get("replacement"):
            f["trailer"] = entry["replacement"]
            f["trailer_fallback"] = True
            replaced += 1

    statefile.write_state_json(path, path.with_name(path.name + ".bak"), cache)
    return {"checked": len(candidates), "probed": probed, "searched": searched, "replaced": replaced}
