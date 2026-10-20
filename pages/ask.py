"""«اسأل الفيلم» (owner 2026-10-18): on a film page, a visitor asks the film a question («شو نوعه؟», «شو يصير بعد ما
يسرقون السيارة؟») and gets one short, exact answer — from the film's own facts and its English Wikipedia plot, never
from anywhere else; an answer that gives the story away sits behind a tap.

This module is the site's half:
  /data/ask/<fid>.json   the facts the answer may use, one small file per showing film: titles, year, runtime, the UAE
                         age rating, language, genres, director and cast (names), release date, synopses, critics and
                         audience scores, our own verdict, where it is showing and from what price, and the Wikidata id
                         (the backend finds the Wikipedia plot from it). Nothing here is new: every value is already on
                         the film's page.
  film.ask slot          the «اسأل الفيلم» tab's panel: a question box and a few ready questions (script-only — the
                         answer needs the backend; with no script the tab is not drawn, like «قارن»).
  ask.js                 a lazy chunk on film pages: sends {fid, q, lang, uid} to counter.yaml's ask_api, draws the
                         answer, hides a spoiler behind «يحرق — اضغط لتشوف».
The backend (infra/ask: Lambda + DynamoDB, Claude Haiku 5.5) owns caching, the daily caps and the kill switch."""
from site_kit import Plugin, esc, genre_words, lang_words, money

LAZY_JS = ("ask",)
CSS = ("ask",)

T = {
    "h": ("اسأل الفيلم", "Ask the film"),
    "lead": ("اسأل أي شي عن الفيلم، ونجاوبك من قصته ومعلوماته بس. الجواب اللي يحرق نخفيه لين تضغط.",
             "Ask anything about the film. Answers come only from its story and facts; anything that spoils it stays hidden until you tap."),
    "ph": ("مثلاً: يناسب العيال؟", "e.g. Is it OK for kids?"),
    "go": ("اسأل", "Ask"),
}
CHIPS = {
    "ar": ["شو نوع الفيلم؟", "يناسب العيال؟", "عن شو القصة؟", "كم مدته؟", "منو الأبطال؟", "شو يصير في النهاية؟"],
    "en": ["What kind of film is it?", "Is it OK for kids?", "What's the story?", "How long is it?", "Who's in it?", "How does it end?"],
}


def _late(t):
    """A show's place in its cinema day: 00:45 is that night's last show, after 23:30."""
    return (t < "04:00", t)


def schedule(site, shows):
    """Our own showing facts (owner 2026-10-20): per day, how many shows and the first and last; the hall formats and
    in how many cinemas; the subtitle and audio languages; the cheapest seat and where. Times are 24h UAE time, and the
    day's counts are what was still to come when the data was read (as_of)."""
    out = {"as_of": str(site.d.get("generated") or "")[:16].replace("T", " ")}
    for label, day in (("today", site.today), ("tomorrow", site.tomorrow)):
        ts = sorted((s["time"] for s in shows if s["date"] == day), key=_late)
        if ts:
            out[label] = {"date": day, "shows_to_come": len(ts), "next_show": ts[0], "last_show": ts[-1]}
    halls = {}
    for s in shows:
        h = site.hname(s, "en")
        if h and site.hkey(s) != "Standard":
            halls.setdefault(h, set()).add(s["cinema"])
    if halls:
        out["special_halls_cinema_count"] = {h: len(c) for h, c in sorted(halls.items(), key=lambda x: -len(x[1]))}
    subs = sorted({k for s in shows for k in str(s.get("subs") or "").split("+") if k})
    if subs:
        out["subtitles"] = lang_words("+".join(subs), "en")
    langs = sorted({s.get("lang") for s in shows if s.get("lang")})
    if langs:
        out["audio"] = lang_words("+".join(langs), "en")
    best = None
    for s in shows:
        for pr in s.get("prices") or []:
            if (pr.get("aed") or 0) > 0 and (best is None or pr["aed"] < best[0]):
                best = (pr["aed"], s)
    if best:
        out["cheapest"] = {"aed": float(money(best[0])), "cinema": site.cname(best[1]["cinema"], "en"),
                           "hall": site.hname(best[1], "en"), "date": best[1]["date"], "time": best[1]["time"]}
    return out if len(out) > 1 else {}


