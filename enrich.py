"""Film enrichment: Wikidata + Rotten Tomatoes public page + Wikipedia summary.

No TMDB/OMDb keys exist for this project and none are created (controller ruling,
2026-09-25). Instead:
  - Wikidata (wbsearchentities + a full-text search, both no key, + wbgetentities) for title_ar,
    year, genres, director, cast, runtime, the IMDb id (P345) and the Rotten Tomatoes id (P1258).
  - The Rotten Tomatoes page itself (https://www.rottentomatoes.com/m/<id>) for the
    Tomatometer/Popcornmeter percentages, review counts and critics consensus —
    parsed out of the page's embedded `media-scorecard-json` block and the
    `#critics-consensus` div, not an API.
  - Wikipedia's REST summary endpoint for an English synopsis. No invention.
  - imdb_score is always written as null: there is no OMDb key, so it waits for one.

enrich(data, cache_path="data/films_cache.json", offline=False) -> dict mutates
data["films"][fid] in place, adding: title_ar, year, genres{ar,en}, director, cast,
runtime (only if missing), synopsis_en, wikidata{qid}, imdb{id}, imdb_score(None),
rt{critics, critics_count, audience, consensus, url}, trailer (the chain's own, else Wikidata
P1651), genres (GENRES keys: the chains' first, then Wikidata's labels folded onto them —
genres.py). `poster` is left untouched.

Cache (data/films_cache.json, gitignored): per-fid {"ids": {...}, "ids_status":
"found"|"not_found"|"error", "ids_checked_at": ISO, "ratings": {...}, "ratings_at": ISO}.
"found" is permanent (never re-queried). "not_found" (a genuine, successfully-queried empty
result) is retried after NOT_FOUND_TTL — a title with no Wikidata item today may get one once
the film is a few days old. "error" (a network/HTTP/parse failure — we couldn't tell either
way) is retried much sooner, after ERROR_TTL, specifically so a transient outage during a
film's first-ever lookup doesn't get treated as "confirmed absent" and left that way forever
(round-3 controller review, 2026-09-26). A "not_found" cached under an older LOOKUP_VERSION is
retried once too, capped per run at NOT_FOUND_RELOOKUP_CAP (oldest-checked first) so a version
bump — e.g. this fix's widened search — doesn't throw every cached-absent film at Wikidata (and
the phone) in one run. Ratings (the RT numbers) expire after RATINGS_TTL regardless of ids
status. offline=True never touches the network — whatever is in the cache (or nothing) is used.

Wikidata matching only ever accepts a film-shaped hit whose own publication year is in
`accepted_years` — the current/previous calendar year by default, or a single explicit
`{film["year_hint"]}` when a reader/caller supplies one. There is no fallback to "the best
non-matching-year hit anyway": a title collision with an older or unrelated work (e.g. "The
Odyssey" 2016 vs the 2026 Nolan film, "Insidious" the franchise vs one specific 2026 entry)
must return no match rather than silently attach the wrong film's data — a wrong match is
worse than none (round-3 controller review; the per-title `search_title` override in
seed_verdicts.py is still how a title that doesn't surface its correct match in the top
search hits at all gets there, orthogonal to this year filter). The Rotten Tomatoes fetch has
the same guard: a page's own `releaseYear` (read out of its `where-to-watch-json` block) must
match the Wikidata-recorded year for that same qid, or the rating is dropped rather than
attached to the wrong film.

Candidates come from two Wikidata searches, merged (fix, 2026-09-30 — the regression that cost
most films their match): wbsearchentities alone (the only source before this fix) is a label/alias
*prefix* match ranked by sitelink count, so a brand-new, barely-linked film routinely loses to an
older or unrelated work sharing its title — the 2026 "Resident Evil" (Zach Cregger) doesn't surface
even 50 hits deep, buried under the video-game franchise and its many entries; "Digger" and "The
Odyssey" both have their current-year film past position 6 (the search `limit` used here), a plain
franchise/game/epic-poem/older-film crowding the front. `_wikidata_fulltext_search` (CirrusSearch's
full-text `list=search`) ranks by textual relevance instead and finds all three directly. Neither
search replaces the other — full text can miss what a short, exact label match gets outright — so
`_find_film_qid` merges both, then still applies every guard above unchanged: a wider candidate
pool, not a looser acceptance test. Among several accepted-year film-shaped candidates,
`_best_film_in_hits` now prefers one whose own label is an exact (case/punctuation-insensitive)
match for the searched title over one that only matched by relevance. The retry-with-suffix pass
appends " film" (proven to surface a buried new release through full-text search) ahead of the
`accepted_years`-derived "(2026 film)"/"(2025 film)" disambiguators (previously hardcoded to those
two literal years regardless of the actual current year).

Re-releases (fix wave, 2026-09-26): a classic back in cinemas (The Dark Knight, Interstellar)
has no current-year Wikidata film, so the year filter above finds nothing. Only then, and only
under three guards, an older film is accepted: its English label equals the cleaned title
exactly (case/punctuation-insensitive), it has >= 20 sitelinks (a well-known film, not a
same-named obscurity), and its runtime, when both are known, is within 5 minutes of the
listing's (plus: its original language, when Wikidata and the listing both give one, agrees).
Such a film carries film["rerelease"] = True, and its RT page is checked against its own year.

Synopsis: only for a film whose Wikidata match was accepted, and only from that item's own
English Wikipedia sitelink — never a title search (that is how "Dhoomakethu" 2026 got the
plot of a 1968 Kannada film).

title_ar (W1-D2, MASTER-PLAN §5.2): resolve_title_ar() below, in this order, never machine-translated:
  0. an entry in titles_ar.yaml the owner reviewed and pinned (`pin: true`): his word is final;
  1. an Arabic-language film is always Arabic: the first of the sources below, and for such a film a
     titles_ar.yaml entry is used even before its review (its Latin is itself a transliteration);
  2. the Wikidata item's own Arabic label (never its English label), re-read every AR_TTL with its Arabic
     aliases (a new film's label often lands on Wikidata days after release). The item is the film's own match,
     or the one its titles_ar.yaml entry names (`qid:`) when the match cannot find it: a re-release listed under
     another name («Avengers Endgame: Encore» is Q23781155). Only that item's Arabic names are used;
  3. one of those Arabic aliases, when the item has no label;
  4. the Arabic title a chain publishes (Reel's TitleAlt, Novo's movie_title_ar);
  5. a titles_ar.yaml entry the owner reviewed (`review: true` = not yet: never published).
Every other sourced Arabic name (the label, the aliases, the chain's, a reviewed entry) is kept in
film["aka_ar"] as a search key only. film["title_ar_src"] says where the title came from, and
data["titles_ar"] carries the review list (entries awaiting review, films with no Arabic title at all, and the
entries it could not use); `python enrich.py titles` prints it for the weekly look (owner default D12). An owner's
edit of titles_ar.yaml never stops enrich: what cannot be used is left out and named, never raised. Only a line
that breaks the YAML itself holds the deploy (the suite's parse check), as for every other YAML file.
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests
import yaml

from genres import genre_keys, merge_keys
from readers.common import youtube_id

UA = "elyoxe-cinema/1.0 (+https://elyoxe.com/cinema; contact hello@elyoxe.com)"
GAP_SECONDS = 2.0
RATINGS_TTL = timedelta(days=3)
NOT_FOUND_TTL = timedelta(days=3)
ERROR_TTL = timedelta(hours=6)
FILM_QIDS = {"Q11424", "Q24862", "Q24869"}  # film, short film, television film
LOOKUP_VERSION = 4          # 4 (2026-10-20): an undated just-released item counts (_recent_undated). 2: re-release fallback. 3 (2026-09-30 regression fix): search widened with
                             # a full-text fallback — wbsearchentities alone buries a brand-new,
                             # low-notability film behind an older/unrelated same-titled one. A
                             # "not_found" from an older version is retried once, capped per run —
                             # NOT_FOUND_RELOOKUP_CAP below — so the version bump does not throw every
                             # cached-absent film at Wikidata (and the phone) in a single run.
NOT_FOUND_RELOOKUP_CAP = 30  # of the films whose "not_found" predates the current LOOKUP_VERSION, at
                             # most this many are retried in one enrich() call (oldest ids_checked_at
                             # first); the rest catch up on a later run.
RERELEASE_MIN_SITELINKS = 20
RERELEASE_RUNTIME_TOLERANCE = 5
# listing language -> Wikidata QID of that language (P364, original language of the film)
LANG_QIDS = {"English": "Q1860", "Arabic": "Q13955", "Hindi": "Q1568", "Malayalam": "Q36236",
             "Tamil": "Q5885", "Telugu": "Q8097", "Korean": "Q9176", "Japanese": "Q5287",
             "French": "Q150", "Tagalog": "Q34057", "Punjabi": "Q58635"}
_ARABIC = re.compile(r"[\u0600-\u06ff]")
TITLES_AR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "titles_ar.yaml")
AR_TTL = timedelta(days=3)       # the matched item's Arabic label and aliases are re-read this often
_EAST_DIGITS = str.maketrans("\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9", "01234567890123456789")
_QID = re.compile(r"Q[1-9][0-9]*")
_FILM_SUFFIX = re.compile(r"\s*[(\uff08]\s*(?:\u0641\u064a\u0644\u0645|film)[^)\uff09]*[)\uff09]\s*$", re.IGNORECASE)

_last_call = [0.0]


class LookupFailed(Exception):
    """A Wikidata call failed at the network/HTTP/JSON-parse level — distinct from a
    legitimate empty result (HTTP 200, zero hits), so the caller can avoid caching a
    transient failure as a permanent "not found" for this film."""


def _polite_get(url, **kw):
    """A GET with a floor on time-between-requests, tolerant of network failure."""
    wait = GAP_SECONDS - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()
    kw.setdefault("timeout", 20)
    headers = kw.pop("headers", {})
    headers.setdefault("User-Agent", UA)
    try:
        return requests.get(url, headers=headers, **kw)
    except requests.RequestException:
        return None


def _load_cache(path):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_cache(path, cache):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _fresh(iso_ts, ttl):
    if not iso_ts:
        return False
    try:
        t = datetime.fromisoformat(iso_ts)
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - t < ttl


# ---------- Wikidata ----------
#
# _wikidata_search/_wikidata_entities raise LookupFailed on a network/HTTP/parse failure —
# they do NOT swallow it into an empty list/dict the way they used to, because an empty dict
# from "the request failed" and an empty dict from "Wikidata legitimately has zero hits" used
# to be indistinguishable to the caller, and the caller (enrich()) cached both as the same
# permanent "not found". A real empty *result* (HTTP 200, `{"search": []}`) still returns []
# normally — that's not a failure, it's an answer.

def _wikidata_search(title):
    r = _polite_get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbsearchentities", "search": title, "language": "en",
                "format": "json", "type": "item", "limit": 6},
    )
    if r is None:
        raise LookupFailed("network error calling wbsearchentities")
    if r.status_code != 200:
        raise LookupFailed(f"wbsearchentities HTTP {r.status_code}")
    try:
        return r.json().get("search", [])
    except ValueError as e:
        raise LookupFailed(f"bad JSON from wbsearchentities: {e}") from e


_TAG = re.compile(r"<[^>]+>")


def _wikidata_fulltext_search(title):
    """CirrusSearch full-text search over the item namespace (action=query&list=search) — ranked by
    textual relevance rather than wbsearchentities' sitelink-popularity-weighted label/alias prefix
    match, so it finds a brand-new, barely-linked film that wbsearchentities buries dozens of hits deep
    behind an older or unrelated same-titled work (module docstring, 2026-09-30 fix). Hit shape matches
    _wikidata_search's: {"id": qid, "description": best-effort text} — "description" is Cirrus's own
    snippet, HTML-stripped; it usually is the item's Description field for a clean match, sometimes a
    fragment of other matched text, so _looks_like_a_film's regex check on it is a heuristic same as for
    wbsearchentities. May raise LookupFailed, same as _wikidata_search."""
    r = _polite_get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "query", "list": "search", "srsearch": title, "srnamespace": 0,
                "format": "json", "srlimit": 10},
    )
    if r is None:
        raise LookupFailed("network error calling the Wikidata full-text search")
    if r.status_code != 200:
        raise LookupFailed(f"Wikidata full-text search HTTP {r.status_code}")
    try:
        hits = r.json().get("query", {}).get("search", [])
    except ValueError as e:
        raise LookupFailed(f"bad JSON from the Wikidata full-text search: {e}") from e
    return [{"id": h["title"], "description": _TAG.sub("", h.get("snippet") or "")}
            for h in hits if isinstance(h.get("title"), str) and h["title"].startswith("Q")]


def _merged_search_hits(title):
    """Both Wikidata searches for one title, deduplicated (wbsearchentities' hits first — its
    "description" is the cleaner of the two). See the module docstring: neither search alone is enough.
    Either call's LookupFailed propagates uncaught, exactly as a single search failing did before this
    function existed — a transient failure on either request is still never miscached as a confirmed
    "not found" (the LookupFailed philosophy above _wikidata_search)."""
    hits = _wikidata_search(title)
    extra = _wikidata_fulltext_search(title)
    seen = {h["id"] for h in hits}
    return hits + [h for h in extra if h["id"] not in seen]


def _wikidata_entities(ids, props="labels|claims"):
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    r = _polite_get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbgetentities", "ids": "|".join(ids), "format": "json",
                "languages": "en|ar", "props": props},
    )
    if r is None:
        raise LookupFailed("network error calling wbgetentities")
    if r.status_code != 200:
        raise LookupFailed(f"wbgetentities HTTP {r.status_code}")
    try:
        return r.json().get("entities", {})
    except ValueError as e:
        raise LookupFailed(f"bad JSON from wbgetentities: {e}") from e


def _label(entities, qid, lang):
    labels = entities.get(qid, {}).get("labels", {})
    if lang in labels:
        return labels[lang]["value"]
    if "en" in labels:
        return labels["en"]["value"]
    return None


def _arabic_label(entities, qid):
    """The item's own Arabic label, or None — never the English label standing in for it."""
    v = (entities.get(qid, {}).get("labels", {}).get("ar") or {}).get("value")
    return v if v and _ARABIC.search(v) else None


