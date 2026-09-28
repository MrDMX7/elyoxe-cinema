"""The chrome: the header's tools, the phone's tab bar, the footer's links, the sheets and the two pill sheets,
the near line (site_kit.Kit's chrome helpers, moved as they were by W1-P1). Owner: W1-P2, then W2-P5.

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)


class ChromeKit:
    # -------- page plumbing
    def card_chips(self, lang):
        """The card sheet's choices (UI redesign Task 2): «بدون بطاقة», then the confirmed cards grouped
        government / banks, every one a toggle button cinema.js drives (main.js pickCard: reprice + persist).
        The bank <select> of the old control sentence is gone into this list."""
        gov = [c for c in self.cards if c.get("kind") == "gov"]; bank = [c for c in self.cards if c.get("kind") != "gov"]
        nm = lambda c: c["name_ar"] if lang == "ar" else c["name_en"]
        b = lambda cid, label, on=False: (f'<button type="button" class="opt" data-card="{esc(cid)}" aria-pressed="{"true" if on else "false"}">'
                                          f'{esc(label)}</button>')
        out = f'<div class="sec"><div class="opts">{b("", L(T["nocard"], lang), True)}</div></div>'
        for key, cs in (("gov", gov), ("bank", bank)):
            if cs:
                out += (f'<div class="sec"><h3 class="l" id="sc-{key}">{esc(L(CHROME_T[key], lang))}</h3>'
                        f'<div class="opts" role="group" aria-labelledby="sc-{key}">{"".join(b(c["id"], nm(c)) for c in cs)}</div></div>')
        return out + f'<p class="sheet-more"><a href="{P(lang, "cards")}">{esc(L(CHROME_T["all_cards"], lang))}</a></p>'

    def sheet(self, sid, title, body, lang):
        """A sheet (src/js/sheet.js): phone = bottom sheet, desktop = side panel; a modal dialog any
        <button data-sheet-open="ID"> (or a pill link carrying it) opens. Hidden until then — with no
        script it never shows, and the pill that opens it is a plain link."""
        t = L(title, lang) if isinstance(title, tuple) else title
        return (f'<div class="sheet" id="{sid}" role="dialog" aria-modal="true" aria-labelledby="{sid}-t" hidden>'
                f'<div class="grab" aria-hidden="true"></div><div class="sheet-h"><h2 id="{sid}-t">{esc(t)}</h2>'
                f'<button type="button" class="sheet-x" data-sheet-close aria-label="{esc(L(CHROME_T["close"], lang))}"></button></div>'
                f'<div class="sheet-b">{body}</div></div>')

    def sheet_city(self, lang, city="dubai"):
        """Every city, and «قريب مني» (near.js askNear: the nearest cinema picks the city). Each city is a link
        to its page; main.js picks it in place where the page follows the city (data-citypick)."""
        opts = "".join(f'<a class="opt" href="{P(lang, c)}" data-city="{c}"{" aria-current=\"true\"" if c == city else ""}>{esc(L((a, e), lang))}</a>'
                       for c, a, e in CITIES)
        body = (f'<div class="sec"><div class="opts" data-citypick>{opts}</div></div>'
                f'<div class="sec"><button type="button" class="opt near-b" data-near>{icon("pin")}{esc(L(CHROME_T["near"], lang))}</button>'
                f'<p class="near-m" data-near-msg aria-live="polite"></p></div>'
                f'<p class="sheet-more"><a href="{P(lang, "cinemas")}">{esc(L(CHROME_T["all_cities"], lang))}</a></p>')
        return self.sheet("sheet-city", CHROME_T["pick_city"], body, lang)

    def sheet_card(self, lang):
        return self.sheet("sheet-card", CHROME_T["pick_card"], self.card_chips(lang), lang)

    def me(self, lang, city=None, mode="home"):
        """What is left of the control sentence «أنا في [المدينة] وعندي [البطاقة]» once the header's pills took
        the city and the card (UI redesign Task 2): the line where «قريب مني» and the network's city say what
        they did, and on home and city pages the «الحين» slot. The page bodies' calls go in Tasks 3–5."""
        now = ""
        if mode in ("home", "city"):
            now = (f'<a class="now" href="#all" data-now data-hold hidden><span class="now-tx"><span class="now-l">{esc(L(T["now_label"], lang))}</span>'
                   f'<span class="now-f" data-now-film></span><span class="now-w" data-now-where></span></span>'
                   f'<span class="flip" dir="ltr" data-now-time></span></a>')
        return f'<div class="me me-{mode}" data-me><p class="near-m" data-near-msg aria-live="polite"></p>{now}</div>'

    NAV = {"films": "hub", "cinemas": "cinemas_href", "thursday": "thursday_href", "cards": "cards_href"}
    # the footer's own order (the spec's): these feature keys come first, right after «من وين الأسعار»
    FOOT_FIRST = ("q", "people")

    def nav_links(self, vals, lang, nav):
        """The modules' NavItems: a built-in key re-points that header link (and the tab bar's); any other key
        is a link in the footer's row (the header keeps its four). Returns [(key, html)] for the footer."""
        extra = []
        for it in self.nav_items:
            href = it.href(lang) if callable(it.href) else it.href
            cur = ' aria-current="page"' if nav == it.key else ""
            if it.key in self.NAV:
                if href: vals[self.NAV[it.key]] = esc(href)
                if it.label: vals["s_" + it.key] = esc(L(it.label, lang))
                vals["c_" + it.key] = cur
            else:
                extra.append((it.key, f'<a href="{esc(href)}"{cur}>{esc(L(it.label or (it.key, it.key), lang))}</a>'))
        return extra

    def chrome(self, vals, lang, nav, pagekind, page_city, extra):
        """The header's tools (search, the city and card pills), the phone's tab bar, the footer's links and
        the two sheets the pills open. No script: the pills are links (the cinemas index, the cards page)."""
        city = page_city or "dubai"
        # the wordmark is «سينما» in both languages (owner default D7, MASTER-PLAN §1.4): on /en/ an Arabic logotype read
        # out as «Cinema»; og:site_name and the JSON-LD keep each language's own name (UI s_mark)
        vals["mark"] = esc(UI["s_mark"][0])
        vals["mark_attrs"] = f' lang="ar" aria-label="{esc(UI["s_mark"][1])}"' if lang == "en" else ""
        vals["city_name"] = esc(L(CITY[city], lang))
        vals["card_name"] = esc(L(CHROME_T["mycard"], lang))
        vals["cinemas_page"], vals["icon_search"] = P(lang, "cinemas"), icon("search")
        cur = lambda on: ' aria-current="page"' if on else ""
        tabs = [(vals["hub"], "home", vals["s_films"], cur(pagekind == "home"), ""),
                (vals["cinemas_page"], "pin", vals["s_cinemas"], cur(nav == "cinemas"), ""),
                (vals["thursday_href"], "cal", vals["s_thursday"], cur(nav == "thursday"), ""),
                # no script: «كل الأفلام» on the home page; with it, the search overlay (src/js/search.js)
                (P(lang) + "#all", "search", vals["s_search"], "", ' data-search aria-haspopup="dialog"')]
        vals["tabs"] = "".join(f'<a href="{h}"{c}{x}>{icon(i)}<span>{t}</span></a>' for h, i, t, c, x in tabs)
        first = [h for k in self.FOOT_FIRST for kk, h in extra if kk == k]
        rest = [h for k, h in extra if k not in self.FOOT_FIRST]
        links = [f'<a href="{vals["cinemas_page"]}"{cur(nav == "cinemas" and pagekind == "cinemas")}>{vals["s_cinemas"]}</a>',
                 f'<a href="{P(lang, "cards")}"{cur(nav == "cards")}>{esc(L(UI["s_cards_f"], lang))}</a>',
                 f'<a href="{P(lang, "sources")}"{cur(pagekind == "sources")}>{esc(L(UI["s_sources"], lang))}</a>',
                 *first, *rest,
                 f'<a href="{vals["halls_href"]}"{cur(pagekind == "halls")}>{vals["s_halls"]}</a>',
                 f'<a href="{vals["alt"]}" hreflang="{vals["alt_lang"]}" lang="{vals["alt_lang"]}">{vals["s_alt"]}</a>']
        vals["foot_links"] = "\n    ".join(links)
        vals["sheets"] = self.sheet_city(lang, city) + self.sheet_card(lang)
