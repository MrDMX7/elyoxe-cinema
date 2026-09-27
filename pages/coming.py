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

from site_kit import L, NavItem, P, Page, Pages, Plugin, esc, genre_words, hue, human_date, rel

TITLE = ("نازل الخميس", "Out Thursday")
CSS = ("coming",)
LAZY_JS = ()
DIRS = ("coming",)


def _thursday_of(iso_date: str) -> str:
    """The Thursday of the ISO week `iso_date` falls in (UAE releases land on Thursdays)."""
    d = dt.date.fromisoformat(iso_date)
    return (d + dt.timedelta(days=(3 - d.weekday()) % 7)).isoformat()


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
        for fid, f in coming.items():
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
            return "غداً" if lang == "ar" else "Tomorrow"
        return (f"بعد {days} يوم" if lang == "ar" else f"In {days} days")

    def _card(self, fid, f, lang):
        pc = hue(fid)
        img = (f'<span class="cs-p img" style="--pc:{pc}"><img src="{esc(rel(f["poster"]))}" alt="" loading="lazy" width="200" height="300"></span>'
               if f.get("poster") else f'<span class="cs-p" style="--pc:{pc}"><span class="cs-t">{esc(f["title"])}</span></span>')
        title_ar = f.get("title_ar")
        titles = (f'<span class="cs-n">{esc(f["title"])}</span>' + (f'<bdi class="cs-ar">{esc(title_ar)}</bdi>' if title_ar and lang == "ar" else "")
                  if lang == "en" or not title_ar else f'<span class="cs-n">{esc(title_ar)}</span><bdi class="cs-ar" lang="en">{esc(f["title"])}</bdi>')
        genres = genre_words(f.get("genres") or [], lang)
        meta = "، ".join(genres[:2]) if lang == "ar" else ", ".join(genres[:2])
        cd = self._countdown(f["release_date"], lang) if f.get("release_date") else ("قريباً" if lang == "ar" else "Coming soon")
        chains = ", ".join(sorted(f.get("chains") or []))
        trailer = (f'<a class="cs-yt" href="https://www.youtube-nocookie.com/embed/{esc(f["trailer"])}" '
                   f'data-trailer="{esc(f["trailer"])}" rel="noopener" target="_blank">'
                   f'{"العرض الترويجي" if lang == "ar" else "Trailer"}</a>') if f.get("trailer") else ""
        notify = (f'<button type="button" class="btn ghost cs-notify" disabled>'
                  f'{"نبّهني" if lang == "ar" else "Notify me"}</button>')
        return (f'<li class="cs-card">{img}<div class="cs-info">{titles}'
                + (f'<span class="cs-meta">{esc(meta)}</span>' if meta else "")
                + f'<span class="cs-cd">{esc(cd)}</span>'
                + (f'<span class="cs-chains">{esc(chains)}</span>' if chains else "")
                + f'<div class="cs-act">{trailer}{notify}</div></div></li>')

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
