"""pages/hubs.py (Task 2, design spec A): /arabic/ (Gulf & Arabic films) + /events/ (chain-labelled
special events). The «آخر فرصة» strip that sat in home.after_tonight / city.after_tonight is deleted
(W0-P2, MASTER-PLAN §4.1 #13): steps/last_chance.py is switched off until a real signal exists, and a strip
brought back then is built on that signal, not on this one.

/arabic/: films from `site.showing` whose `lang` is Arabic (data's own film-level `lang`, the
same field core.py's ticket already reads -- never guessed at from title or chain). "Produced in
the Gulf" (the design spec's other half of this hub) has no signal anywhere in the data yet (no
reader captures a film's production country) -- left out rather than inferred; see
task-2-report.md.

/events/: fix round 1 (review, Critical) -- reads `data["events"]` (steps/events.py, one entry
per recognised chain-labelled event with >= 1 match: K-Fest, Immersive Dining, ... -- see that
step's own docstring and events.yaml for how the label survives normalize.py's title cleanup;
confirmed against the live data/raw/*.json in this worktree). When there are genuinely none, the
empty state is `NOINDEX` (site_kit.py's own constant, the same one `pages/seasons.py`'s
`build_summer` uses) and excluded from the sitemap-eligible set via `path=` -- `site_kit.py:995`
(`page()`) only appends a page's `parts` to `self.urls` when `path is None`, the same mechanism
`pages/core.py`'s own noindexed card-stub and 404 pages already use for this exact purpose.
Fix round 2 (re-review, Critical persisted): round 1 mistakenly made this state indexable
instead, reasoning that `tests/test_preview.py::test_default_build_stays_indexable` (a
pre-existing, project-wide "no page is noindex outside its own named exemptions" contract)
would fail against `fixtures/sample_latest.json`'s empty `events` data -- true, but the fix was
to add a third exemption there (the file already exempts the unconfirmed-discount-card URL the
same way, one line with a comment), not to revert the page. That exemption is now in place.
"""
import os

from site_kit import NOINDEX, L, NavItem, P, Page, Pages, Plugin, esc

TITLE_AR = ("عربي وخليجي", "Arabic & Gulf")
TITLE_EV = ("فعاليات", "Events")
CSS = ("hubs",)
LAZY_JS = ()
DIRS = ("arabic", "events")

_ARABIC_LANGS = {"arabic", "ar"}


def register(site):
    p = HubPages(site)
    return Plugin(
        pages=[Page(("arabic",), lang, lambda lang=lang: p.arabic_page(lang)) for lang in ("ar", "en")]
        + [Page(("events",), lang, lambda lang=lang: p.events_page(lang)) for lang in ("ar", "en")],
        nav=[NavItem("arabic", href=lambda lang: P(lang, "arabic"), label=TITLE_AR),
             NavItem("events", href=lambda lang: P(lang, "events"), label=TITLE_EV)])


class HubPages(Pages):
    # -------------------------------------------------------------- /arabic/
    def arabic_films(self):
        return [fid for fid in self.showing if str(self.films[fid].get("lang") or "").lower() in _ARABIC_LANGS]

    def arabic_page(self, lang):
        fids = self.arabic_films()
        title = L(TITLE_AR, lang)
        desc = ("أفلام عربية وخليجية تُعرض الحين في الإمارات." if lang == "ar"
                else "Arabic and Gulf films showing now in the UAE.")
        head = f'<section class="head wrap">{self.crumbs(lang, (title, None))}<h1 class="pt">{esc(title)}</h1>' \
               f'<p class="lead">{esc(desc)}</p></section>'
        if fids:
            tiles = "".join(self.film_tile(fid, lang, self.shows, i=i) for i, fid in enumerate(fids))
            body = head + f'<section class="wrap"><div class="posters">{tiles}</div></section>'
        else:
            empty = "ما في فيلم عربي أو خليجي معروض الحين." if lang == "ar" else "No Arabic or Gulf film showing right now."
            body = head + f'<section class="wrap"><p class="empty">{esc(empty)}</p></section>'
        graph = [self.breadcrumb_ld(lang, (title, P(lang, "arabic")))]
        return {"title": title, "desc": desc, "body": body, "kind": "arabic", "nav": "arabic", "graph": graph}

    # -------------------------------------------------------------- /events/
    def events_list(self):
        """data["events"] (steps/events.py), each with its recognised name in this language and
        only the fids that are still real film pages (film_fid on a raw title always matches a
        real data["films"] entry once that film is merged -- see steps/events.py's docstring --
        but this stays defensive rather than assuming it)."""
        return [ev for ev in (self.d.get("events") or []) if any(fid in self.films for fid in ev.get("fids") or [])]

    def events_page(self, lang):
        title = L(TITLE_EV, lang)
        events = self.events_list()
        desc = ("فعاليات السينمات: مهرجانات، ليالي خاصة، وعروض كلاسيكية." if lang == "ar"
                else "Cinema chains' own events: festivals, special nights, and classics screenings.")
        head = f'<section class="head wrap">{self.crumbs(lang, (title, None))}<h1 class="pt">{esc(title)}</h1>' \
               f'<p class="lead">{esc(desc)}</p></section>'
        if events:
            sections = []
            for ev in events:
                name = (ev.get("name_ar") if lang == "ar" else ev.get("name_en")) or ev["label"]
                rows = "".join(
                    f'<div class="row"><a class="nm" href="{P(lang, "film", fid)}">{esc(self.ftitle(fid, lang))}</a></div>'
                    for fid in ev.get("fids") or [] if fid in self.films)
                sections.append(f'<section class="wrap ev-block"><h2>{esc(name)}</h2><div class="rows">{rows}</div></section>')
            body = head + "".join(sections)
            graph = [self.breadcrumb_ld(lang, (title, P(lang, "events")))]
            return {"title": title, "desc": desc, "body": body, "kind": "events", "nav": "events", "graph": graph}
        # genuinely empty: noindex and out of the sitemap (fix round 2) -- `path=` matches this
        # exact output location so the file is still written normally, just never added to
        # self.urls (site_kit.py's own page() only tracks a page for the sitemap when path is
        # None), and tests/test_preview.py carries a matching exemption for this honest state.
        empty = ("ما عندنا فعاليات مؤكدة من السينمات الحين — نضيفها أول ما تعلنها سينما." if lang == "ar"
                 else "No chain-confirmed events yet — added as soon as a chain announces one.")
        body = head + f'<section class="wrap"><p class="empty">{esc(empty)}</p></section>'
        graph = [self.breadcrumb_ld(lang, (title, P(lang, "events")))]
        return {"title": title, "desc": desc, "body": body, "kind": "events", "nav": "events", "graph": graph,
                "robots": NOINDEX,
                "path": os.path.join(self.out, *(["en"] if lang == "en" else []), "events", "index.html")}