def clean_ar(s):
    """An Arabic title as the site prints it: Western digits, one space between words, no trailing
    «(فيلم)» disambiguator; None unless it is written in Arabic script."""
    if not s or not isinstance(s, str):
        return None
    s = unicodedata.normalize("NFC", s).translate(_EAST_DIGITS)
    s = re.sub(r"\s+", " ", _FILM_SUFFIX.sub("", s)).strip()
    return s if _ARABIC.search(s) else None


def _wikidata_ar(qids):
    """{qid: {"label": str|None, "aliases": [str]} or None} — each item's own Arabic label and Arabic aliases,
    50 ids a call; None for an id the answer has no item for (merged or deleted: the caller keeps what it had,
    and asks again only after AR_TTL). May raise LookupFailed."""
    qids = [q for q in dict.fromkeys(qids) if q]
    out = {}
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        ents = _wikidata_entities(batch, props="labels|aliases")
        for q in batch:
            e = ents.get(q)
            if not isinstance(e, dict) or "missing" in e:
                out[q] = None
                continue
            label = clean_ar(((e.get("labels") or {}).get("ar") or {}).get("value"))
            aliases = [clean_ar(a.get("value")) for a in ((e.get("aliases") or {}).get("ar") or []) if isinstance(a, dict)]
            out[q] = {"label": label, "aliases": [a for a in dict.fromkeys(aliases) if a and a != label]}
    return out


