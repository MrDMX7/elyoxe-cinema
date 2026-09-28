"""Home: the page itself and its poster rows (pages/core.py's home family, moved as it was by W1-P1).
Owner in Wave 2: W2-P4 (rows and grid); W3-P1 and W4-P2 add their slot lines only (MASTER-PLAN §6.2).

Methods of pages.core.CorePages: `self` is a Pages, which reads everything else (self.page, self.poster,
self.shows ...) through to the site."""
from site_kit import *  # noqa: F401,F403  (the names these pages were written against)


class HomePages:
    # ================================================================ pages
    def home(self):
        """The home page (UI redesign Task 3, docs/superpowers/specs/2026-09-27-ui-redesign-design.md «Home»): the
        billboard (the default city's most-shown film over a frame of its trailer, then its top 5 in turn), «يبدأ
        قريب منك» (drawn by cinema.js from the city's slice), the rows, the feature slot, then «كل الأفلام» with
        the filter sheet. The cities grid, the cards list and the chains' freshness live in the header's sheets,
        /cinemas/, /cards/ and /sources/ now."""
        films = sorted(self.showing, key=lambda fid: (-self.today_count.get(fid, 0), fid))
        today = [s for s in self.shows if s["date"] == self.today]
        tops = {}
        for c, _, _ in CITIES:
            cnt = {}
            for s in today:
                if self.cinemas[s["cinema"]].get("city") == c: cnt[s["film"]] = cnt.get(s["film"], 0) + 1
            tops[c] = self.bill_pick(sorted(cnt, key=lambda f: (-cnt[f], f)))
        tops["*"] = self.bill_pick(films)   # a city with nothing tonight: the country's
        for lang in ("ar", "en"):
            self.site._first_poster = {}   # no tile claims the page's image priority: the billboard's frame is the LCP
            body = self.billboard(lang, tops, today) if films else ""
            body += (f'<h1 class="vh">{"كل سينما في الإمارات، والسعر بعد خصم بطاقتك" if lang == "ar" else "Every cinema in the UAE, priced after your card discount"}</h1>')
            # Wave 2's places on home (W1-P1): the board under the billboard, then the Thursday band (MASTER-PLAN §1.2 #2)
            body += self.slot("home.after_bill", lang) + self.slot("home.after_board", lang)
            body += self.rail(lang, "near", L(HOME_T["near"], lang), "",
                              sub=f'<span data-near-sub></span><button type="button" class="lnk near-ask" data-near hidden>{esc(L(CHROME_T["near"], lang))}</button>',
                              # id="now": the manifest's «الحين» shortcut opens /#now here (W0-P1, plan §4.1 #5; the row's slot
                              # is reserved while hidden). At cutover the board carries the id (W2-P2)
                              attrs=' id="now" data-near-row data-hold hidden')
            body += self.home_rows(lang, films)
            body += self.slot("home.after_tonight", lang)
            # a film in its last days is tagged in the grid too (the «آخر فرصة» row needs 4 films to be drawn)
            # (off with steps/last_chance.py until the signal is real: W0-P2, plan §4.1 #13 and §4.2 #23)
            last = {f: L(HOME_T["tag_last"], lang) for fs in self.last_chance().values() for f in fs}
            body += self.posters_row(lang, films, self.shows, L(HOME_T["all_films"], lang), tags=last, prayer=True, yes=True)
            hn = self.first_city_show(self.shows, ["dubai"])
            body += self.ticket(hn, lang, hidden=True) if hn else self.ticket_shell()
            title = ("سينما الإمارات اليوم — الأفلام والأسعار وخصم فزعة وإسعاد" if lang == "ar"
                     else "UAE cinemas today — films, ticket prices and card discounts")
            desc = ("مواعيد أفلام اليوم في كل سينمات الإمارات، سعر التذكرة لكل قاعة وفئة، والسعر بعد خصم فزعة وإسعاد وعروض البنوك، وهل الفيلم يستاهل."
                    if lang == "ar" else "Today’s showtimes at every UAE cinema, the ticket price per hall and seat class, the price after Fazaa, Esaad and bank offers, and whether the film is worth it.")
            graph = [{"@type": "WebSite", "name": L(UI["s_mark"], lang), "url": SITE + P(lang), "inLanguage": lang},
                     {"@type": "ItemList", "name": "Films", "itemListElement": [
                         # the 20 most shown: the list of every film cost ~9 KB of a 150 KB page (fix round 1, I3)
                         {"@type": "ListItem", "position": i + 1, "url": SITE + P(lang, "film", fid), "name": self.ftitle(fid, lang)} for i, fid in enumerate(films[:20])]},
                     self.breadcrumb_ld(lang)]
            self.page(lang, (), title, desc, body, graph, "home")

    # -------------------------------------------------- home: the rows
    def last_chance(self):
        """data["last_chance"] while steps/last_chance.py is switched on, else nothing (W0-P2, plan §4.1 #13; the
        row and the «آخر أسبوع» tags stay off until the signal is real, §4.2 #23): a latest.json written before the
        switch, or by hand, never brings them back."""
        from steps.last_chance import ENABLED
        return (self.d.get("last_chance") or {}) if ENABLED else {}

    def home_rows(self, lang, films):
        """The rows, in the spec's order, each from the data the site already keeps: tonight's show counts, the
        verdicts, the cheapest ticket, the family flag, «نازل الخميس» (data["coming"], pages/coming.py's fold),
        «آخر فرصة» (data["last_chance"], steps/last_chance.py) and Arabic (pages/hubs.py's rule: the film's own
        `lang`). A row with fewer than 4 films is not drawn. «الكل» goes to the feature's page, or to «كل الأفلام»
        with the matching sort or filter chosen (?sort= / ?f= / ?fl=, read by src/js/filters.js)."""
        N = 10
        home = P(lang)
        keys = {it.key for it in self.nav_items}
        tile = lambda fid, tag=None: self.film_tile(fid, lang, self.shows, row=True, live=True, tag=tag)
        out = []

        def row(key, title, fids, more=None, sub="", tag=None, attrs=""):
            if len(fids) >= 4:
                out.append(self.rail(lang, key, L(title, lang), "".join(tile(f, tag) for f in fids[:N]), sub=sub, more=more, attrs=attrs))

        # «الأكثر عرضاً الليلة»: by tonight's shows (cinema.js re-sorts it by the visitor's city)
        row("top", HOME_T["top"], films, home + "#all", attrs=' data-rail-sort="count"')
        row("yes", HOME_T["yes"], [f for f in films if (self.films[f].get("verdict") or {}).get("verdict") == "yes"],
            home + "?f=yes#all", sub=esc(L(HOME_T["yes_sub"], lang)))
        # «أرخص لك الليلة»: the cheapest ticket before any card here; after the visitor's card and in their city there
        priced = [(self.min_price([s for s in self._by_film.get(f, []) if s["date"] == self.today]), f) for f in films]
        cheap = [f for b, f in sorted(((b, f) for b, f in priced if b), key=lambda x: (x[0][0], x[1]))]
        row("cheap", HOME_T["cheap"], cheap, home + "?sort=price#all", sub='<span data-card-sub></span>', attrs=' data-rail-sort="pay"')
        row("family", HOME_T["family"], [f for f in films if film_flags(self.films[f])[0]], home + "?f=family#all")
        coming = self.d.get("coming") or {}
        if coming and "thursday" in keys:
            from pages.coming import fold_near_duplicates, _thursday_of
            # «الخميس» marks the week that opens on the coming Thursday (today when it is one), filed as /coming/
            # files it: _thursday_of puts Mon–Wed under the Thursday after and Fri–Sun under the one before (W0-P2,
            # plan §4.1 #11), so on a Friday it names the week already open, not the one this row announces
            from datetime import date, timedelta
            t0 = date.fromisoformat(self.today)
            thu = (t0 + timedelta(days=(3 - t0.weekday()) % 7)).isoformat()
            items = sorted(fold_near_duplicates(coming), key=lambda kv: (not kv[1].get("release_date"), kv[1].get("release_date") or "", kv[1]["title"]))
            items = [(k, f) for k, f in items if not f.get("release_date") or f["release_date"] >= self.today]
            if len(items) >= 4:
                tiles = "".join(self.coming_tile(k, f, lang, L(HOME_T["tag_thu"], lang) if f.get("release_date") and _thursday_of(f["release_date"]) == thu else None)
                                for k, f in items[:N])
                out.append(self.rail(lang, "coming", L(HOME_T["coming"], lang), tiles, more=P(lang, "coming")))
        last = list(dict.fromkeys(f for fs in self.last_chance().values() for f in fs if f in self.films and f in self.showing))
        row("last", HOME_T["last"], last, tag=L(HOME_T["tag_last"], lang))
        arabic = [f for f in films if str(self.films[f].get("lang") or "").lower() in ("arabic", "ar")]
        row("arabic", HOME_T["arabic"], arabic, P(lang, "arabic") if "arabic" in keys else home + "?fl=Arabic#all")
        return "".join(out)
