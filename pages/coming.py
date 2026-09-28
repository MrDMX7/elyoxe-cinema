"""pages/coming.py (Task 2, design spec A): «نازل الخميس» — /coming/ (+ /en/), a grid of films the
chains have announced grouped by their release Thursday, with a countdown only for films that
have a real release date (undated films sit in their own "date to be announced" group).

Data: steps/coming.py's data["coming"][fid] = {"title","title_ar","release_date","poster",
"trailer","genres","chains"} -- these are NOT in `site.films` (they aren't showing yet), so this
page never calls site.poster()/site.film_tile() (those index self.films by fid); it renders its
own small card directly from the coming-soon record.

The nav key "thursday" re-points the built-in «نازل الخميس» header link (PLUGINS.md's nav table)
from the home page to here.
"""
from __future__ import annotations

import datetime as dt
import html
import re

from genres import GENRES, genre_keys
from normalize import film_fid
from site_kit import L, NavItem, P, Page, Pages, Plugin, ar_count, esc, hue, human_date, rel

TITLE = ("نازل الخميس", "Out Thursday")
CSS = ("coming",)
LAZY_JS = ()
DIRS = ("coming",)


def _thursday_of(iso_date: str) -> str:
    """The Thursday that opens the release week `iso_date` falls in (UAE releases land on Thursdays): Monday to
    Wednesday belong to the coming Thursday, Thursday to itself, and Friday to Sunday to the Thursday before --
    a Friday 2 October release opened with the 1 October slate, not the 8 October one."""
    d = dt.date.fromisoformat(iso_date)
    return (d + dt.timedelta(days=3 - d.weekday())).isoformat()


_RERELEASE = re.compile(r"-?re-?release$")


def _title_key(title: str) -> str:
    """normalize.film_fid's slug of the decoded title, without hyphens or a re-release tag: the
    chains' own spellings of one film ("Don&#39;t…", "Don't…", "Dont… (Telugu)") meet here."""
    return _RERELEASE.sub("", film_fid(html.unescape(title or ""))).replace("-", "")


