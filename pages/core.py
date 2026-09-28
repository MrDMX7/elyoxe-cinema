"""The core pages: home, city, cinema, film (showing and archived), cards (each card, the matrix, the stubs of
unconfirmed cards), old film ids, halls, /cinemas/, /sources/, 404, offline, and the /data slices cinema.js reads.
Always the first module (build.py loads core, then pages/*.py alphabetically).

Since W1-P1 (MASTER-PLAN §5.2) the page families live in pages/_core/ as mixins of CorePages, one Wave 2 owner
each (§6.2): home.py, bill.py (the billboard), film.py, places.py (city, cinema, /cinemas/), money.py (cards,
halls, /sources/), edge.py (404, offline). This file keeps the registration, the client's module lists, the
/data slices and the old film ids' redirects.

The methods are the old Site methods: `self` is a Pages, which reads everything else (self.page,
self.poster, self.shows ...) through to the site. Features hook into these pages only at Kit.SLOTS."""
from site_kit import *  # noqa: F401,F403  (the names these pages were written against)
from site_kit import Emit, Pages, Plugin
from pages._core.bill import BillPages
from pages._core.edge import EdgePages
from pages._core.film import FilmPages
from pages._core.home import HomePages
from pages._core.money import MoneyPages
from pages._core.places import TOMORROW_AT_CINEMA, PlacesPages  # noqa: F401  (pages.core.TOMORROW_AT_CINEMA stays importable)

# the client: small modules under src/js/, concatenated in this order into ONE function scope (so they share
# helpers without globals), comments and indentation stripped. pure.js and disc.js are plain function
# declarations with no page access: tests/test_js.py and tests/test_parity.py run them in node as they are.
# main.js (start-up) stays last: a feature's main-bundle modules go in just before it (build.js_files).
# chrome.js (W2-P5) and places.js (W2-P6) are empty until Wave 2 fills them: declared here so no Wave 2 package edits
# this file or build.py to get its module into the bundle (W1-P1)
JS = ("core", "pure", "disc", "flip", "prices", "near", "prayer", "home", "filters", "bill", "ticket", "film", "tabs", "trailer", "pwa", "sheet",
      "chrome", "places", "main")
# the shared stylesheet: src/cinema.css (tokens and base), then these partials in this order (W1-P1 split the rest of
# cinema.css by owner, MASTER-PLAN §6.2), then every feature's src/css/<name>.css in module order
CSS = ("ui-paper", "ui-chrome", "ui-tabs", "ui-sheet", "ui-near", "ui-bill", "ui-fhero", "ui-lights", "ui-rows", "ui-tile", "ui-grid",
       "ui-film", "ui-sched", "ui-dock", "ui-ticket", "ui-places", "ui-money")
# page-scoped: a second small stylesheet on that page kind only (build.page_css_files); the 404's leader is W2-P10's
PAGE_CSS = {"404": ("ui-edge",)}
# drag.js: the sheets' drag (W2-P5), loaded on idle by the page that asks for it; empty until then
LAZY_JS = ("drag",)
DIRS = tuple(c for c, _, _ in CITIES) + ("film", "cards", "halls", "data", "assets", "en", "cinema", "cinemas", "sources")


def register(site):
    c = CorePages(site)
    return Plugin(pages=[Emit(c.home), Emit(c.city_pages), Emit(c.cinema_pages), Emit(c.film_pages), Emit(c.card_pages),
                         Emit(c.card_stubs), Emit(c.redirect_pages), Emit(c.halls_page), Emit(c.cinemas_page), Emit(c.sources_page),
                         Emit(c.not_found), Emit(c.offline),
                         Emit(c.slices)])


