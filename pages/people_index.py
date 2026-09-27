"""/people/ + /en/people/ (phase 3, batch A, task A5): every person with a real page, showing-now people
first, then alphabetically (a name's own script already sorts ا-ي / A-Z by codepoint once case-folded).
Reuses pages/people.py's `People` — the same filter that decides who gets a page (a name and >= 1 film we
list) — so this index can never link somewhere pages/people.py itself would not build. Not a second data
source: it renders what steps/people.py already put in data["people"]; pages/search.py's index also reads
that same filtered set, independently, for the client search box.

Fix round 1 (task-A5-review.md): a real refresh can carry 100+ people (steps/people.py has no cap on how
many distinct cast/director qids a season of films can name). A flat photo grid for all of them would blow
the ~125 KB page target long before 300 rows, so this page uses `site.fit()` (site_kit.py — the same
budget-fit mechanism core.py's schedules use) between two render modes: "full" (photo or placeholder, per
pages/people.py's own row markup) and, only if that does not fit, "compact" (name only, no image markup at
all — not merely a lazily-loaded image, since the <img>/srcset text itself is most of the byte cost)."""
from site_kit import CHROME, L, P, PAGE_TARGET, Page, Pages, Plugin, esc
from pages.people import People

TITLE = ("الناس", "People")
CSS = ("people_index",)


class PeopleIndex(Pages):
    def __init__(self, site):
        super().__init__(site)
        self.ppl = People(site)

    def showing_now(self, q):
        fids = self.ppl.films_of.get(q) or {}
        return any(self.films[f].get("status") != "archived" for f in fids)

    def row(self, q, lang, mode):
        if mode == "compact":
            return f'<li><a href="{self.ppl.href(q, lang)}"{self.ppl.name_attr(q, lang)}>{esc(self.ppl.name(q, lang))}</a></li>'
        ph = self.ppl.photo(q)
        img = (f'<img src="{esc(ph["src"])}" srcset="{esc(ph["src"])} 160w, {esc(ph["src2x"])} 320w" sizes="64px"'
               f' width="64" height="80" alt="" loading="lazy" decoding="async">' if ph
               else '<span class="pi-i" aria-hidden="true"></span>')
        return (f'<li><a href="{self.ppl.href(q, lang)}">{img}'
                f'<span{self.ppl.name_attr(q, lang)}>{esc(self.ppl.name(q, lang))}</span></a></li>')

    def section(self, h2, qs, lang, mode):
        cls = "pi-l" if mode == "full" else "pi-l pi-c"
        return f'<section class="wrap pi"><h2>{esc(h2)}</h2><ul class="{cls}">{"".join(self.row(q, lang, mode) for q in qs)}</ul></section>'

    def page(self, lang):
        ar = lang == "ar"
        title = L(TITLE, lang)
        desc = ("كل من نعرض له فيلماً في سينمات الإمارات، الحين أو قبل — الطاقم والمخرجين." if ar
                else "Everyone with a film showing now or shown before in UAE cinemas — cast and directors.")
        head = (f'<section class="head wrap">{self.crumbs(lang, (title, None))}<h1 class="pt">{esc(title)}</h1>'
                f'<p class="lead">{esc(desc)}</p></section>')
        qs = sorted(self.ppl.p, key=lambda q: self.ppl.name(q, lang).casefold())
        now_qs = [q for q in qs if self.showing_now(q)]
        rest_qs = [q for q in qs if not self.showing_now(q)]
        graph = [self.breadcrumb_ld(lang, (title, P(lang, "people")))]

        def render(mode):
            body = head
            if now_qs:
                h2 = "يعرض لهم الحين" if ar else "Showing now"
                body += self.section(h2, now_qs, lang, mode)
            if rest_qs:
                h2 = "الكل" if ar else "Everyone"
                body += self.section(h2, rest_qs, lang, mode)
            if not now_qs and not rest_qs:
                empty = "ما عندنا صفحات أشخاص بعد." if ar else "No people pages yet."
                body += f'<section class="wrap"><p class="empty">{esc(empty)}</p></section>'
            return body

        left = PAGE_TARGET - CHROME - len(head.encode()) - self.ld_size(graph) - 200
        body, _ = self.fit(render, ("full", "compact"), left)
        return {"title": title, "desc": desc, "body": body, "kind": "people", "nav": "films", "graph": graph}


def register(site):
    idx = PeopleIndex(site)
    if not idx.ppl.p:
        return Plugin()
    return Plugin(pages=[Page(("people",), lang, (lambda lang=lang: idx.page(lang))) for lang in ("ar", "en")])