# ---------- titles_ar.yaml: the reviewed list (owner-editable) ----------

def load_titles_ar(path=None, problems=None):
    """titles_ar.yaml -> {fid: {"ar", "review", "pin", "qid", "kind", "source", "en"}}. It never stops the hourly
    run, whatever the owner typed: a file that cannot be read gives {}, an entry it cannot use is left out, a
    `review`/`pin` that is not true or false keeps its safe side (awaiting review, not pinned), and each of these
    is named on stderr and in `problems` (a list, when given; enrich puts it in data["titles_ar"]["invalid"]).
    Eastern digits, double spaces and a trailing «(فيلم)» are simply cleaned (clean_ar)."""
    path = path or TITLES_AR_PATH

    def bad(fid, why):
        print(f"enrich: titles_ar.yaml {fid}: {why}", file=sys.stderr)
        if problems is not None:
            problems.append({"fid": str(fid), "why": why})
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        bad("*", f"unreadable, every entry left out: {e}")
        return {}
    titles = raw.get("titles") if isinstance(raw, dict) else None
    if not isinstance(titles, (dict, type(None))):
        bad("*", "`titles` is not a list of film ids: every entry left out")
        return {}
    out = {}
    for fid, e in (titles or {}).items():
        if isinstance(e, str):
            e = {"ar": e}
        if not isinstance(e, dict):
            bad(fid, "not an entry like {ar: ...}: left out")
            continue
        ar, qid = clean_ar(e.get("ar")), str(e.get("qid") or "").strip() or None
        if qid and not _QID.fullmatch(qid):
            bad(fid, f"qid {qid!r} is not a Wikidata id like Q23781155: ignored")
            qid = None
        if not ar and (e.get("ar") or not qid):
            bad(fid, "`ar` is not written in Arabic: " + ("only its qid is used" if qid else "left out"))
            if not qid:
                continue
        review, pin = e.get("review", False), e.get("pin", False)
        if not isinstance(review, bool):
            bad(fid, "`review` is not true or false: kept awaiting review")
            review = True
        if not isinstance(pin, bool):
            bad(fid, "`pin` is not true or false: not pinned")
            pin = False
        out[str(fid)] = {"ar": ar, "review": review, "pin": pin, "qid": qid, "kind": e.get("kind"),
                         "source": e.get("source"), "en": e.get("en")}
    return out