class CorePages(HomePages, BillPages, FilmPages, PlacesPages, MoneyPages, EdgePages, Pages):
    # the page families live in pages/_core/ (one Wave 2 owner each, MASTER-PLAN §6.2); what stays here is the
    # module's registration, the /data slices every page's script reads, and the old film ids' redirects
    # -------------------------------------------------- old URLs that must not 404
    def redirect_pages(self):
        """An old fid (the film's canonical id changed, final review I1) answers with a small page that sends
        the reader on at once: meta refresh + canonical to the film's page + noindex. Never in the sitemap."""
        for old, new in sorted(self.redirects.items()):
            for lang in ("ar", "en"):
                href = P(lang, "film", new); t = self.ftitle(new, lang)
                robots = NOINDEX if self.noindex else '<meta name="robots" content="noindex">'
                page = (f'<!doctype html>\n<html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8">'
                        f'<title>{esc(t)}</title>{robots}'
                        f'<link rel="canonical" href="{SITE + href}"><meta http-equiv="refresh" content="0; url={href}">'
                        f'<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
                        f'<body><p><a href="{href}">{esc(t)}</a></p></body></html>\n')
                self.write(os.path.join(self.out, *(["en"] if lang == "en" else []), "film", old, "index.html"), page)

    # -------------------------------------------------- data for cinema.js
    def slices(self):
        """/data/<city>-<date>.json per city and day, holding only what cinema.js reads, as indexed arrays:
        C[[cid, chain, ar, en]] F[[fid, ar, en]] H[[hall code, key, ar, en]] P[[[seat, aed]…]] B[booking URL prefixes]
        S[[cinema i, film i, "HH:MM", hall i, price i|-1, prefix i|-1, url tail(, table date)]] — the 8th
        element is present only when the price came from prices.yaml, and is that entry's date.
        Aligned with S when any is known: E[minutes from start to the approximate end, 0 = unknown] and
        Li[index into L[[lang, subs]] or -1]."""
        ddir = os.path.join(self.out, "data")
        for city, _, _ in CITIES:
            cids = {cid for cid, c in self.cinemas.items() if c.get("city") == city}
            for day in sorted({s["date"] for s in self.shows if s["cinema"] in cids}):
                ss = sorted((s for s in self.shows if s["cinema"] in cids and s["date"] == day), key=lambda s: s["time"])
                lists = {"C": [], "F": [], "H": [], "P": [], "B": [], "L": []}
                idx = {k: {} for k in lists}

                def at(kind, key, row):
                    if key not in idx[kind]: idx[kind][key] = len(lists[kind]); lists[kind].append(row)
                    return idx[kind][key]
                S, E, Li = [], [], []
                for s in ss:
                    cid, fid, chain = s["cinema"], s["film"], self.cinemas[s["cinema"]]["chain"]
                    code = s.get("hall") or "OTHER"
                    ci = at("C", cid, [cid, chain, self.cname(cid, "ar"), self.cname(cid, "en")])
                    fi = at("F", fid, [fid, self.ftitle(fid, "ar"), self.ftitle(fid, "en")])
                    hk = self.hkey(s)
                    hi = at("H", (chain, hk, code), [code, chain + "|" + hk, self.hname(s, "ar"), self.hname(s, "en")])
                    pr = [[p["seat"], p["aed"]] for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
                    pi = at("P", json.dumps(pr), pr) if pr else -1
                    bi, tail = -1, ""
                    if s.get("book"):
                        pre, _, tail = s["book"].rpartition("/")
                        bi = at("B", pre + "/", pre + "/") if pre else -1
                        if not pre: tail = s["book"]
                    row = [ci, fi, s["time"], hi, pi, bi, tail]
                    if pr and self.table_date(s): row.append(self.table_date(s))  # a table price carries its date
                    E.append(self.end_offset(s))
                    Li.append(at("L", (s.get("lang"), s.get("subs")), [s.get("lang"), s.get("subs")]) if s.get("lang") or s.get("subs") else -1)
                    S.append(row)
                j = {"g": self.d.get("generated"), **{k: v for k, v in lists.items() if k != "L"}, "S": S}
                if any(E): j["E"] = E
                if lists["L"]: j["L"], j["Li"] = lists["L"], Li
                self.write(os.path.join(ddir, f"{city}-{day}.json"), json.dumps(j, ensure_ascii=False, separators=(",", ":")))
        # «أقرب سينما لي» and the ticket's directions: every cinema's city and coordinates, {cid: [city, chain, lat, lng, ar, en]}
        geo = {cid: [c.get("city"), c["chain"], round(float(c["lat"]), 5), round(float(c["lng"]), 5), self.cname(cid, "ar"), self.cname(cid, "en")]
               for cid, c in self.cinemas.items() if c.get("lat") is not None and c.get("lng") is not None}
        self.write(os.path.join(ddir, "cinemas.json"), json.dumps(geo, ensure_ascii=False, separators=(",", ":")))
        rules = {ch: {card: {k: v for k, v in r.items() if k in ("status", "type", "value", "excluded_halls", "halls_excluded", "included_halls", "included_cinemas", "valid_until", "confidence", "box_office_only", "max_tickets", "note_ar")}
                      for card, r in (cards or {}).items()} for ch, cards in self.rules.items()}
        chains = {ch: self.h.chain_name(ch, "ar") for ch in sorted(set(self.rules) | {c["chain"] for c in self.cinemas.values()})}
        chains_en = {ch: self.h.chain_name(ch, "en") for ch in chains}
        self.write(os.path.join(ddir, "discounts.json"), json.dumps({"cards": self.cards, "rules": rules, "chains": {"ar": chains, "en": chains_en}},
                                                                    ensure_ascii=False, separators=(",", ":"), default=str))
