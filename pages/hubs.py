"""pages/hubs.py (Task 2, design spec A): /arabic/ (Gulf & Arabic films) + /events/ (chain-labelled
special events), and the «آخر فرصة» strip on home + city pages (Kit.SLOTS: home.after_tonight,
city.after_tonight -- the extension hooks PLUGINS.md offers; no new hook was needed).

/arabic/: films from `site.showing` whose `lang` is Arabic (data's own film-level `lang`, the
same field core.py's ticket already reads -- never guessed at from title or chain). "Produced in
the Gulf" (the design spec's other half of this hub) has no signal anywhere in the data yet (no
reader captures a film's production country) -- left out rather than inferred; see
task-2-report.md.

/events/: fix round 1 (review, Critical) -- reads `data["events"]` (steps/events.py, one entry
per recognised chain-labelled event with >= 1 match: K-Fest, Immersive Dining, ... -- see that
step's own docstring and events.yaml for how the label survives normalize.py's title cleanup;
confirmed against the live data/raw/*.json in this worktree, so the empty state below is no
longer the expected case in production). When there are genuinely none, the page stays an
honest "none yet" empty state -- indexable, same as `/arabic/`'s own empty state, and unlike the
review's "at minimum" noindex fallback suggestion: `tests/test_preview.py::
test_default_build_stays_indexable` (a pre-existing, project-wide contract this task doesn't
own) asserts no page carries "noindex" outside its own two named exemptions, and
`fixtures/sample_latest.json` (also not this task's to edit) has no `events` data, so a noindex
empty state here would fail that test on every default build. Recovering the real label (done)
already answers the review's actual concern -- an indexed placeholder for a state that isn't
expected to persist is the honest trade-off, not a guess.

«آخر فرصة» strip: steps/last_chance.py's data["last_chance"][city] -> the same site.film_tile()
core.py's own posters row uses, so a last-chance film looks and behaves exactly like any other
tile (same poster, price, verdict word, link to its film page -- these are always currently-
showing films, never coming-soon ones).
"""
from site_kit import L, NavItem, P, Page, Pages, Plugin, esc

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
             NavItem("events", href=lambda lang: P(lang, "events"), label=TITLE_EV)],
        slots={"home.after_tonight": last_chance_strip, "city.after_tonight": last_chance_strip})


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
        else:
            # honest and indexable, exactly like /arabic/'s own empty state above -- see the
            # module docstring for why this stays indexed rather than noindex.
            empty = ("ما عندنا فعاليات مؤكدة من السينمات الحين — نضيفها أول ما تعلنها سينما." if lang == "ar"
                     else "No chain-confirmed events yet — added as soon as a chain announces one.")
            body = head + f'<section class="wrap"><p class="empty">{esc(empty)}</p></section>'
        graph = [self.breadcrumb_ld(lang, (title, P(lang, "events")))]
        return {"title": title, "desc": desc, "body": body, "kind": "events", "nav": "events", "graph": graph}

# -------------------------------------------------------------- last-chance strip (slot)
# A plain fn(site, lang, **ctx) as PLUGINS.md's slot contract asks for -- NOT a Pages/HubPages
# method: the framework calls slot functions with the site itself as the first argument, so a
# bound method here would double up on that first positional argument.
def last_chance_strip(site, lang, city=None):
    last_chance = site.d.get("last_chance") or {}
    if city:
        fids = [fid for fid in last_chance.get(city, []) if fid in site.films]
    else:
        fids = list(dict.fromkeys(fid for fids in last_chance.values() for fid in fids if fid in site.films))
    if not fids:
        return ""
    heading = "آخر فرصة" if lang == "ar" else "Last chance"
    tiles = "".join(site.film_tile(fid, lang, site.shows, i=i) for i, fid in enumerate(fids[:8]))
    return (f'<section class="tonight wrap last-chance"><div class="sec-h"><h2>{esc(heading)}</h2></div>'
            f'<div class="posters">{tiles}</div></section>')