def resolve_title_ar(film, wd_label=None, wd_aliases=(), listed=None):
    """(title_ar or None, source, aka_ar) for one film — the order is the module docstring's. `listed` is the
    film's titles_ar.yaml entry. Sources: pin, wikidata, wikidata-alias, chain, list, list-unreviewed (an
    Arabic film only). aka_ar: every other sourced Arabic name, for search; an unreviewed entry is never one."""
    listed = listed or {}
    reviewed = listed.get("ar") if listed and not listed.get("review") else None
    label = clean_ar(wd_label)
    aliases = [a for a in (clean_ar(x) for x in (wd_aliases or ())) if a]
    chain = clean_ar(film.get("title_ar_chain"))
    if reviewed and listed.get("pin"):
        title, src = reviewed, "pin"
    else:
        order = [(label, "wikidata"), (aliases[0] if aliases else None, "wikidata-alias"), (chain, "chain"), (reviewed, "list")]
        if film.get("lang") == "Arabic" and listed.get("ar") and not reviewed:
            order.append((listed["ar"], "list-unreviewed"))
        title, src = next(((t, s) for t, s in order if t), (None, None))
    aka = [a for a in dict.fromkeys([label, *aliases, chain, reviewed]) if a and a != title]
    return title, src, aka


def titles_report(films, listed, shows=None, invalid=None):
    """The weekly look (D12): {"review": [...], "missing": [...], "invalid": [...], "sources": {src: n}}. `review`
    is every titles_ar.yaml entry still awaiting the owner (with the title it would replace, and whether it
    spells the sounds or translates words), `missing` every film with no Arabic title and no entry at all, both
    busiest first; `invalid` the entries load_titles_ar() could not use."""
    count = {}
    for s in shows or ():
        f = s.get("film") if isinstance(s, dict) else None
        if f:
            count[f] = count.get(f, 0) + 1
    by = lambda r: (-r["shows"], r["fid"])
    review, missing, sources = [], [], {}
    for fid, film in films.items():
        src = film.get("title_ar_src")
        sources[src or "latin"] = sources.get(src or "latin", 0) + 1
        e = listed.get(fid)
        row = {"fid": fid, "title": film.get("title") or fid, "lang": film.get("lang"), "shows": count.get(fid, 0)}
        if e and e.get("review") and e.get("ar"):
            kind = e.get("kind") or ("transliteration" if e.get("source") == "proposed" else None)
            review.append({**row, "ar": e["ar"], "pin": e.get("pin", False), "kind": kind, "now": film.get("title_ar")})
        elif not film.get("title_ar"):
            missing.append(row)
    return {"review": sorted(review, key=by), "missing": sorted(missing, key=by), "invalid": list(invalid or ()),
            "sources": sources}


def _norm_title(t):
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def _claim_values(entity, prop):
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        try:
            out.append(c["mainsnak"]["datavalue"]["value"])
        except (KeyError, TypeError):
            continue
    return out


def _claim_year(entity, prop="P577"):
    for v in _claim_values(entity, prop):
        try:
            return int(v["time"][1:5])
        except (KeyError, TypeError, ValueError):
            continue
    return None


_DESC_FILM = re.compile(r"\bfilm\b", re.IGNORECASE)
_DESC_NOT_FILM = re.compile(r"video game|soundtrack|\bscore\b|franchise|universe|book|novel", re.IGNORECASE)


def _looks_like_a_film(hit, ent):
    """P31 in FILM_QIDS covers plain "film"; Wikidata also has many film subtypes (animated
    film, documentary film, ...) not worth enumerating one by one, so fall back to the search
    hit's own description ("2026 animated film directed by ...") when P31 doesn't match.
    """
    instances = {v.get("id") for v in _claim_values(ent, "P31")}
    if instances & FILM_QIDS:
        return True
    desc = hit.get("description") or ""
    return bool(_DESC_FILM.search(desc)) and not _DESC_NOT_FILM.search(desc)


RECENT_IMDB = 20_000_000   # IMDb ids from tt20000000 on were issued from 2022 (tt33318732 = Jailer 2, 2026)


def _recent_undated(ent, label, want):
    """2026-10-20: a just-released film's Wikidata item often has no publication date yet (Jailer 2, Q133255153), so the
    year filter never sees it and the film goes without its article, cast and scores. Such an item counts only when its
    English label is exactly the title asked for AND its IMDb id is recent (>= tt20000000) — an older film of the same
    name has an old id (or a date, which the year filter judges as before)."""
    if not want or _claim_year(ent) is not None or _norm_title(label or "") != want:
        return False
    for v in _claim_values(ent, "P345"):
        m = re.match(r"^tt(\d+)$", str(v))
        if m and int(m.group(1)) >= RECENT_IMDB:
            return True
    return False


def _best_film_in_hits(hits, accepted_years, want_title=None):
    """Given search hits (wbsearchentities, full-text, or the two merged), returns the qid of a
    film-shaped hit whose own publication year is in `accepted_years`, or None.

    No "best guess" fallback: a film-shaped hit whose year is wrong (or unknown) is not
    returned even if it's the only film-shaped hit. Round-3 controller review — the previous
    version returned the best film-shaped hit regardless of year when nothing recent was
    found, which is how "The Odyssey" silently resolved to a 2016 film. Wrong match is worse
    than no match: the caller treats None as "not found" and moves on, rather than attaching
    another film's title_ar/genres/cast/runtime/ids to this listing.

    `want_title`, when given (2026-09-30 fix): among several accepted-year film-shaped hits —
    now a real possibility once wbsearchentities and full-text results are merged — one whose
    own English label is an exact match (case/punctuation-insensitive, via _norm_title) for it
    wins over one that only matched by relevance/alias. Hit order (the search engines' own
    ranking) still decides when no hit is an exact label match, same as before this parameter
    existed.
    """
    if not hits:
        return None
    entities = _wikidata_entities([h["id"] for h in hits])
    want = _norm_title(want_title) if want_title else None
    candidates, undated = [], []
    recent = max(accepted_years or {0}) >= datetime.now().year - 1   # only for a current release, never a year_hint of old
    for h in hits:
        qid = h["id"]
        ent = entities.get(qid)
        if not ent or not _looks_like_a_film(h, ent):
            continue
        if _claim_year(ent) in accepted_years:
            candidates.append((qid, ent))
        elif recent and _recent_undated(ent, _label(entities, qid, "en"), want):
            undated.append(qid)
    if not candidates:
        return undated[0] if undated else None   # a dated accepted-year film always wins over an undated one
    if want:
        for qid, ent in candidates:
            if _norm_title(_label(entities, qid, "en")) == want:
                return qid
    return candidates[0][0]


