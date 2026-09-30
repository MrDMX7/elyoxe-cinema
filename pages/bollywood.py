"""«بوليوود وجنوب الهند» (r3-home, owner idea 2026-09-30): /bollywood/ + /en/bollywood/, a hub for Hindi, Malayalam,
Tamil and Telugu films (film["lang"], the same field pages/hubs.py's /arabic/ already reads) with a language tab
per section. Linked from the home row's «الكل» and the footer (its NavItem)."""
from site_kit import L, NavItem, P, Page, Pages, Plugin, esc

TITLE = ("بوليوود وجنوب الهند", "Bollywood and South India")
CSS = ("hubs",)
DIRS = ("bollywood",)

# a film's lang field, as seen in the data (English words, sometimes ISO codes): canonical key -> (label, match set)
TABS = [("hindi", ("هندي", "Hindi"), {"hindi", "hi"}),
        ("malayalam", ("مالايالام", "Malayalam"), {"malayalam", "ml"}),
        ("tamil", ("تاميلي", "Tamil"), {"tamil", "ta"}),
        ("telugu", ("تيلوغو", "Telugu"), {"telugu", "te"})]
LANG_KEYS = {k for _, _, ks in TABS for k in ks}


def _tab_of(lang_field):
    v = str(lang_field or "").lower()
    for key, _, ks in TABS:
        if v in ks: return key
    return None


def register(site):
    p = BollywoodPages(site)
    if not any(p.films_by_tab().values()):     # films_by_tab() always has all 4 keys; check their lists, not the dict
        return Plugin()
    return Plugin(pages=[Page(("bollywood",), lang, lambda lang=lang: p.page(lang)) for lang in ("ar", "en")],
                  nav=[NavItem("bollywood", href=lambda lang: P(lang, "bollywood"), label=TITLE)])


class BollywoodPages(Pages):
    def films_by_tab(self):
        out = {k: [] for k, _, _ in TABS}
        for fid in self.showing:
            t = _tab_of(self.films[fid].get("lang"))
            if t: out[t].append(fid)
        for k in out: out[k].sort(key=lambda f: (-self.today_count.get(f, 0), f))
        return out

    def page(self, lang):
        by = self.films_by_tab()
        title = L(TITLE, lang)
        desc = ("أفلام هندية وجنوب هندية تُعرض الحين في سينمات الإمارات، مبوّبة باللغة." if lang == "ar"
                else "Hindi and South Indian films showing now in UAE cinemas, by language.")
        present = [(k, t, by[k]) for k, t, _ in TABS if by[k]]
        tabs_nav = "".join(f'<a href="#bw-{k}">{esc(L(t, lang))} <span class="num">{len(fids)}</span></a>' for k, t, fids in present)
        head = (f'<section class="head wrap">{self.crumbs(lang, (title, None))}<h1 class="pt">{esc(title)}</h1>'
                f'<p class="lead">{esc(desc)}</p>' + (f'<nav class="bw-tabs" aria-label="{esc(title)}">{tabs_nav}</nav>' if len(present) > 1 else "") + '</section>')
        if present:
            sections = []
            for k, t, fids in present:
                tiles = "".join(self.film_tile(fid, lang, self.shows, i=i) for i, fid in enumerate(fids))
                sections.append(f'<section class="wrap" id="bw-{k}"><h2>{esc(L(t, lang))}</h2><div class="posters">{tiles}</div></section>')
            body = head + "".join(sections)
        else:
            empty = "ما في فيلم هندي أو جنوب هندي معروض الحين." if lang == "ar" else "No Hindi or South Indian film showing right now."
            body = head + f'<section class="wrap"><p class="empty">{esc(empty)}</p></section>'
        graph = [self.breadcrumb_ld(lang, (title, P(lang, "bollywood")))]
        return {"title": title, "desc": desc, "body": body, "kind": "bollywood", "nav": "bollywood", "graph": graph}
