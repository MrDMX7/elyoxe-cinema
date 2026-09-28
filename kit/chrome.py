"""The chrome: the header's tools, the phone's tab bar, the footer's links, the sheets and the pill sheets, the near
line (site_kit.Kit's chrome helpers, moved as they were by W1-P1). Owner: W1-P2, then W2-P5.

W2-P5 (MASTER-PLAN §2.0, §5.3): every sheet has a sticky head (the grabber and the title), which src/js/drag.js drags;
the filter sheet stops at 60 % and 92 % (DETENTS); «قريب مني» and «بدون بطاقة» are full-width first rows; each city
says how many cinemas it has, each card its best number; the fourth tab is «قائمتي» (owner decision D2, ME_TAB), which
opens the «قائمتي» sheet until W3-P1's /me/ page exists. A door (§1.2 #10) is any element with data-sheet-open: the
screen's own package draws it next to its first price (the billboard's is W2-P1's, the stub's W2-P3's), and
src/js/sheet.js opens its sheet by delegation, whenever it was drawn.

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)
from site_kit import ICONS

# the one new icon of the surface budget (MASTER-PLAN §1.2 #5): the bookmark, the «قائمتي» tab's (W3-P1 saves with it)
ICONS.setdefault("bookmark", '<path d="M6 3h12v18l-6-4-6 4z"/>')

# D2 (owner, 2026-09-28: yes): the fourth tab is «قائمتي», and search stays the header's icon on every page. False puts
# «بحث» back in the tab bar. Until W3-P1 builds /me/, the tab opens the «قائمتي» sheet: what this phone really keeps
# (the city, the card) and «امسح بياناتي». No list and no promise of one: nothing saves a film yet
ME_TAB = True

# the sheets that stop part-way (MASTER-PLAN §2.0): fractions of the viewport's height, lowest first. drag.js reads them
DETENTS = {"sheet-filter": "60 92"}

# W2-P5's words (the dialect gate reviews them with the rest; feedback_emirati_dialect: «تلفون» not «جوال»)
CHROME_W2 = {
    "me": ("قائمتي", "My list"),
    "me_city": ("مدينتك", "Your city"), "me_card": ("بطاقتك", "Your card"),
    "me_note": ("هذي اختياراتك، محفوظة على تلفونك بس.", "These are your choices, kept on your phone only."),
    "me_clear": ("امسح بياناتي", "Clear my data"), "me_sure": ("متأكد؟ اضغط مرة ثانية", "Sure? Tap again"),
    # a card's best number: «لين» when its offers differ from chain to chain, so the number is the most it gives
    "upto": ("لين {n}", "up to {n}"), "bogo": ("1+1", "1+1"), "fixed": ("{n} درهم", "AED {n}"),
}


class ChromeKit:
    # -------- page plumbing
    def card_best(self, cid, lang):
        """A card's best number in the card sheet (§2.0, «فزعة 20%»): its biggest current official offer, as that offer
        reads. Two tickets for one count as half off each, so «1+1» beats a smaller percentage; «لين 25%» when the card's
        offers differ between chains (Fazaa: 20 % at four, 25 % at Reel). Empty when nothing current is known."""
        offs = [r for cs in self.rules.values() for k, r in (cs or {}).items()
                if k == cid and r and rule_state(r, self.today) == "ok"]
        if not offs: return ""
        worth = lambda r: 50.0 if r.get("type") == "bogo" else -1.0 if r.get("type") == "fixed" else float(r.get("value") or 0)
        best = max(offs, key=lambda r: (worth(r), -float(r.get("value") or 0)))
        v = f'{float(best.get("value") or 0):g}'
        if best.get("type") == "bogo": return L(CHROME_W2["bogo"], lang)
        if best.get("type") == "fixed": return L(CHROME_W2["fixed"], lang).format(n=v)
        same = len({(r.get("type"), float(r.get("value") or 0)) for r in offs}) == 1
        return f"{v}%" if same else L(CHROME_W2["upto"], lang).format(n=f"{v}%")

    def card_chips(self, lang):
        """The card sheet's choices (UI redesign Task 2): «بدون بطاقة» first as a full-width row (W2-P5), then the
        confirmed cards grouped government / banks, each with its best number in gold (a toggle button main.js drives:
        pickCard reprices and persists)."""
        gov = [c for c in self.cards if c.get("kind") == "gov"]; bank = [c for c in self.cards if c.get("kind") != "gov"]
        nm = lambda c: c["name_ar"] if lang == "ar" else c["name_en"]

        def b(cid, label, on=False, cls="opt"):
            best = self.card_best(cid, lang) if cid else ""
            # dates(): the sitewide rule (site_kit.dates, used for the cards page's own offers) isolates only the
            # percentage itself in dir="ltr", not the whole label — so «لين 25%» keeps «لين» first and reads right
            # to left; wrapping the whole string in dir=ltr (the first run's bug) printed «25% لين» instead
            n = f' <b class="best">{dates(esc(best))}</b>' if best else ""
            return (f'<button type="button" class="{cls}" data-card="{esc(cid)}" aria-pressed="{"true" if on else "false"}">'
                    f'{esc(label)}{n}</button>')
        out = f'<div class="sec">{b("", L(T["nocard"], lang), True, "opt wide")}</div>'
        for key, cs in (("gov", gov), ("bank", bank)):
            if cs:
                out += (f'<div class="sec"><h3 class="l" id="sc-{key}">{esc(L(CHROME_T[key], lang))}</h3>'
                        f'<div class="opts" role="group" aria-labelledby="sc-{key}">{"".join(b(c["id"], nm(c)) for c in cs)}</div></div>')
        return out + f'<p class="sheet-more"><a href="{P(lang, "cards")}">{esc(L(CHROME_T["all_cards"], lang))}</a></p>'

    def sheet(self, sid, title, body, lang):
        """A sheet (src/js/sheet.js): phone = bottom sheet, desktop = side panel; a modal dialog any
        <button data-sheet-open="ID"> (or a pill link carrying it) opens. Hidden until then — with no
        script it never shows, and the pill that opens it is a plain link. Its head (the grabber and the title row)
        stays at the top while the body scrolls, and is what src/js/drag.js drags; DETENTS names the sheets that stop
        part-way."""
        t = L(title, lang) if isinstance(title, tuple) else title
        dt = f' data-detents="{DETENTS[sid]}"' if sid in DETENTS else ""
        return (f'<div class="sheet" id="{sid}" role="dialog" aria-modal="true" aria-labelledby="{sid}-t"{dt} hidden>'
                f'<div class="sheet-t"><div class="grab" aria-hidden="true"></div><div class="sheet-h"><h2 id="{sid}-t">{esc(t)}</h2>'
                f'<button type="button" class="sheet-x" data-sheet-close aria-label="{esc(L(CHROME_T["close"], lang))}"></button></div></div>'
                f'<div class="sheet-b">{body}</div></div>')

    def sheet_city(self, lang, city="dubai"):
        """«قريب مني» first, as a full-width row (near.js askNear: the nearest cinema picks the city), then every city with
        how many cinemas it has («دبي 22 سينما»). Each city is a link to its page; main.js picks it in place where the
        page follows the city (data-citypick)."""
        n = {c: sum(1 for x in self.cinemas.values() if x.get("city") == c) for c, _, _ in CITIES}
        cnt = lambda k: (ar_count_num(k, CINEMAS_AR) if lang == "ar" else num(k) + (" cinema" if k == 1 else " cinemas"))
        opts = "".join(f'<a class="opt" href="{P(lang, c)}" data-city="{c}"{" aria-current=\"true\"" if c == city else ""}>{esc(L((a, e), lang))}'
                       + (f' <small class="n">{cnt(n[c])}</small>' if n[c] else "") + '</a>'
                       for c, a, e in CITIES)
        body = (f'<div class="sec"><button type="button" class="opt wide near-b" data-near>{icon("pin")}{esc(L(CHROME_T["near"], lang))}</button>'
                f'<p class="near-m" data-near-msg aria-live="polite"></p></div>'
                f'<div class="sec"><div class="opts" data-citypick>{opts}</div></div>'
                f'<p class="sheet-more"><a href="{P(lang, "cinemas")}">{esc(L(CHROME_T["all_cities"], lang))}</a></p>')
        return self.sheet("sheet-city", CHROME_T["pick_city"], body, lang)

    def sheet_card(self, lang):
        return self.sheet("sheet-card", CHROME_T["pick_card"], self.card_chips(lang), lang)

    def sheet_me(self, lang, city="dubai"):
        """«قائمتي» until W3-P1's /me/ (owner decision D2): only what this phone really keeps. The city and the card, each
        a row that opens its own sheet (the sheet covers the header's pills, so it is the screen's one door to them), a
        line saying where they are kept, and «امسح بياناتي», which asks once more before it clears every «cinema.» key
        on this phone, the location too (src/js/chrome.js). No list, and no promise of one."""
        k = lambda key: esc(L(CHROME_W2[key], lang))
        body = (f'<div class="sec me-rows">'
                f'<button type="button" class="opt wide dr" data-sheet-open="sheet-city"><span>{k("me_city")}</span> '
                f'<b data-city-name>{esc(L(CITY.get(city, CITY["dubai"]), lang))}</b></button>'
                f'<button type="button" class="opt wide dr" data-sheet-open="sheet-card"><span>{k("me_card")}</span> '
                f'<b data-me-card>{esc(L(T["nocard"], lang))}</b></button></div>'
                f'<p class="me-n">{k("me_note")}</p>'
                f'<button type="button" class="btn ghost me-clear" data-me-clear data-t="{k("me_clear")}" data-sure="{k("me_sure")}">{k("me_clear")}</button>')
        return self.sheet("sheet-me", CHROME_W2["me"], body, lang)

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
        the sheets the pills and the «قائمتي» tab open. No script: the pills are links (the cinemas index, the cards
        page) and the «قائمتي» tab is not drawn (what it shows lives in the phone's storage, which only the script reads)."""
        city = page_city or "dubai"
        # the wordmark is «سينما» in both languages (owner default D7, MASTER-PLAN §1.4): on /en/ an Arabic logotype read
        # out as «Cinema»; og:site_name and the JSON-LD keep each language's own name (UI s_mark)
        vals["mark"] = esc(UI["s_mark"][0])
        vals["mark_attrs"] = f' lang="ar" aria-label="{esc(UI["s_mark"][1])}"' if lang == "en" else ""
        vals["city_name"] = esc(L(CITY[city], lang))
        vals["card_name"] = esc(L(CHROME_T["mycard"], lang))
        vals["cinemas_page"], vals["icon_search"] = P(lang, "cinemas"), icon("search")
        # the sheets' drag (src/js/drag.js): chrome.js fetches it when the page is idle, or at the first sheet
        vals["drag_js"] = (self.chunk_urls or {}).get("drag", "")
        cur = lambda on: ' aria-current="page"' if on else ""
        # the fourth tab: «قائمتي» (D2), the «قائمتي» sheet's opener (sheet.js makes it a button); with no script it is not
        # drawn, and a tap before the script has bound it stays on the page (#me names nothing). Else «بحث», which with
        # no script is «كل الأفلام» on the home page and with it the search overlay (src/js/search.js)
        fourth = (("#me", "bookmark", esc(L(CHROME_W2["me"], lang)), "", ' class="js-only" data-sheet-open="sheet-me" data-me-tab')
                  if ME_TAB else (P(lang) + "#all", "search", vals["s_search"], "", ' data-search aria-haspopup="dialog"'))
        tabs = [(vals["hub"], "home", vals["s_films"], cur(pagekind == "home"), ""),
                (vals["cinemas_page"], "pin", vals["s_cinemas"], cur(nav == "cinemas"), ""),
                (vals["thursday_href"], "cal", vals["s_thursday"], cur(nav == "thursday"), ""),
                fourth]
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
        vals["sheets"] = self.sheet_city(lang, city) + self.sheet_card(lang) + (self.sheet_me(lang, city) if ME_TAB else "")