def _find_film_qid(title, accepted_years):
    """Wikidata match: instance-of film, publication year in `accepted_years`, or None.

    wbsearchentities alone first — cheap, and already right for most titles (module docstring:
    it is a plain label/alias prefix match, so an exact or near-exact title still lands directly
    on the film). Only when that doesn't land on an accepted-year hit does a full-text search
    (_wikidata_fulltext_search) join in, merged with what wbsearchentities already returned — a
    brand-new, barely-linked film routinely loses wbsearchentities' popularity ranking to an
    older or unrelated entity of the same name (e.g. "Resident Evil" the video-game franchise
    outranking the 2026 film by dozens of positions), which the full-text side finds directly.
    If that still doesn't land, retry both merged, appending " film" (proven to surface a buried
    new release through the full-text search), then a "(<year> film)" disambiguator for each
    accepted year — how Wikidata titles some just-released films, tried last since it rarely
    matches literally. If nothing lands on an accepted year, return None — never the best
    non-matching hit (see _best_film_in_hits). This keeps the common case at one request, paying
    for the wider (and slower, rate-limited) search only for the titles that actually need it.
    """
    hits = _wikidata_search(title)
    qid = _best_film_in_hits(hits, accepted_years, title)
    if qid:
        return qid
    hits = hits + [h for h in _wikidata_fulltext_search(title) if h["id"] not in {x["id"] for x in hits}]
    qid = _best_film_in_hits(hits, accepted_years, title)
    if qid:
        return qid
    suffixes = [" film"] + [f" ({y} film)" for y in sorted(accepted_years, reverse=True)]
    for suffix in suffixes:
        more_hits = _merged_search_hits(title + suffix)
        more_qid = _best_film_in_hits(more_hits, accepted_years, title)
        if more_qid:
            return more_qid
    return None


