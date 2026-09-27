"""/people/ + /en/people/ (phase 3, batch A, task A5): every person with a real page, showing-now people
first, then alphabetically (a name's own script already sorts ا-ي / A-Z by codepoint once case-folded).
Reuses pages/people.py's `People` — the same filter that decides who gets a page (a name and >= 1 film we
list) — so this index can never link somewhere pages/people.py itself would not build. Not a second data
source: it renders what steps/people.py already put in data["people"]; pages/search.py's index also reads
that same filtered set, independently, for the client search box."""
from site_kit import L, P, Page, Pages, Plugin, esc
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

    def row(self, q, lang):
        ph = self.ppl.photo(q)
        img = (f'<img src="{esc(ph["src"])}" srcset="{esc(ph["src"])} 160w, {esc(ph["src2x"])} 320w" sizes="64px"'
               f' width="64" height="80" alt="" loading="lazy" decoding="async">' if ph
               else '<span class="pi-i" aria-hidden="true"></span>')
        return (f'<li><a href="{self.ppl.href(q, lang)}">{img}'
                f'<span{self.ppl.name_attr(q, lang)}>{esc(self.ppl.name(q, lang))}</span></a></li>')

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
        body = head
        if now_qs:
            h2 = "يعرض لهم الحين" if ar else "Showing now"
            body += (f'<section class="wrap pi"><h2>{esc(h2)}</h2>'
                     f'<ul class="pi-l">{"".join(self.row(q, lang) for q in now_qs)}</ul></section>')
        if rest_qs:
            h2 = "الكل" if ar else "Everyone"
            body += (f'<section class="wrap pi"><h2>{esc(h2)}</h2>'
                     f'<ul class="pi-l">{"".join(self.row(q, lang) for q in rest_qs)}</ul></section>')
        if not now_qs and not rest_qs:
            empty = "ما عندنا صفحات أشخاص بعد." if ar else "No people pages yet."
            body += f'<section class="wrap"><p class="empty">{esc(empty)}</p></section>'
        graph = [self.breadcrumb_ld(lang, (title, P(lang, "people")))]
        return {"title": title, "desc": desc, "body": body, "kind": "people", "nav": "films", "graph": graph}


def register(site):
    idx = PeopleIndex(site)
    if not idx.ppl.p:
        return Plugin()
    return Plugin(pages=[Page(("people",), lang, (lambda lang=lang: idx.page(lang))) for lang in ("ar", "en")])