def _edits(a: str, b: str) -> int:
    """Levenshtein distance (the titles are short; a plain two-row table is enough)."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _same_title(a: str, b: str) -> bool:
    """One film under two spellings (final review M1: "The Legendaires"/"The Legendaries"): the same
    key, or at most 2 edits apart when both keys are 10+ letters long and carry the same numbers
    (so "Golmaal 4"/"Golmaal 5" and short titles like "Wake"/"Make" never fold)."""
    ka, kb = _title_key(a), _title_key(b)
    if ka == kb:
        return bool(ka)
    if min(len(ka), len(kb)) < 10 or re.findall(r"\d+", ka) != re.findall(r"\d+", kb):
        return False
    return _edits(ka, kb) <= 2


def fold_near_duplicates(coming: dict) -> list:
    """[(fid, film)] with near-identical titles on the same release date merged into one card: the
    spelling most chains use (then the shorter fid) names it, chains and genres are the union, and
    poster/trailer come from whichever entry has them. Titles are HTML-unescaped once for display."""
    groups: list[list] = []
    for fid, f in sorted(coming.items()):
        for g in groups:
            if g[0][1].get("release_date") == f.get("release_date") and _same_title(g[0][1]["title"], f["title"]):
                g.append((fid, f))
                break
        else:
            groups.append([(fid, f)])
    out = []
    for g in groups:
        g.sort(key=lambda kv: (-len(kv[1].get("chains") or []), len(kv[0]), kv[0]))
        fid, base = g[0]
        f = dict(base, title=html.unescape(base["title"]),
                 title_ar=html.unescape(base["title_ar"]) if base.get("title_ar") else base.get("title_ar"))
        f["chains"] = sorted({c for _, x in g for c in (x.get("chains") or [])})
        f["genres"] = [x for _, m in g for x in (m.get("genres") or [])]
        for k in ("poster", "trailer", "title_ar"):
            if not f.get(k):
                f[k] = next((m[k] for _, m in g if m.get(k)), f.get(k))
        out.append((fid, f))
    return out


def genre_labels(raw, lang) -> list:
    """The chains' raw genre words through genres.py's vocabulary; a word it does not know is left
    out (never printed in English on the Arabic page, never shown as «أخرى»)."""
    return [GENRES[k][0 if lang == "ar" else 1] for k in genre_keys(raw or []) if k != "other"]


def register(site):
    p = ComingPages(site)
    return Plugin(
        pages=[Page(("coming",), lang, lambda lang=lang: p.coming_page(lang)) for lang in ("ar", "en")],
        data={"data/coming.json": lambda: {fid: f for fid, f in (site.d.get("coming") or {}).items()}},
        nav=[NavItem("thursday", href=lambda lang: P(lang, "coming"))])


class ComingPages(Pages):
    def _groups(self):
        """{thursday-iso|None: [(fid, film), ...]} sorted by date, undated (None) group last."""
        coming = self.d.get("coming") or {}
        groups: dict = {}
        for fid, f in fold_near_duplicates(coming):
            key = _thursday_of(f["release_date"]) if f.get("release_date") else None
            groups.setdefault(key, []).append((fid, f))
        for key in groups:
            groups[key].sort(key=lambda kv: kv[1]["title"])
        return dict(sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0] or "")))

    def _countdown(self, release_date, lang):
        days = (dt.date.fromisoformat(release_date) - self.now.date()).days
        if days < 0:
            return ""
        if days == 0:
            return "اليوم" if lang == "ar" else "Today"
        if days == 1:
            return "بكرة" if lang == "ar" else "Tomorrow"
        return ("بعد " + ar_count(days, ("يوم", "يومين", "أيام", "يوم"))) if lang == "ar" else f"In {days} days"

    def _card(self, fid, f, lang):
        pc = hue(fid)
        img = (f'<span class="cs-p img" style="--pc:{pc}"><img src="{esc(rel(f["poster"]))}" alt="" loading="lazy" width="200" height="300"></span>'
               if f.get("poster") else f'<span class="cs-p" style="--pc:{pc}"><span class="cs-t">{esc(f["title"])}</span></span>')
        title_ar = f.get("title_ar")
        titles = (f'<span class="cs-n">{esc(f["title"])}</span>' + (f'<bdi class="cs-ar">{esc(title_ar)}</bdi>' if title_ar and lang == "ar" else "")
                  if lang == "en" or not title_ar else f'<span class="cs-n">{esc(title_ar)}</span><bdi class="cs-ar" lang="en">{esc(f["title"])}</bdi>')
        sep = "، " if lang == "ar" else ", "
        meta = sep.join(genre_labels(f.get("genres"), lang)[:2])
        cd = self._countdown(f["release_date"], lang) if f.get("release_date") else ("قريباً" if lang == "ar" else "Coming soon")
        chains = sep.join(self.h.chain_name(c, lang) for c in sorted(f.get("chains") or []))
        trailer = (f'<a class="cs-yt" href="https://www.youtube-nocookie.com/embed/{esc(f["trailer"])}" '
                   f'data-trailer="{esc(f["trailer"])}" rel="noopener" target="_blank">'
                   f'{"العرض الترويجي" if lang == "ar" else "Trailer"}</a>') if f.get("trailer") else ""
        return (f'<li class="cs-card">{img}<div class="cs-info">{titles}'
                + (f'<span class="cs-meta">{esc(meta)}</span>' if meta else "")
                + f'<span class="cs-cd">{esc(cd)}</span>'
                + (f'<span class="cs-chains">{esc(chains)}</span>' if chains else "")
                + (f'<div class="cs-act">{trailer}</div>' if trailer else "") + '</div></li>')

    def coming_page(self, lang):
        title = L(TITLE, lang)
        desc = ("الأفلام النازلة قريباً في سينمات الإمارات، حسب أسبوع نزولها." if lang == "ar"
                else "Films announced by UAE cinema chains, grouped by the week they open.")
        head = f'<section class="head wrap">{self.crumbs(lang, (title, None))}<h1 class="pt">{esc(title)}</h1><p class="lead">{esc(desc)}</p></section>'
        groups = self._groups()
        sections = []
        for key, items in groups.items():
            if key:
                heading = human_date(key, lang)
            else:
                heading = "التاريخ لاحقاً" if lang == "ar" else "Date to be announced"
            cards = "".join(self._card(fid, f, lang) for fid, f in items)
            sections.append(f'<section class="wrap cs-week"><h2>{esc(heading)}</h2><ul class="cs-grid">{cards}</ul></section>')
        if sections:
            body = head + "".join(sections)
        else:
            empty = "ما عندنا أفلام نازلة قريباً معروفة الحين." if lang == "ar" else "Nothing announced by the chains yet."
            body = head + f'<section class="wrap"><p class="empty">{esc(empty)}</p></section>'
        graph = [self.breadcrumb_ld(lang, (title, P(lang, "coming")))]
        return {"title": title, "desc": desc, "body": body, "kind": "coming", "nav": "thursday", "graph": graph}