def _runtime_of(ent):
    for v in _claim_values(ent, "P2047"):
        try:
            return round(float(str(v["amount"]).lstrip("+")))
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _find_rerelease_qid(title, runtime=None, lang=None):
    """An older film for a title with no current-year match — see the module docstring's
    "Re-releases": its English label equals the cleaned title, or (2026-09-30 fix) is a leading
    word-prefix of it — a themed re-release is often listed with a promotional tag stuck onto the
    original title ("Avengers Endgame: Encore" for "Avengers: Endgame"), which no Wikidata search
    finds under the full listing title at all (unlike an unrelated title, that search returns zero
    hits, full stop). Up to 3 trailing words are dropped from the *search query* to find such a
    listing's own item; the label comparison itself is never loosened beyond "is a prefix of the
    full listing title" — still gated by every other guard: >= RERELEASE_MIN_SITELINKS sitelinks
    (a well-known film, not a same-named obscurity), runtime within RERELEASE_RUNTIME_TOLERANCE
    when both are known, original language agreeing when both are known. The title itself falls
    back to the item's own enwiki sitelink when its English *label* is empty (2026-09-30 fix,
    found live: Q23781155, "Avengers: Endgame" itself, carries no English label at all despite 90
    sitelinks and an enwiki article titled exactly that — the label field and the sitelink can
    genuinely disagree on Wikidata). Returns the qid or None. May raise LookupFailed, from any of
    the (up to 4) queries tried."""
    want = _norm_title(title)
    if not want:
        return None
    words = title.split()
    queries = dict.fromkeys(q for q in
                             [title] + [" ".join(words[:-n]) for n in range(1, min(3, len(words) - 1) + 1)]
                             if q.strip())
    for query in queries:
        hits = _merged_search_hits(query)  # LookupFailed propagates uncaught, same as _find_film_qid's
        if not hits:                       # retries above — a failure is never miscached as "not found"
            continue
        entities = _wikidata_entities([h["id"] for h in hits], props="labels|claims|sitelinks")
        for h in hits:
            qid = h["id"]
            ent = entities.get(qid)
            if not ent or not _looks_like_a_film(h, ent):
                continue
            en_name = (((ent.get("labels") or {}).get("en") or {}).get("value")
                       or ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title"))
            label = _norm_title(en_name)
            if not label or not want.startswith(label):
                continue
            if len(ent.get("sitelinks") or {}) < RERELEASE_MIN_SITELINKS:
                continue
            rt = _runtime_of(ent)
            if runtime and rt and abs(int(runtime) - rt) > RERELEASE_RUNTIME_TOLERANCE:
                continue
            lang_qid = LANG_QIDS.get(lang or "")
            langs = {v.get("id") for v in _claim_values(ent, "P364")}
            if lang_qid and langs and lang_qid not in langs:
                continue
            return qid
    return None


def _rerelease_ids(title, runtime=None, lang=None):
    """_wikidata_ids() for the re-release fallback: {} or the same dict with rerelease=True."""
    qid = _find_rerelease_qid(title, runtime, lang)
    if not qid:
        return {}
    out = _ids_for_qid(qid)
    if out:
        out["rerelease"] = True
    return out


def _wikidata_ids(title, accepted_years):
    """Returns a permanent-cacheable dict of ids/labels for a title, or {} if unmatched.

    May raise LookupFailed if a Wikidata call fails at the network/HTTP/parse level — the
    caller (enrich()) must not treat that the same as a confirmed empty match.
    """
    qid = _find_film_qid(title, accepted_years)
    if not qid:
        return {}
    return _ids_for_qid(qid)


def _ids_for_qid(qid):
    entities = _wikidata_entities([qid], props="labels|claims|sitelinks")
    ent = entities.get(qid)
    if not ent:
        return {}

    genre_ids = [v.get("id") for v in _claim_values(ent, "P136")]
    director_ids = [v.get("id") for v in _claim_values(ent, "P57")]
    cast_ids = [v.get("id") for v in _claim_values(ent, "P161")][:3]
    side_entities = _wikidata_entities(genre_ids + director_ids + cast_ids)

    runtimes = _claim_values(ent, "P2047")
    runtime = None
    if runtimes:
        try:
            runtime = round(float(str(runtimes[0]["amount"]).lstrip("+")))
        except (KeyError, TypeError, ValueError):
            runtime = None

    imdb_ids = _claim_values(ent, "P345")
    trailer = next((t for t in map(youtube_id, _claim_values(ent, "P1651")) if t), None)
    rt_ids = _claim_values(ent, "P1258")

    enwiki = ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title")
    return {
        "qid": qid,
        "enwiki": enwiki,
        "title_ar": _arabic_label(entities, qid),
        "year": _claim_year(ent),
        "runtime": runtime,
        "genres": {
            "en": [_label(side_entities, g, "en") for g in genre_ids if _label(side_entities, g, "en")],
            "ar": [_label(side_entities, g, "ar") for g in genre_ids if _label(side_entities, g, "ar")],
        },
        "director": next((_label(side_entities, d, "en") for d in director_ids
                           if _label(side_entities, d, "en")), None),
        "cast": [_label(side_entities, c, "en") for c in cast_ids if _label(side_entities, c, "en")],
        "imdb_id": imdb_ids[0] if imdb_ids else None,
        "trailer": trailer,  # P1651 YouTube video ID — the fallback when no chain publishes one
        # Wikidata's P1258 value is sometimes bare ("heart_of_the_beast") and sometimes
        # already prefixed with the RT URL segment ("m/heart_of_the_beast") — normalise to bare.
        "rt_id": re.sub(r"^m/", "", rt_ids[0]) if rt_ids else None,
    }


def _wikidata_trailer(qid):
    """P1651 (YouTube video ID) of one item — for cache entries written before ids carried it.
    Returns the id or None; raises LookupFailed on a network/HTTP failure."""
    ent = _wikidata_entities([qid], props="claims").get(qid) or {}
    return next((t for t in map(youtube_id, _claim_values(ent, "P1651")) if t), None)


# ---------- Rotten Tomatoes ----------

def _rt_release_year(html):
    """Pulls the release year RT itself prints for this page, from the `where-to-watch-json`
    block's `"releaseYear":"2026"` field. Not present under every id, so a miss returns None
    (treated as "can't verify" by the caller, not as a mismatch)."""
    m = re.search(r'"releaseYear"\s*:\s*"(\d{4})"', html)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _rt_ratings(rt_id, expected_year=None):
    """Scrape the RT page for tomatometer/popcornmeter numbers and the consensus line.

    If `expected_year` is given and the page's own release year is readable and differs,
    the whole result is dropped (None) rather than attached to the wrong film — this is the
    Wikidata-recorded rt_id turning out to point at the wrong RT entry (rare, but the exact
    shape of bug that put a 2016 "The Odyssey" number on the 2026 Nolan film before the
    Wikidata-side year guard existed). A page where the year can't be read at all is
    accepted leniently — we already trust the qid it came from.
    """
    r = _polite_get(f"https://www.rottentomatoes.com/m/{rt_id}")
    if r is None or r.status_code != 200:
        return None
    html = r.text
    if expected_year is not None:
        page_year = _rt_release_year(html)
        if page_year is not None and page_year != expected_year:
            return None
    m = re.search(r'id="media-scorecard-json"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        card = json.loads(m.group(1))
    except (ValueError, TypeError):
        return None

    critics = card.get("criticsScore", {})
    audience = card.get("audienceScore", {})

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    consensus = None
    cm = re.search(r'id="critics-consensus"[^>]*>.*?<p>(.*?)</p>', html, re.S)
    if cm:
        consensus = re.sub(r"<[^>]+>", "", cm.group(1)).strip()

    return {
        "critics": _int(critics.get("score")),
        "critics_count": _int(critics.get("reviewCount")),
        "audience": _int(audience.get("score")),
        "consensus": consensus,
        "url": f"https://www.rottentomatoes.com/m/{rt_id}",
    }


# ---------- Wikipedia synopsis ----------

def _wikipedia_summary(title):
    """The REST summary of one exact English Wikipedia page (the matched item's sitelink)."""
    r = _polite_get(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title.replace(' ', '_'), safe='')}"
    )
    if r is None or r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    extract = data.get("extract")
    return extract.strip() if extract else None


# ---------- main entry ----------

def _blank_film_fields(film):
    film.setdefault("title_ar", None)
    film.setdefault("year", None)
    film.setdefault("genres", [])
    film.setdefault("trailer", None)
    film.setdefault("director", None)
    film.setdefault("cast", [])
    film.setdefault("synopsis_en", None)
    film.setdefault("wikidata", {"qid": None})
    film.setdefault("imdb", {"id": None})
    film.setdefault("imdb_score", None)
    film.setdefault("rt", None)
    film.setdefault("poster", film.get("poster"))
    film.setdefault("post_credits", None)  # see post_credits_for() below — the field + UI slot exist; left empty for now