def facts(site, fid, ppl=None):
    """The one JSON the backend answers from (all English keys; values in the site's own words)."""
    f = site.films[fid]
    rt = f.get("rt") or {}
    vd = f.get("verdict") or {}
    shows = [s for s in site.shows if s["film"] == fid]
    cities = sorted({site.cinemas[s["cinema"]].get("city") for s in shows if site.cinemas[s["cinema"]].get("city")})
    prices = [p["aed"] for s in shows for p in (s.get("prices") or []) if (p.get("aed") or 0) > 0]
    cast = []
    for q in f.get("cast") or []:
        if ppl and q in ppl.p:
            cast.append(ppl.name(q, "en"))
        elif isinstance(q, str) and not q.startswith("Q"):
            cast.append(q)
    out = {
        "fid": fid, "title": f.get("title"), "title_ar": f.get("title_ar"), "year": f.get("year"),
        "runtime_min": f.get("runtime"), "uae_age_rating": f.get("rating"),
        "language": lang_words(f["lang"], "en") if f.get("lang") else None,
        "genres": genre_words(f.get("genres"), "en") or None,
        "director": f.get("director"), "cast": cast[:10] or None,
        "uae_release_date": f.get("released"), "re_release": bool(f.get("rerelease")) or None,
        "synopsis_en": f.get("synopsis_en"), "synopsis_ar": f.get("synopsis_ar"),
        "rotten_tomatoes": {"critics_pct": rt.get("critics"), "critics_count": rt.get("critics_count"),
                            "audience_pct": rt.get("audience"), "consensus": rt.get("consensus")} if rt else None,
        "imdb_score": f.get("imdb_score"),
        "our_verdict": {"word": vd.get("verdict"), "ar": vd.get("ar"), "en": vd.get("en")} if vd.get("verdict") not in (None, "unknown") else None,
        "post_credits_scene": f.get("post_credits") or None,
        "family_friendly": bool(f.get("family")) or None, "for_kids": bool(f.get("kids")) or None,
        "showing_in_uae": {"cities": cities, "cinemas": len({s["cinema"] for s in shows}),
                           "chains": sorted({site.cinemas[s["cinema"]]["chain"] for s in shows}),
                           "from_aed": float(money(min(prices))) if prices else None} if shows else None,
        "schedule_uae": schedule(site, shows) or None,
        "qid": (f.get("wikidata") or {}).get("qid"),
    }
    return {k: v for k, v in out.items() if v not in (None, [], {}, "")}


def panel(site, lang, fid):
    ar = lang == "ar"
    if site.films[fid].get("status") == "archived":
        return ""
    chips = "".join(f'<li><button type="button" class="ask-chip" data-ask-q="{esc(c)}">{esc(c)}</button></li>' for c in CHIPS[lang])
    # hidden until ask.js shows it (not .js-only: that class makes a flex row of the panel once .js is on <html>)
    return (f'<div class="ask" data-ask data-fid="{esc(fid)}" hidden>'
            f'<h2 class="tp-h">{esc(T["h"][0 if ar else 1])}</h2><p class="ask-lead">{esc(T["lead"][0 if ar else 1])}</p>'
            f'<form class="ask-f" data-ask-form><label class="vh" for="ask-q">{esc(T["h"][0 if ar else 1])}</label>'
            f'<input id="ask-q" name="q" type="text" maxlength="240" autocomplete="off" enterkeyhint="send" placeholder="{esc(T["ph"][0 if ar else 1])}">'
            f'<button type="submit" class="btn velvet">{esc(T["go"][0 if ar else 1])}</button></form>'
            f'<ul class="ask-chips">{chips}</ul><div class="ask-out" data-ask-out aria-live="polite"></div></div>')


def register(site):
    try:
        from pages.people import People
        ppl = People(site)
    except Exception:   # a build without the people module still answers from the rest
        ppl = None
    data = {f"data/ask/{fid}.json": (lambda fid=fid: facts(site, fid, ppl)) for fid in site.showing}
    return Plugin(data=data, slots={"film.ask": panel}, page_js={"film": ("ask",)})
