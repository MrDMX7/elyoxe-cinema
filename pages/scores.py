"""«الأحسن تقييم» (the trust sweep, W0-P3, plan §4.1 #25): the sort ranks films by critics + audience, and the
verdict only breaks ties (it used to rank by verdict alone, so «يستاهل» films with no score at all came first).

A tile prints one score at most, so each page with the sort (home, city, cinema) carries its films' two numbers
as a small JSON island, read by src/js/filters.js (scoreRank):

    <script type="application/json" id="cinema-sc">{"fid": [critics, audience], …}</script>

Either number may be null; a film with neither is left out. The numbers are the film page's own (films[fid].rt),
so the sort and the film page never disagree."""
import json

from site_kit import Plugin


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def scores(site, fids):
    """{fid: [critics, audience]} for the films in `fids` that have at least one of the two."""
    out = {}
    for fid in sorted(set(fids)):
        rt = (site.films.get(fid) or {}).get("rt") or {}
        c, a = _n(rt.get("critics")), _n(rt.get("audience"))
        if c is not None or a is not None:
            out[fid] = [c, a]
    return out


def island(site, fids):
    j = json.dumps(scores(site, fids), ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/json" id="cinema-sc">{j}</script>'


def _home(site, lang):
    return island(site, {s["film"] for s in site.shows})


def _city(site, lang, city=None):
    return island(site, {s["film"] for s in site.shows if site.cinemas[s["cinema"]].get("city") == city})


def _cinema(site, lang, cid=None):
    return island(site, {s["film"] for s in site.shows if s["cinema"] == cid})


def register(site):
    return Plugin(slots={"home.after_tonight": _home, "city.after_tonight": _city, "cinema.after_halls": _cinema})