def enrich(data: dict, cache_path: str = "data/films_cache.json", offline: bool = False, titles_path: str | None = None) -> dict:
    """`titles_path`: the reviewed Arabic titles (default titles_ar.yaml beside this file)."""
    films = data.get("films", {})
    cache = _load_cache(cache_path)
    dirty = False
    current_year = datetime.now(timezone.utc).year

    # A "not_found" cached under an older LOOKUP_VERSION all become eligible for a retry at once
    # when the version bumps (e.g. this fix, 2: re-release fallback -> 3: widened search) — capped
    # here, oldest-checked first, so that doesn't throw every stale "not found" film at Wikidata
    # (and the phone) in a single run; the rest catch up on a later run.
    version_stale = sorted(
        (fid for fid, film in films.items()
         if (cache.get(fid) or {}).get("ids_status") == "not_found"
         and (cache[fid].get("lookup_v", 1) < LOOKUP_VERSION)),
        key=lambda fid: cache[fid].get("ids_checked_at") or "",
    )
    version_retry_batch = set(version_stale[:NOT_FOUND_RELOOKUP_CAP])

    for fid, film in films.items():
        _blank_film_fields(film)
        # search_title is an optional override for the Wikidata/Wikipedia query only — the
        # displayed film["title"] never changes. Useful when the UAE listing's title is
        # ambiguous (e.g. "Insidious" for a franchise with six films, "The Odyssey" which
        # collides with several older works of the same name).
        title = film.get("search_title") or film.get("title") or fid
        # A reader/caller can pin the exact expected year (e.g. from its own listing data);
        # otherwise accept the current or previous calendar year, which covers both a film
        # that opened late last year and is still in UAE cinemas, and one opening this year.
        year_hint = film.get("year_hint")
        accepted_years = {year_hint} if year_hint else {current_year, current_year - 1}

        entry = cache.get(fid, {})
        ids = entry.get("ids")
        # Backward-compatible status inference for a cache written before ids_status existed:
        # a truthy "ids" is treated as a confirmed "found" (unchanged behavior); a falsy one
        # with no status is unknown-provenance (could be an old permanent "not found" or a
        # pre-upgrade write) and is simply re-attempted once, which is always safe.
        ids_status = entry.get("ids_status") or ("found" if ids else None)
        ids_checked_at = entry.get("ids_checked_at")

        if ids_status == "found":
            should_attempt = False  # a confirmed match is permanent, never re-queried
        elif ids_status == "not_found":
            # a "not found" from before the current LOOKUP_VERSION is retried once, capped per
            # run (version_retry_batch above); otherwise the ordinary NOT_FOUND_TTL applies.
            should_attempt = fid in version_retry_batch or not _fresh(ids_checked_at, NOT_FOUND_TTL)
        elif ids_status == "error":
            should_attempt = not _fresh(ids_checked_at, ERROR_TTL)
        else:  # never attempted
            should_attempt = True

        if should_attempt and not offline:
            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                found = _wikidata_ids(title, accepted_years)
                if not found and not year_hint:
                    found = _rerelease_ids(title, film.get("runtime"), film.get("lang"))
            except LookupFailed:
                # Transient failure — do NOT overwrite a previously-found `ids` (there isn't
                # one, by construction of should_attempt, except in the "not_found"-retry
                # case where ids is already {} anyway) and do NOT mark this "not_found" — a
                # network blip must not permanently poison a film that was never actually
                # confirmed absent from Wikidata. Retried again after ERROR_TTL.
                entry["ids_status"] = "error"
                entry["ids_checked_at"] = now_iso
                dirty = True
                found = ids or {}
            except Exception:
                # An unexpected bug in our own parsing is not proof the film has no Wikidata
                # entry either — same conservative "error" treatment, not "not_found".
                entry["ids_status"] = "error"
                entry["ids_checked_at"] = now_iso
                dirty = True
                found = ids or {}
            else:
                entry["ids"] = found
                entry["ids_status"] = "found" if found else "not_found"
                entry["ids_checked_at"] = now_iso
                entry["lookup_v"] = LOOKUP_VERSION
                dirty = True
            ids = found

            # the plot only of the page Wikidata itself links to this film — never a title search
            if found and found.get("enwiki"):
                try:
                    syn = _wikipedia_summary(found["enwiki"])
                except Exception:
                    syn = None
                if syn:
                    entry["synopsis_en"] = syn
                    dirty = True

        ids = ids or {}
        if not ids.get("qid") and entry.pop("synopsis_en", None) is not None:
            dirty = True  # a synopsis without an accepted match is someone else's plot

        # title_ar is resolved after this loop (resolve_title_ar), once the Arabic labels are fresh
        film["rerelease"] = bool(ids.get("rerelease"))
        if ids.get("year"):
            film["year"] = ids["year"]
        if ids.get("runtime") and not film.get("runtime"):
            film["runtime"] = ids["runtime"]
        # genres: the chains' keys first, then Wikidata's labels folded onto the same key set
        chain_genres = film.get("genres")
        if isinstance(chain_genres, dict):
            chain_genres = genre_keys(chain_genres.get("en"))
        wd = ids.get("genres") or {}
        film["genres"] = merge_keys(chain_genres, genre_keys(wd.get("en") if isinstance(wd, dict) else wd))
        # trailer: the chain's own first; else Wikidata P1651 (from ids, or looked up once for an
        # older cache entry, re-checked after RATINGS_TTL when Wikidata had none)
        if not film.get("trailer") and ids.get("qid"):
            if "trailer" in ids:
                film["trailer"] = ids.get("trailer")
            else:
                if not offline and not _fresh(entry.get("wd_trailer_at"), RATINGS_TTL):
                    try:
                        entry["wd_trailer"] = _wikidata_trailer(ids["qid"])
                        entry["wd_trailer_at"] = datetime.now(timezone.utc).isoformat()
                        dirty = True
                    except Exception as e:  # noqa: BLE001 - retried next run; say so, don't hide it
                        print(f"enrich: Wikidata trailer lookup for {fid} ({ids['qid']}) failed: {e}",
                              file=sys.stderr)
                film["trailer"] = youtube_id(entry.get("wd_trailer"))
        if ids.get("director"):
            film["director"] = ids["director"]
        if ids.get("cast"):
            film["cast"] = ids["cast"]
        film["wikidata"] = {"qid": ids.get("qid")}
        film["imdb"] = {"id": ids.get("imdb_id")}
        film["imdb_score"] = None  # no OMDb key — filled later by hand
        if entry.get("synopsis_en") and ids.get("qid"):
            film["synopsis_en"] = entry["synopsis_en"]

        rt_id = ids.get("rt_id")
        ratings = entry.get("ratings")
        ratings_at = entry.get("ratings_at")
        need_ratings = rt_id and not offline and (ratings is None or not _fresh(ratings_at, RATINGS_TTL))
        if need_ratings:
            # Guard against a stale/wrong Wikidata rt_id: the RT page's own release year must
            # match the year Wikidata recorded for this same qid, or the rating is dropped.
            try:
                fresh_ratings = _rt_ratings(rt_id, expected_year=ids.get("year"))
            except Exception:
                fresh_ratings = None
            if fresh_ratings:
                ratings = fresh_ratings
                ratings_at = datetime.now(timezone.utc).isoformat()
                entry["ratings"] = ratings
                entry["ratings_at"] = ratings_at
                dirty = True

        film["rt"] = ratings

        cache[fid] = entry

    # each film's Wikidata item (its own match, or the one titles_ar.yaml names): its Arabic label and aliases,
    # re-read every AR_TTL in one batched call (W1-D2). The cached read is tied to its qid, so a changed item is
    # read again at once, never shown under the old item's name.
    problems = []
    listed = load_titles_ar(titles_path, problems)
    qids = {fid: (listed.get(fid) or {}).get("qid") or ((cache.get(fid) or {}).get("ids") or {}).get("qid") for fid in films}
    qids = {fid: q for fid, q in qids.items() if q}
    due = {fid: q for fid, q in qids.items()
           if ((cache.get(fid) or {}).get("ar") or {}).get("qid") != q or not _fresh(cache[fid]["ar"].get("at"), AR_TTL)}
    if due and not offline:
        try:
            got = _wikidata_ar(due.values())
        except Exception as e:  # noqa: BLE001 - retried next run; the titles we had stay
            print(f"enrich: Wikidata Arabic labels failed: {e}", file=sys.stderr)
            got = {}
        at = datetime.now(timezone.utc).isoformat()
        for fid, q in due.items():
            if q in got:   # an item gone from Wikidata keeps what we had, and is asked again after AR_TTL
                old = (cache.get(fid) or {}).get("ar") or {}
                cache.setdefault(fid, {})["ar"] = {**(old if old.get("qid") == q else {}), **(got[q] or {}), "qid": q, "at": at}
                dirty = True

    for fid, film in films.items():
        entry = cache.get(fid) or {}
        ids, q = entry.get("ids") or {}, qids.get(fid)
        ar = entry.get("ar") if q and (entry.get("ar") or {}).get("qid") == q else {}
        # a read of the item wins, even an empty one; before the first read, the label its own match stored
        label = ar["label"] if "label" in ar else (ids.get("title_ar") if not q or q == ids.get("qid") else None)
        title, src, aka = resolve_title_ar(film, label, ar.get("aliases") or (), listed.get(fid))
        film["title_ar"], film["title_ar_src"], film["aka_ar"] = title, src, aka
    data["titles_ar"] = titles_report(films, listed, data.get("shows"), problems)

    if dirty and not offline:
        _save_cache(cache_path, cache)

    return data


# ---------------------------------------------------------------------------------------------
# Phase 2, task 6 (docs/superpowers/specs/2026-09-27-phase2-design.md, section B): post-credits
# scene, "only from a sourced dataset (Wikipedia/Wikidata or a named site); otherwise nothing."
#
# Checked (2026-09-27, offline research, no network access from this session to re-verify):
# Wikidata has no dedicated property for "has a post-credits scene" — P... none of the film
# properties (P462 color, P2047 duration, P364 language, etc.) cover it, and neither Wikidata
# nor the English Wikipedia infobox schema carries this as a structured field; it only ever
# shows up as unstructured prose inside a "Home media" or trivia section, which is not a named,
# fetchable dataset we can cite a URL for per-film. Per the spec's own fallback ("if none
# reliable, implement the field + UI slot and leave it empty, report"): film["post_credits"] is
# now always present (see _blank_film_fields above, default None) and pages/seasons.py renders
# its slot only when a value is set, so wiring in a real source later (a specific named site,
# once one is chosen and approved) needs no schema change here or in the page module.
#
# post_credits_for() is the seam for that future source: still a stub, on purpose, until a
# reliable one is chosen. It must never guess -- returning a made-up True/False would be the
# same mistake enrich.py's module docstring already rejects for TMDB/OMDb ("no key exists and
# none is created... no invention").
def post_credits_for(qid: str | None) -> dict | None:  # pragma: no cover - stub, no source wired yet
    """{"has": bool, "note": str|None, "source": url} once a reliable dataset is wired in; None
    (unknown, shown as nothing) until then. `qid` (Wikidata id) is the seam a real source hangs
    off of -- unused for now."""
    return None


# ---------------------------------------------------------------------------------------------
# The weekly look (owner default D12): `python enrich.py titles [data/latest.json]`

def _yaml_line(fid, ar, en, note, pin=False, review=True):
    q = lambda x: json.dumps(x or "", ensure_ascii=False)
    parts = [f"ar: {q(ar)}", f"en: {q(en)}"] + ["pin: true"] * bool(pin) + ["review: true"] * bool(review)
    return f"  # {fid}: {{{', '.join(parts)}}}   # {note}"


def main(argv=None):
    """Prints every titles_ar.yaml entry still awaiting review, every film with no Arabic title at all and every
    entry enrich could not use, busiest first. Every line is a YAML comment, so pasting the output into
    titles_ar.yaml changes nothing until the owner acts: approve = delete `review: true` from that film's line in
    the file; a film with no entry = write its Arabic and remove the leading "# "."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "titles":
        print("usage: python enrich.py titles [data/latest.json]", file=sys.stderr)
        return 2
    path = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "latest.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    films = data.get("films") or {}
    rep = data.get("titles_ar")
    if not rep:
        problems = []
        rep = titles_report(films, load_titles_ar(problems=problems), data.get("shows"), problems)
    say = lambda r: ", ".join(x for x in (r.get("kind"), f"{r['shows']} shows", r.get("lang") or "language unknown") if x)
    print(f"# awaiting review ({len(rep['review'])}): in titles_ar.yaml, delete `review: true` from a line to publish it")
    for r in rep["review"]:
        now = f", replaces «{r['now']}»" if r.get("now") else ""
        print(_yaml_line(r["fid"], r["ar"], r["title"], say(r) + now, r.get("pin")))
    print(f"# no Arabic title and no entry ({len(rep['missing'])}): write the Arabic, then remove the leading \"# \"")
    for r in rep["missing"]:
        print(_yaml_line(r["fid"], "", r["title"], say(r), review=False))
    if rep.get("invalid"):
        print(f"# entries enrich could not use ({len(rep['invalid'])}):")
        for r in rep["invalid"]:
            print(f"#   {r['fid']}: {r['why']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
