"""The phase-1 page types, moved from build.py as they were: home, city, cinema, film (showing and archived),
cards (each card, the matrix, the stubs of unconfirmed cards), old film ids, halls, 404, offline, and the
/data slices cinema.js reads. Always the first module (build.py loads core, then pages/*.py alphabetically).

The methods are the old Site methods: `self` is a Pages, which reads everything else (self.page,
self.poster, self.shows ...) through to the site. Features hook into these pages only at Kit.SLOTS."""
from site_kit import *  # noqa: F401,F403  (the names these pages were written against)
from site_kit import Emit, Pages, Plugin

# the client: small modules under src/js/, concatenated in this order into ONE function scope (so they share
# helpers without globals), comments and indentation stripped. pure.js and disc.js are plain function
# declarations with no page access: tests/test_js.py and tests/test_parity.py run them in node as they are.
# main.js (start-up) stays last: a feature's main-bundle modules go in just before it (build.js_files).
JS = ("core", "pure", "disc", "flip", "prices", "near", "prayer", "home", "filters", "bill", "ticket", "film", "tabs", "trailer", "pwa", "sheet", "main")
CSS = ()            # src/cinema.css is the base sheet; features append src/css/<name>.css
LAZY_JS = ()
DIRS = tuple(c for c, _, _ in CITIES) + ("film", "cards", "halls", "data", "assets", "en", "cinema", "cinemas", "sources")


def register(site):
    c = CorePages(site)
    return Plugin(pages=[Emit(c.home), Emit(c.city_pages), Emit(c.cinema_pages), Emit(c.film_pages), Emit(c.card_pages),
                         Emit(c.card_stubs), Emit(c.redirect_pages), Emit(c.halls_page), Emit(c.cinemas_page), Emit(c.sources_page),
                         Emit(c.not_found), Emit(c.offline),
                         Emit(c.slices)])


class CorePages(Pages):
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
            body += self.rail(lang, "near", L(HOME_T["near"], lang), "",
                              sub=f'<span data-near-sub></span><button type="button" class="lnk near-ask" data-near hidden>{esc(L(CHROME_T["near"], lang))}</button>',
                              attrs=" data-near-row hidden")
            body += self.home_rows(lang, films)
            body += self.slot("home.after_tonight", lang)
            # a film in its last days is tagged in the grid too (the «آخر فرصة» row needs 4 films to be drawn)
            last = {f: L(HOME_T["tag_last"], lang) for fs in (self.d.get("last_chance") or {}).values() for f in fs}
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

    # -------------------------------------------------- home: the billboard
    def bill_facts(self, fid, lang):
        """The billboard's facts, each its own span (no dots): the critics' (or audience's) score, the runtime,
        the rating when the score did not already take its place, two genres."""
        f = self.films[fid]; rt = f.get("rt") or {}
        out = [self.score(f, lang)]
        if f.get("runtime"): out.append(f'{num(f["runtime"])} {L(HOME_T["min"], lang)}')
        if f.get("rating") and (rt.get("critics") is not None or rt.get("audience") is not None):
            out.append(f'<bdi class="num" dir="ltr">{esc(f["rating"])}</bdi>')
        g = genre_words(f.get("genres"), lang)[:2]
        if g: out.append(esc(("، " if lang == "ar" else ", ").join(g)))
        return [x for x in out if x]

    def bill_film(self, fid, lang):
        """One film as the billboard's script swaps it in (the JSON island): what the server writes for the first."""
        f = self.films[fid]; v, vw = self.vword(fid, lang); vd = f.get("verdict") or {}
        say = vd.get("ar") if lang == "ar" else vd.get("en")
        bd = f.get("backdrop") if isinstance(f.get("backdrop"), dict) else None
        o = {"t": self.ftitle(fid, lang), "h": P(lang, "film", fid), "v": v, "w": vw, "x": self.bill_facts(fid, lang),
             "c": f.get("poster_color") or hue(fid)}
        if self.title_attr(fid, lang): o["e"] = 1
        if say and v != "unknown": o["s"] = dates(esc(say))   # no verdict yet: the word alone (Task 4 fix round 1, I4)
        if f.get("trailer"): o["tr"] = f["trailer"]
        if bd and bd.get("w1280") and bd.get("w640"): o["b"] = [rel(bd["w640"]), rel(bd["w1280"])]
        elif f.get("poster"): o["p"] = [rel(f["poster"]), rel(f.get("poster_2x") or f["poster"])]
        return o

    # a phone draws the frame darkened under the text: 640w is plenty (at 390 px, 2x, `100vw` took the 1280w file)
    BILL_BD_SIZES = "(min-width:1024px) 100vw, 320px"

    def bill_pick(self, ranked):
        """A city's five slides (fix round 1, I1): the first is its real most-shown film tonight, whatever it looks
        like (the eyebrow says so); the other four prefer the films of its top 10 that have a trailer frame, then
        the rest in order."""
        if not ranked: return []
        has = lambda f: isinstance(self.films[f].get("backdrop"), dict)
        rest = ranked[1:10]
        return (ranked[:1] + [f for f in rest if has(f)] + [f for f in ranked[1:] if not (f in rest and has(f))])[:5]

    def bill_frame(self, fid, o, lang):
        """The billboard's picture: the trailer frame (Kit.backdrop, 640w on a phone); with none yet, the poster — a
        heavily blurred, darkened full-bleed layer (the 342w file: blurred, its size does not show) and, on a
        desktop, a sharp copy at the inline end with the velvet glow (`sizes` 1px on a phone, so there it resolves
        to the same 342w file: one download); with no poster either, the film's typographic tile over the velvet
        glow (Kit.backdrop's fallback, shown). src/js/bill.js draws the same for the next films (fix round 1, I1)."""
        if o.get("b") or not o.get("p"): return self.backdrop(fid, hero=True, sizes=self.BILL_BD_SIZES, lang=lang)
        p342, p684 = esc(o["p"][0]), esc(o["p"][1])
        self.site._preload = f'<link rel="preload" as="image" href="{p342}" fetchpriority="high">'
        return (f'<div class="bd pf" style="--pc:{esc(o["c"])}" aria-hidden="true"><img src="{p342}" class="pb" alt="" width="342" height="513" decoding="async" fetchpriority="high">'
                f'<img src="{p342}" srcset="{p342} 342w, {p684} 684w" sizes="(min-width:1024px) 300px, 1px" class="ps" alt="" width="342" height="513" decoding="async"></div>')

    def bill_price(self, fid, shows):
        """[aed, chain, hall, hall key, cinema, table date]: the film's cheapest ticket among `shows`, the price
        cell's inputs (cinema.js reprices it after the visitor's card), or None."""
        b = self.min_price([s for s in shows if s["film"] == fid])
        if not b: return None
        aed, s = b; code, _ = self.hall_code_label(s)
        return [money(aed), self.cinemas[s["cinema"]]["chain"], code, self.hkey(s), s["cinema"], self.table_date(s)]

    def billboard(self, lang, tops, today):
        """The first of the default city's top 5, server-rendered over its trailer frame (Kit.backdrop, the page's
        LCP, preloaded), and the top 5 of every city as a JSON island: src/js/bill.js swaps the slide when the
        city changes and every 6 s (never under reduced motion; paused on hover, focus and a hidden tab)."""
        city = "dubai" if tops.get("dubai") else "*"
        fids = tops[city]; fid = fids[0]; o = self.bill_film(fid, lang)
        cn = L(CITY["dubai"], lang)
        eye = L(HOME_T["top_in"], lang).format(city=cn) if city != "*" else L(HOME_T["top"], lang)
        in_city = [s for s in today if self.cinemas[s["cinema"]].get("city") == "dubai"] if city != "*" else today
        if o.get("b"):
            self.site._preload = (f'<link rel="preload" as="image" href="{esc(o["b"][1])}" imagesrcset="{esc(o["b"][0])} 640w, {esc(o["b"][1])} 1280w"'
                                  f' imagesizes="{self.BILL_BD_SIZES}" fetchpriority="high">')
        mc = self.min_cell(in_city and [s for s in in_city if s["film"] == fid] or self._by_film.get(fid, []), lang)
        frm = (f'<span class="from" data-from="{esc(fid)}">{esc(L(HOME_T["from"], lang))} {mc[0]}</span>' if mc
               else f'<span class="from" data-from="{esc(fid)}" hidden></span>')
        tr = o.get("tr")
        trailer = (f'<a class="btn ghost" data-bill-tr href="{"https://www.youtube-nocookie.com/embed/" + esc(tr) if tr else "#"}"'
                   + (f' data-trailer="{esc(tr)}"' if tr else " hidden") + ' rel="noopener" target="_blank">'
                   f'<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>{esc(L(HOME_T["trailer"], lang))}</a>')
        say = f' {o["s"]}' if o.get("s") else ""
        slide = (f'<p class="eyebrow" data-bill-eye>{esc(eye)}</p>'
                 f'<h2 class="bill-t"><a href="{o["h"]}" data-bill-a{self.title_attr(fid, lang)}>{esc(o["t"])}</a></h2>'
                 f'<p class="bill-v" data-bill-v><b class="v-{o["v"]}">{esc(o["w"])}{"." if lang == "ar" or say else ""}</b>{say}</p>'
                 f'<p class="bill-f" data-bill-f>{"".join(f"<span>{x}</span>" for x in o["x"])}</p>'
                 f'<p class="cta"><a class="btn main" href="{o["h"]}" data-bill-go>{esc(L(HOME_T["times"], lang))}{frm}</a>{trailer}</p>')
        dots = "".join(f'<button type="button" aria-label="{esc(self.ftitle(x, lang))}" aria-pressed="{"true" if i == 0 else "false"}"><i></i></button>'
                       for i, x in enumerate(fids))
        # the island: each film once, then per city its top 5 with each one's cheapest ticket there
        by_city = {}
        for c, ids in tops.items():
            if not ids: continue   # nothing tonight there: bill.js shows the country's ("*")
            shows = today if c == "*" else [s for s in today if self.cinemas[s["cinema"]].get("city") == c]
            by_city[c] = [[x, self.bill_price(x, shows)] for x in ids]
        ffs = {x: self.bill_film(x, lang) for ids in tops.values() for x in ids}
        island = json.dumps({"f": ffs, "c": by_city}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        return (f'<section class="bill" data-bill aria-roledescription="{"عرض" if lang == "ar" else "carousel"}" aria-label="{esc(L(HOME_T["slides"], lang))}">'
                f'<div class="bill-bd" data-bill-bd>{self.bill_frame(fid, o, lang)}</div>'
                f'<div class="wrap bill-w"><div class="bill-in" data-bill-slide>{slide}</div>'
                f'<div class="bill-nav js-only"><button type="button" class="bill-pp" data-bill-pp aria-pressed="false"{"" if len(fids) > 1 else " hidden"}>'
                f'<span class="vh">{esc(L(HOME_T["pause"], lang))}</span></button>'
                f'<div class="dots" data-bill-dots role="group" aria-label="{esc(L(HOME_T["slides"], lang))}">{dots if len(fids) > 1 else ""}</div></div></div>'
                f'<script type="application/json" id="bill-data">{island}</script></section>')

    # -------------------------------------------------- home: the rows
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
            thu = _thursday_of(self.today)
            items = sorted(fold_near_duplicates(coming), key=lambda kv: (not kv[1].get("release_date"), kv[1].get("release_date") or "", kv[1]["title"]))
            items = [(k, f) for k, f in items if not f.get("release_date") or f["release_date"] >= self.today]
            if len(items) >= 4:
                tiles = "".join(self.coming_tile(k, f, lang, L(HOME_T["tag_thu"], lang) if f.get("release_date") and _thursday_of(f["release_date"]) == thu else None)
                                for k, f in items[:N])
                out.append(self.rail(lang, "coming", L(HOME_T["coming"], lang), tiles, more=P(lang, "coming")))
        last = list(dict.fromkeys(f for fs in (self.d.get("last_chance") or {}).values() for f in fs if f in self.films and f in self.showing))
        row("last", HOME_T["last"], last, tag=L(HOME_T["tag_last"], lang))
        arabic = [f for f in films if str(self.films[f].get("lang") or "").lower() in ("arabic", "ar")]
        row("arabic", HOME_T["arabic"], arabic, P(lang, "arabic") if "arabic" in keys else home + "?fl=Arabic#all")
        return "".join(out)

    def cards_strip(self, lang):
        gov = [c for c in self.cards if c.get("kind") == "gov"]
        bank = [c for c in self.cards if c.get("kind") != "gov"]
        a = lambda c: f'<a href="{P(lang, "cards", c["id"])}">{esc(c["name_ar"] if lang == "ar" else c["name_en"])}</a>'
        return (f'<section class="wrap cardsx"><h2>{"خصم بطاقتك في السينما" if lang == "ar" else "Your card at the cinema"}</h2>'
                f'<p class="lead">{"وين تنفع كل بطاقة، كم تخصم، وشروطها، ومتى تحققنا منها. نعرض بس الخصومات اللي أعلنتها السينما أو البطاقة نفسها." if lang == "ar" else "Where each card works, how much it takes off, the conditions and when we checked. Only discounts the cinema or the card issuer states themselves."}</p>'
                + (f'<p class="links"><span>{"حكومية" if lang == "ar" else "Government"}</span> {" ".join(a(c) for c in gov)}</p>' if gov else "")
                + (f'<p class="links"><span>{"بنوك" if lang == "ar" else "Banks"}</span> {" ".join(a(c) for c in bank)}</p>' if bank else "")
                + f'<p class="links more"><a href="{P(lang, "cards")}">{"كل البطاقات في جدول واحد" if lang == "ar" else "All cards in one table"}</a> <a href="{P(lang, "halls")}">{"القاعات المميزة، شو فيها؟" if lang == "ar" else "Premium halls, explained"}</a></p></section>')

    def sources(self, lang):
        rows = []
        for chain, ch in sorted(self.d.get("chains", {}).items()):
            at = parse_iso(ch["at"]) if ch.get("at") else None
            state = ("" if ch.get("ok", True) else f' <span class="stale">{"ما قدرنا نحدّث آخر مرة" if lang == "ar" else "last refresh failed"}</span>')
            rows.append(f'<li><b>{esc(self.h.chain_name(chain, lang))}</b> '
                        + (f'<span class="age" data-at="{esc(ch["at"])}">{esc(L(T["updated"], lang))} {esc(ago(at, self.now, lang))}</span>' if at else "")
                        + state + '</li>')
        return (f'<section class="wrap srcs"><h2>{"من وين الأسعار" if lang == "ar" else "Where the prices come from"}</h2>'
                f'<p class="hint">{"من نظام الحجز عند كل سينما، ثلاث مرات باليوم. إذا ما حصلنا السعر نكتب «السعر في الشباك»، وما نخمّن." if lang == "ar" else "From each chain’s booking system, three times a day. When we can’t read a price we say «price at the box office» — we never guess."}</p>'
                f'<ul class="chains">{"".join(rows)}</ul></section>')

    def sources_page(self):
        """/sources/: where the prices come from, and each chain's last refresh (was the home page's last section)."""
        for lang in ("ar", "en"):
            name = L(UI["s_sources"], lang)
            body = (f'<section class="head wrap">{self.crumbs(lang, (name, None))}<h1 class="pt">{esc(name)}</h1></section>'
                    + self.sources(lang).replace('<section class="wrap srcs"><h2>', '<section class="wrap srcs"><h2 class="vh">', 1))
            title = ("من وين أسعار السينما — سينما" if lang == "ar" else "Where the cinema prices come from — Cinema")
            desc = ("الأسعار من نظام الحجز عند كل سينما، ومتى حدّثنا كل سلسلة آخر مرة." if lang == "ar"
                    else "Prices come from each chain’s booking system; when each chain was last refreshed.")
            self.page(lang, ("sources",), title, desc, body, [self.breadcrumb_ld(lang, (name, P(lang, "sources")))], "sources", nav="sources")

    def cinemas_page(self):
        """/cinemas/: every cinema by city — the header's «السينمات» and the city pill with no script."""
        for lang in ("ar", "en"):
            name = L(UI["s_cinemas"], lang)
            body = f'<section class="head wrap">{self.crumbs(lang, (name, None))}<h1 class="pt">{esc(name)}</h1></section>'
            for city, a, e in CITIES:
                cids = sorted((cid for cid, c in self.cinemas.items() if c.get("city") == city), key=lambda cid: self.cname(cid, lang))
                cn = L((a, e), lang)
                body += (f'<section class="wrap cities" id="{city}"><h2><a href="{P(lang, city)}">{esc(cn)}</a> '
                         f'<small>{num(len(cids))} {"سينما" if lang == "ar" else ("cinema" if len(cids) == 1 else "cinemas")}</small></h2>')
                if cids:
                    body += ('<ul class="clist">' + "".join(
                        f'<li><a href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a> <span class="n">{esc(self.h.chain_name(self.cinemas[cid]["chain"], lang))}</span></li>'
                        for cid in cids) + '</ul>')
                body += '</section>'
            title = ("كل سينمات الإمارات حسب المدينة — سينما" if lang == "ar" else "Every UAE cinema by city — Cinema")
            desc = ("كل سينما في الإمارات، مدينة مدينة، ولكل سينما صفحة فيها الأوقات والأسعار وخصم البطاقات." if lang == "ar"
                    else "Every cinema in the UAE, city by city; each has a page with showtimes, prices and card discounts.")
            self.page(lang, ("cinemas",), title, desc, body, [self.breadcrumb_ld(lang, (name, P(lang, "cinemas")))], "cinemas", nav="cinemas")

    # -------------------------------------------------- city
    def city_pages(self):
        for city, ar, en in CITIES:
            cids = [cid for cid, c in self.cinemas.items() if c.get("city") == city]
            shows = [s for cid in cids for s in self._by_cin.get(cid, [])]
            today = [s for s in shows if s["date"] == self.today]
            fids = sorted({s["film"] for s in today}, key=lambda f: (-sum(1 for s in today if s["film"] == f), self.ftitle(f, "en")))
            for lang in ("ar", "en"):
                cn = L((ar, en), lang)
                body = f'<section class="head wrap">{self.crumbs(lang, (cn, None))}'
                body += f'<h1 class="pt">{"سينما " + cn + " اليوم" if lang == "ar" else "Cinemas in " + cn + " today"}</h1>'
                if not cids:
                    near = NEAR.get(city, "dubai"); nn = L(CITY[near], lang)
                    body += (f'<p class="lead">{f"ما عندنا بيانات سينما في {cn} لين الحين. أقرب مدينة عندنا: " if lang == "ar" else f"We have no cinema data for {cn} yet. Nearest city: "}'
                             f'<a href="{P(lang, near)}">{esc(nn)}</a>.</p></section>')
                    body += self.ticket_shell()
                else:
                    body += (f'<p class="lead">{f"{len(cids)} سينما و{len(fids)} فيلم اليوم. السعر لكل قاعة من السينما نفسها، وينحسب بعد خصم بطاقتك." if lang == "ar" else f"{len(cids)} cinemas and {len(fids)} films today. Every hall’s price comes from the cinema itself and is worked out after your card."}</p></section>')
                    body += f'<div class="wrap">{self.me(lang, city, "city")}</div>'
                    if fids: body += self.posters_row(lang, fids, today, "الليلة في " + cn if lang == "ar" else "Tonight in " + cn, prayer=True)
                    body += self.slot("city.after_tonight", lang, city=city)
                    body += f'<section class="wrap"><h2>{"السينمات" if lang == "ar" else "Cinemas"}</h2><div class="rows">'
                    for cid in cids:
                        c = self.cinemas[cid]; pr = self.cinema_prices(cid)
                        # the lowest known price in any hall (an unpriced Standard hall must not hide a priced one)
                        low = min(((a, h["code"], k, h["asof"]) for k, h in pr.items() for a in h["seats"].values()), default=None)
                        halls = [k for k in pr if k != "Standard"]
                        hn = ("، " if lang == "ar" else ", ").join(self.h.name(c["chain"], pr[k]["code"], pr[k]["label"], lang) for k in halls)
                        body += (f'<div class="row cin" data-cin="{esc(cid)}"{self.geo_attrs(c)}><a class="nm" href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a>'
                                 f'<span class="sub"><span data-dist></span>{("<bdi>" + esc(hn) + "</bdi>") if hn else ""} {self.fresh(c["chain"], lang)}</span>'
                                 f'<span class="from">{("من " if lang == "ar" else "from ") + self.pcell(low[0], c["chain"], low[1], low[2], cid, low[3], lang) if low else self.box(lang)}</span></div>')
                    body += '</div></section>'
                    cnx = self.next_show(today)
                    tk = self.ticket(cnx, lang) if cnx else self.ticket_shell()

                    def city_sched(mode, fids=fids, today=today, cids=cids, cn=cn, lang=lang, city=city, cnx=cnx):
                        """links / plain: every time a link; compact: times as text; digestN (a busy day): the first
                        N cinemas per film and a link to the film's page — cinema.js redraws the whole list from
                        the city's slice, so only a visitor with no script sees the digest."""
                        small = mode == "compact" or mode.startswith("digest")
                        sched = (f'<section><h2>{"اليوم في " + cn if lang == "ar" else "Today in " + cn}</h2>'
                                 f'<div class="sched"{f" data-sched={chr(34)}{mode.rstrip(chr(49) + chr(50) + chr(51))}{chr(34)}" if small else ""}>')
                        for fid in fids:
                            fs = [s for s in today if s["film"] == fid]
                            v, vw = self.vword(fid, lang)
                            # only the id: cinema.js reads the genres and flags from the film's tile above
                            sched += (f'<div class="srow" data-fid="{esc(fid)}"><div class="sf"><a href="{P(lang, "film", fid)}">{self.title_html(fid, lang, "b", "t")}</a>'
                                      f'<span class="vw v-{v}">{esc(vw)}</span></div><div class="sc">')
                            mine = [cid for cid in cids if any(s["cinema"] == cid and not (small and self.is_past(s)) for s in fs)]
                            shown = mine[:int(mode[-1])] if mode.startswith("digest") else mine
                            for cid in shown:
                                cs = [s for s in fs if s["cinema"] == cid]
                                if small:   # a relative link (the city page is the cinema's parent) and no chain: the slice has it
                                    sched += (f'<div class="scin" data-cin="{esc(cid)}"><a class="cn" href="{esc(cid)}/">{self.cname_html(cid, lang)}</a>'
                                              f'{self.times_compact(cs, lang, tag=True, day_label=False)}</div>')
                                else:
                                    tm = self.times(cs, lang, tag_halls=True, links=mode == "links", day_label=False, on=self.sid(cnx) if cnx else None)
                                    sched += f'<div class="scin" data-cin="{esc(cid)}" data-chain="{esc(self.cinemas[cid]["chain"])}"><a class="cn" href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a>{tm}</div>'
                            if len(mine) > len(shown):
                                n = len(mine) - len(shown)
                                sched += (f'<a class="more" href="{P(lang, "film", fid)}">{f"و{n} سينما ثانية" if lang == "ar" else f"and {n} more cinemas"}</a>')
                            sched += '</div></div>'
                        return sched + '</div></section>'
                    graph0 = [{"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": self.theater_ld(c, lang)} for i, c in enumerate(cids)]}]
                    # the filter and sort sheets (posters_row) ride after the footer: counted here like the body
                    left = PAGE_TARGET - CHROME - len(body.encode()) - len("".join(self._sheets).encode()) - len(tk.encode()) - self.ld_size(graph0) - 600
                    sched, _ = self.fit(city_sched, ("links", "plain", "compact", "digest3", "digest2", "digest1"), left)
                    body += f'<div class="wrap split"><div class="main">{sched}</div>{tk}</div>'
                title = (f"سينما {cn} اليوم — الأفلام والأسعار وخصم فزعة" if lang == "ar" else f"{cn} cinemas today — films, prices and card discounts")
                names = ("، " if lang == "ar" else ", ").join(self.cname(c, lang) for c in cids[:6])
                desc = (f"أفلام سينمات {cn} اليوم ومواعيدها، سعر التذكرة لكل قاعة، والسعر بعد خصم فزعة وإسعاد والبنوك. {names}" if lang == "ar"
                        else f"Films and showtimes at {cn} cinemas today, ticket prices per hall, and the price after Fazaa, Esaad and bank cards. {names}")
                graph = [{"@type": "ItemList", "name": title, "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "item": self.theater_ld(cid, lang)} for i, cid in enumerate(cids)]},
                    self.breadcrumb_ld(lang, (cn, P(lang, city)))]
                self.page(lang, (city,), title, desc, body, graph, "city", f' data-city="{city}" data-chains="{" ".join(sorted({self.cinemas[c]["chain"] for c in cids}))}"', nav="cinemas")

    # -------------------------------------------------- cinema (the second flow: cinema → films → times → ticket)
    def cinema_pages(self):
        for cid, c in self.cinemas.items():
            city, chain = c.get("city"), c["chain"]
            pr = self.cinema_prices(cid)
            shows = self._by_cin.get(cid, [])
            nxt = self.next_show(shows)
            for lang in ("ar", "en"):
                cn, name = L(CITY.get(city, (city, city)), lang), self.cname(cid, lang)
                body = f'<section class="head wrap">{self.crumbs(lang, (cn, P(lang, city)), (name, None))}'
                body += f'<h1 class="pt"{" lang=\"en\"" if self.cname_is_en(cid, lang) else ""}>{esc(name)}</h1>'
                # the name already says the mall; the reader's address is English, isolated
                addr = esc(c.get("address") or ("" if cid in self.names else c.get("mall")) or "")
                body += (f'<p class="lead">{f"<bdi lang=\"en\">{addr}</bdi>" if addr else ""}</p>'
                         f'<p class="meta">{self.directions(c, lang)} {self.fresh(chain, lang, always=True)}</p></section>')
                body += f'<div class="wrap">{self.me(lang, city, "cinema")}</div>'
                body += '<div class="wrap split"><div class="main">'
                cfids = sorted({s["film"] for s in shows})
                body += f'<div class="sec-h cin-h">{self.filters(lang, cfids)}</div>{self.controls(lang, prayer=True)}<p class="empty" data-empty hidden></p>'
                # halls: explained + prices
                rest = ''
                rest += f'<section><h2>{"القاعات والأسعار" if lang == "ar" else "Halls and prices"}</h2><div class="halls">'
                for k, h in pr.items():
                    e = self.h.match(chain, h["code"], h["label"])
                    hn = self.h.name(chain, h["code"], h["label"], lang)
                    what = (e.get("what_ar") if lang == "ar" else e.get("what_en")) if e else ""
                    note = ""
                    if e and e.get("confidence") == "low":
                        note = f' <small class="weak">{"ما تأكدنا من التفاصيل" if lang == "ar" else "details not confirmed"}</small>'
                    src = f' <a class="src" href="{esc(e["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>' if e and e.get("source") else ""
                    seats = "".join(f'<tr><th scope="row">{esc(seat)}</th><td>{self.pcell(aed, chain, h["code"], k, cid, h["asof"], lang)}</td></tr>'
                                    for seat, aed in sorted(h["seats"].items(), key=lambda x: x[1])) or f'<tr><td colspan="2">{self.box(lang)}</td></tr>'
                    rest += (f'<div class="hall"><h3{" lang=\"en\"" if lang == "ar" and re.search("[A-Za-z]", hn) else ""}>{esc(hn)}</h3>' + (f'<p>{dates(esc(what))}{note}{src}</p>' if what else "") +
                             f'<table class="prices"><thead><tr><th scope="col">{"الفئة" if lang == "ar" else "Seat"}</th><th scope="col">{"السعر" if lang == "ar" else "Price"} <small>{esc(L(T["aed"], lang))}</small></th></tr></thead><tbody>{seats}</tbody></table></div>')
                rest += f'</div><p class="hint"><a href="{P(lang, "halls")}">{"كل القاعات المميزة في الإمارات، مقارنة" if lang == "ar" else "Every premium hall in the UAE, compared"}</a></p></section>'
                rest += self.slot("cinema.after_halls", lang, cid=cid)
                # cards (confirmed only)
                rows = ""
                for card in self.cards:
                    r = rule_for(self.rules, chain, card["id"]); st = rule_state(r, self.today)
                    if st == "unchecked": continue
                    rows += self.card_row(card, chain, r, st, lang, P(lang, "cards", card["id"]))
                if rows:
                    rest += f'<section><h2>{"البطاقات في " + self.h.chain_name(chain, lang) if lang == "ar" else "Cards at " + self.h.chain_name(chain, lang)}</h2><div class="rows">{rows}</div></section>'
                rest += '</div>' + (self.ticket(nxt, lang) if nxt else self.ticket_shell()) + '</div>'
                # films with their times, today then tomorrow — as richly as fits what the rest of the page leaves
                th0 = self.theater_ld(cid, lang)
                th0["event"] = [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:40]
                left = PAGE_TARGET - CHROME - len(body.encode()) - len(rest.encode()) - self.ld_size([th0]) - 600
                sched, _ = self.fit(lambda m: self.cinema_schedule(shows, lang, m, self.sid(nxt) if nxt else None), ("full", "today", "plain", "compact"), left)
                body += sched + rest
                title = (f"{name} — أسعار التذاكر ومواعيد اليوم وخصم البطاقات" if lang == "ar" else f"{name} — ticket prices, today’s showtimes and card discounts")
                desc = (f"مواعيد أفلام {name} اليوم، سعر التذكرة لكل قاعة وفئة، شو الفرق بين القاعات، والسعر بعد خصم فزعة وإسعاد والبنوك." if lang == "ar"
                        else f"Today’s showtimes at {name}, ticket prices per hall and seat class, what each hall offers, and the price after Fazaa, Esaad and bank cards.")
                th = self.theater_ld(cid, lang)
                th["event"] = [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:40]
                graph = [th, self.breadcrumb_ld(lang, (cn, P(lang, city)), (name, P(lang, city, cid)))]
                self.page(lang, (city, cid), title, desc, body, graph, "cinema",
                          f' data-city="{city}" data-chains="{chain}" data-cin="{esc(cid)}"', nav="cinemas")

    def cinema_schedule(self, shows, lang, mode, on=None):
        """The films at one cinema: poster, title, verdict, then each hall's time buttons. mode full = today +
        tomorrow with booking URLs; today = today only; plain = today, no booking URLs on the buttons."""
        out = []
        days = ((self.today, ("اليوم", "Today")), (self.tomorrow, ("بكرة", "Tomorrow")))
        for day, lab in days[:2 if mode in ("full", "compact") else 1]:
            ds = [s for s in shows if s["date"] == day]
            if not ds: continue
            out.append(f'<section class="day" data-d="{day}"><h2>{esc(L(lab, lang))} <small>{esc(human_date(day, lang))}</small></h2><div class="cfilms">')
            fids = sorted({s["film"] for s in ds}, key=lambda f: (-sum(1 for s in ds if s["film"] == f), self.ftitle(f, "en")))
            for fid in fids:
                fs = [s for s in ds if s["film"] == fid]
                v, vw = self.vword(fid, lang)
                out.append(f'<div class="cf"{self.film_attrs(fid)} data-v="{v}"><a class="cf-p" href="{P(lang, "film", fid)}" tabindex="-1" aria-hidden="true">{self.poster(fid, lang, "pst sm")}</a>'
                           f'<div class="cf-b"><h3><a href="{P(lang, "film", fid)}"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</a></h3>'
                           f'<p class="cf-m"><span class="vw v-{v}">{esc(vw)}</span>{self.score(self.films[fid], lang)}</p>')
                for k in dict.fromkeys(self.hkey(s) for s in fs):
                    hs = [s for s in fs if self.hkey(s) == k]
                    out.append(f'<div class="hl" data-hall="{esc(hs[0].get("hall") or "OTHER")}" data-hk="{esc(k)}"><span class="hn">{self.hall_html(hs[0], lang)}</span>'
                               + (self.times_compact(hs, lang, day_label=False) if mode == "compact" else
                                  self.times(hs, lang, links=mode != "plain", day_label=False, on=on)) + '</div>')
                out.append('</div></div>')
            out.append('</div></section>')
        if mode not in ("full", "compact"):
            out.append(f'<p class="hint">{"مواعيد بكرة تنزل هني الصبح." if lang == "ar" else "Tomorrow’s times appear here in the morning."}</p>')
        return "".join(out)

    # -------------------------------------------------- film (UI redesign Task 4): hero → day bar → schedule + ticket → tabs
    # a phone draws the trailer frame darkened under the words: the 640w file (as the home billboard)
    FILM_BD_SIZES = "(min-width:1024px) 100vw, 320px"
    # the hero's poster card is a desktop thing: on a phone `1px` resolves to the 342w file the blurred layer already
    # fetched (one download), and with a trailer frame it is display:none there (lazy, so never fetched)
    FILM_POSTER_SIZES = "(min-width:1024px) 240px, 1px"

    def film_rates(self, fid, lang):
        """The critics' and the audience's scores, two plain items in reading order (never the mixed-language
        «basis»); from the verdict's basis when the film has no rt block."""
        f = self.films[fid]; vd = f.get("verdict") or {}; rt = f.get("rt") or {}
        rates = [f'<span>{esc(a if lang == "ar" else e)} {num(str(rt[k]) + "%")}</span>'
                 for k, a, e in (("critics", "النقاد", "Critics"), ("audience", "الجمهور", "Audience")) if rt.get(k) is not None]
        if not rates and vd.get("basis"):   # «RT 96% (249 ناقد)، الجمهور 91%»
            b = str(vd["basis"])
            for rx, a, e in ((r"\bRT (\d{1,3})%", "النقاد", "Critics"), (r"(?:الجمهور|[Aa]udience) (\d{1,3})%", "الجمهور", "Audience")):
                m = re.search(rx, b)
                if m: rates.append(f'<span>{esc(a if lang == "ar" else e)} {num(m.group(1) + "%")}</span>')
        return rates

    def film_people(self, f, key, lang):
        """Names for «المخرج»/«البطولة»: plain names as the data has them, or person ids resolved from data["people"]."""
        pp = self.d.get("people") or {}
        v = f.get(key) if key == "cast" else (f.get("directors") or ([f["director"]] if isinstance(f.get("director"), str) else []))
        out = []
        for x in v if isinstance(v, list) else []:
            if not isinstance(x, str): continue
            if re.match(r"^Q\d+$", x):
                p = pp.get(x) if isinstance(pp, dict) else None
                x = isinstance(p, dict) and ((p.get("name_ar") if lang == "ar" else p.get("name_en")) or p.get("name_en") or p.get("name_ar"))
                if not x or re.match(r"^Q\d+$", str(x)): continue
            out.append(x)
        return out[:4]

    def film_hero(self, fid, lang, rates, cmp_tab):
        """The hero (the mock's .fhero): the trailer frame full-bleed under the header (Kit.backdrop, the page's LCP);
        with none yet, the poster blurred beyond reading on a phone and, on a desktop, the sharp poster card in the
        velvet glow (the home billboard's fallback); the title, the English title and year, the verdict (three
        lines, «المزيد» opens the rest), the facts, and the actions: الإعلان، شارك (pages/og.py), قارن."""
        f = self.films[fid]; v = (f.get("verdict") or {}).get("verdict") or "unknown"
        t = self.ftitle(fid, lang); attr = self.title_attr(fid, lang); ar = lang == "ar"
        bd = f.get("backdrop"); frame = isinstance(bd, dict) and bd.get("w1280") and bd.get("w640")
        pc = esc(f.get("poster_color") or hue(fid))
        if frame:
            w640, w1280 = esc(rel(bd["w640"])), esc(rel(bd["w1280"]))
            self.site._preload = (f'<link rel="preload" as="image" href="{w1280}" imagesrcset="{w640} 640w, {w1280} 1280w"'
                                  f' imagesizes="{self.FILM_BD_SIZES}" fetchpriority="high">')
            pic = self.backdrop(fid, hero=True, sizes=self.FILM_BD_SIZES, lang=lang)
        elif f.get("poster"):
            p342 = esc(rel(f["poster"]))
            self.site._preload = f'<link rel="preload" as="image" href="{p342}" fetchpriority="high">'
            pic = (f'<div class="bd pf" style="--pc:{pc}" aria-hidden="true"><img src="{p342}" class="pb" alt="" width="342" height="513"'
                   f' decoding="async" fetchpriority="high" onerror="this.remove()"></div>')
        else:
            pic = self.backdrop(fid, hero=True, lang=lang)
        card = self.poster(fid, lang, "pst hero", eager=not frame, lazy=bool(frame), size=(342, 513), sizes=self.FILM_POSTER_SIZES)
        yr = f'<span class="num">{esc(f["year"])}</span>' if f.get("year") and not f.get("rerelease") else ""
        en = f'<bdi lang="en" dir="ltr">{esc(f["title"])}</bdi>' if ar and f.get("title_ar") and f.get("title") else ""
        sub = f'<p class="fte">{en}{" " if en and yr else ""}{yr}</p>' if en or yr else ""
        if f.get("rerelease"):
            y = f' <span class="num">{esc(f["year"])}</span>' if f.get("year") else ""
            sub += f'<p class="rr">{esc(L(RERELEASE, lang))}{" — من سنة" if ar and y else (" — first released" if y else "")}{y}</p>'
        vd = f.get("verdict") or {}; say = vd.get("ar") if ar else vd.get("en")
        word = L(VERDICT.get(v, VERDICT["unknown"]), lang)
        # no verdict yet: the word says it all («ما في تقييم كافي»); its template sentence only said it again (fix round 1, I4)
        if v == "unknown": say = None
        verdict = (f'<div class="fv-w"><p class="fv verdict v-{v}" id="fv" data-fv><b class="word">{esc(word)}{"." if say else ""}</b>'
                   + (f' <span class="say">{dates(esc(say))}</span>' if say else "") + '</p>'
                   + (f'<button type="button" class="fv-m" data-fv-more aria-controls="fv" aria-expanded="false" hidden>{esc(L(FILM_T["more"], lang))}</button>'
                      if say else "") + '</div>')
        facts = []
        if rates: facts.append(f'<span class="basis rates">{"".join(rates)}</span>')
        if f.get("runtime"): facts.append(f'<span>{num(f["runtime"])} {esc(L(HOME_T["min"], lang))}</span>')
        if f.get("rating"): facts.append(f'<span><bdi class="num" dir="ltr">{esc(f["rating"])}</bdi></span>')
        gw = genre_words(f.get("genres"), lang)
        ff = (f'<p class="ff">{"".join(facts)}</p>' if facts else "") + (f'<p class="fg">{esc(("، " if ar else ", ").join(gw))}</p>' if gw else "")
        acts = ""
        if f.get("trailer"):
            acts += (f'<a class="btn ghost" href="https://www.youtube-nocookie.com/embed/{esc(f["trailer"])}" data-trailer="{esc(f["trailer"])}" rel="noopener" target="_blank">'
                     f'<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>{esc(L(FILM_T["trailer"], lang))}</a>')
        acts += self.slot("film.share", lang, fid=fid)
        # «قارن» opens its tab (tabs.js); the tab itself is script-drawn (compare.js), so is this link
        if cmp_tab: acts += f'<a class="btn ghost js-only" href="#compare" data-tab-go="compare">{esc(L(FILM_T["compare"], lang))}</a>'
        arch = self.archive_note(fid, lang) if f.get("status") == "archived" else ""
        cls = " fr" if frame else "" if f.get("poster") else " np"   # np: the typographic tile stands in the poster's place
        return (f'<section class="fhero{cls}"><div class="fh-bd">{pic}</div><div class="wrap fhero-in">'
                f'<div class="fposter">{card}</div><div class="fh-t"><h1 class="ft"{attr}>{esc(t)}</h1>{sub}{verdict}{ff}'
                + (f'<p class="cta">{acts}</p>' if acts else "") + f'{arch}</div></div></section>')

    def film_about(self, fid, lang, shows, rates):
        """«عن الفيلم»: the synopsis, the facts (as a list of terms), the basis when no scores came out of it, whatever a
        feature adds (film.info), and the breadcrumb."""
        f = self.films[fid]; vd = f.get("verdict") or {}; ar = lang == "ar"
        facts = []
        for key, a, e in (("director", "المخرج", "Director"), ("cast", "البطولة", "Starring")):
            names = self.film_people(f, key, lang)
            if names: facts.append((a, e, "، ".join(f"<bdi>{esc(n)}</bdi>" for n in names) if ar else ", ".join(esc(n) for n in names)))
        if f.get("runtime"): facts.append(("المدة", "Runtime", num(f["runtime"]) + (" د" if ar else " min")))
        if f.get("rating"): facts.append(("التصنيف", "Rating", f'<bdi class="num" dir="ltr">{esc(f["rating"])}</bdi>'))
        if f.get("lang"): facts.append(("اللغة", "Language", esc(lang_words(f["lang"], lang))))
        subs = [s["subs"] for s in shows if s.get("subs")]
        if subs:
            top = max(set(subs), key=subs.count)
            facts.append(("الترجمة", "Subtitles", esc(lang_words(top, lang))))
        gw = genre_words(f.get("genres"), lang)
        if gw: facts.append(("النوع", "Genre", esc(("، " if ar else ", ").join(gw))))
        if shows:
            nch = len({self.cinemas[s["cinema"]]["chain"] for s in shows}); ns = len(shows)
            chains = ar_count(nch, ("سلسلة وحدة", "سلسلتين", "سلاسل", "سلسلة")) if ar else f"{nch} chain{'s' if nch != 1 else ''}"
            n = ar_count(ns, ("عرض واحد", "عرضين", "عروض", "عرض")) if ar else f"{ns} show{'s' if ns != 1 else ''}"
            say = f"{chains}، {n} اليوم وبكرة" if ar else f"{chains}, {n} today and tomorrow"
            facts.append(("في الإمارات", "In the UAE", dates(esc(say))))
        syn = (f.get("synopsis_ar") if ar else None) or f.get("synopsis") or f.get("overview") or f.get("synopsis_en")
        out = f'<h2 class="tp-h">{esc(L(FILM_T["about"], lang))}</h2>'
        if syn: out += f'<p class="syn"{" lang=\"en\" dir=\"ltr\"" if ar and not f.get("synopsis_ar") else ""}>{esc(syn)}</p>'
        out += '<dl class="facts">' + "".join(f'<div><dt>{esc(a if ar else e)}</dt><dd>{val}</dd></div>' for a, e, val in facts) + '</dl>'
        if not rates and vd.get("basis") and vd["basis"] not in ("manual", "unknown", "template"):
            out += f'<p class="basis"><bdi>{dates(esc(str(vd["basis"]).replace(" · ", "، " if ar else ", ")))}</bdi></p>'
        out += self.slot("film.info", lang, fid=fid)
        return out + self.crumbs(lang, (self.ftitle(fid, lang), None))

    def film_tabs(self, fid, lang, panels):
        """The tabs under the schedule (the mock's .tabsx): عن الفيلم، الطاقم، شي يشبه، فيلمين ورا بعض، قارن — each only
        when it has something. No script: in-page links to the sections, which stand one after another in that
        order; src/js/tabs.js makes them a tablist (arrow keys, aria-selected, the others hidden, #hash opens one).
        «قارن» is script-drawn (compare.js), so its tab is too."""
        order = [k for k in ("about", "cast", "similar", "double", "compare") if panels.get(k)]
        if not order: return ""
        links = "".join(f'<a href="#{k}" data-tab="{k}"{" class=\"js-only\"" if k == "compare" else ""}>{esc(L(FILM_T[k], lang))}</a>' for k in order)
        secs = "".join(f'<section class="tpn" id="{k}">{panels[k]}</section>' for k in order)
        return (f'<div class="ftabs"><div class="wrap tabsx" data-tabs aria-label="{esc(L(FILM_T["tabs"], lang))}">{links}</div></div>'
                f'<div class="wrap tpns">{secs}</div>')

    def film_bar(self, lang, days):
        """The sticky day bar (the mock's .bar) under the header: a button per day the schedule has (the chosen one
        gold; main.js switches them as before), and at its end «⋯», the options sheet: «مع منو رايح؟», «لازم يخلص
        قبل» and the prayer switch (the old control rows, filters.js drives them)."""
        ar = lang == "ar"
        def lab(d):
            x = dt.date.fromisoformat(d); wd = L(WEEKDAYS[x.weekday()], lang)
            return wd, f"{wd} {x.day}"
        btns = "".join(f'<button type="button" class="dy" data-day="{d}" data-wd="{esc(lab(d)[0])}" aria-pressed="{"true" if i == 0 else "false"}">'
                       f'<b>{esc(L(T["today"] if d == self.today else T["tomorrow"] if d == self.tomorrow else (lab(d)[0], lab(d)[0]), lang))}</b>'
                       f'<span class="num">{esc(lab(d)[1])}</span></button>' for i, d in enumerate(days))
        opts = L(FILM_T["opts"], lang)
        more = (f'<button type="button" class="icon dmore" data-sheet-open="sheet-fopts" aria-label="{esc(opts)}">{icon("dots")}'
                f'<b class="fbadge num" data-fcount hidden>0</b></button>')
        b = lambda attrs, label, on=False: f'<button type="button" class="opt" {attrs} aria-pressed="{"true" if on else "false"}">{esc(label)}</button>'
        sec = lambda key, body: (f'<div class="sec"><h3 class="l" id="so-{key}">{esc(L(HOME_T[key], lang))}</h3>'
                                 f'<div class="opts" role="group" aria-labelledby="so-{key}">{body}</div></div>')
        ws = [("solo", "بروحي", "Just me"), ("friends", "ربعي", "Friends"), ("family", "العائلة", "Family"), ("kids", "العيال", "The kids")]
        ends = [("", "ما يهم", "Any time"), ("21:00", "9 بالليل", "9 pm"), ("22:00", "10 بالليل", "10 pm"), ("23:00", "11 بالليل", "11 pm"), ("24:00", "12 بالليل", "Midnight")]
        body = (sec("who", "".join(b(f'data-who="{k}"', a if ar else e) for k, a, e in ws))
                + sec("before", "".join(b(f'data-before="{v}"', a if ar else e, not v) for v, a, e in ends))
                + f'<div class="sec">{self.prayer_switch(lang)}</div>'
                + f'<div class="go"><button type="button" class="btn ghost" data-reset>{esc(L(HOME_T["clear"], lang))}</button>'
                f'<button type="button" class="btn main" data-sheet-close>{"تمام" if ar else "Done"}</button></div>')
        self._sheets.append(self.sheet("sheet-fopts", FILM_T["opts"], body, lang))
        return (f'<div class="dbar js-only"><div class="wrap dbar-in"><div class="days" role="group" aria-label="{esc(L(FILM_T["days"], lang))}">{btns}</div>'
                f'{more}</div></div>')

    def film_pages(self):
        for fid, f in self.films.items():
            shows = self._by_film.get(fid, [])
            vd = f.get("verdict") or {}; v = vd.get("verdict") or "unknown"
            archived = f.get("status") == "archived"
            cities = [c for c, _, _ in CITIES if any(self.cinemas[s["cinema"]].get("city") == c for s in shows)]
            for lang in ("ar", "en"):
                t = self.ftitle(fid, lang)
                rates = self.film_rates(fid, lang)
                panels = {"about": self.film_about(fid, lang, [] if archived else shows, rates),
                          "cast": self.slot("film.cast", lang, fid=fid),
                          "similar": self.similar(fid, lang) if archived else self.slot("film.similar", lang, fid=fid),
                          "double": self.slot("film.double", lang, fid=fid), "compare": self.slot("film.compare", lang, fid=fid)}
                hero = self.film_hero(fid, lang, rates, bool(panels["compare"]))
                tabs = self.film_tabs(fid, lang, panels)
                vword = L(VERDICT.get(v, VERDICT["unknown"]), lang)
                if archived:
                    title = (f"فيلم {t} — انتهى عرضه في سينما الإمارات، ويستاهل؟" if lang == "ar" else f"{t} — no longer in UAE cinemas; was it worth it?")
                    desc = (f"{t}: {vword}. التقييمات والمعلومات، ومتى عُرض في سينمات الإمارات، وشو المعروض الحين." if lang == "ar"
                            else f"{t}: {vword}. Ratings, facts, when it showed in UAE cinemas, and what is showing now.")
                    self.page(lang, ("film", fid), title, desc, hero + tabs, [self.movie_ld(fid, lang), self.breadcrumb_ld(lang, (t, P(lang, "film", fid)))],
                              "film", f' data-fid="{esc(fid)}" data-archived="1"', og_image=f.get("poster_2x") or f.get("poster"))
                    continue
                days = [d for d in (self.today, self.tomorrow) if any(s["date"] == d for s in shows)]
                nxt = self.first_city_show(shows, cities)
                # «اختر وقت» (the desktop column with nothing chosen) and the phone's dock (film.js fills it)
                empty = (f'<div class="tk-empty" data-tk-empty hidden><p class="k">{esc(L(FILM_T["pick"], lang))}</p>'
                         f'<p>{esc(L(FILM_T["pick_s"], lang))}</p></div>')
                dock = (f'<div class="dock" data-dock role="region" aria-label="{esc(L(FILM_T["chosen"], lang))}" hidden><div class="dk-t">'
                        f'<p class="dk-p" data-dk-p></p><p class="dk-s" data-dk-s></p></div>'
                        f'<button type="button" class="btn dk-b" data-dk-open aria-haspopup="dialog">{esc(L(FILM_T["details"], lang))}</button>'
                        f'</div><p class="vh" data-dk-live aria-live="polite"></p>')   # the live region outside the dock: always rendered (M5)
                graph = [self.movie_ld(fid, lang)] + [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:30] + [self.breadcrumb_ld(lang, (t, P(lang, "film", fid)))]
                if not cities:
                    sched = f'<p class="lead">{esc(L(FILM_T["none"], lang))}</p>'
                else:
                    # the schedule is most of the page's weight: render it as richly as fits what the rest leaves
                    bar0 = self.film_bar(lang, days); sheet0 = self._sheets.pop()   # measured (bar and its «⋯» sheet), drawn for real below
                    fixed = len((hero + tabs + bar0 + sheet0).encode())
                    # the ticket as it will be drawn (measured, where this used to reserve 4.5 KB), the page's wrappers
                    tk0 = len((self.ticket(nxt, lang) if nxt else self.ticket_shell()).encode())
                    left = PAGE_TARGET - CHROME - fixed - self.ld_size(graph) - tk0 - len((empty + dock).encode()) - 1200
                    # full, else compact: both keep today AND tomorrow (a page built late at night still has the next
                    # day's times when the visitor's «اليوم» has moved on)
                    sched, mode = self.fit(lambda m: self.film_schedule(shows, cities, lang, m, self.sid(nxt) if nxt else None), ("full", "compact"), left)
                    if mode not in ("full", "compact") and nxt and nxt["date"] != self.today: nxt = self.first_city_show([s for s in shows if s["date"] == self.today], cities) or nxt
                # a day button only for a day the schedule actually has
                days = [d for d in days if f'data-d="{d}"' in sched]
                bar = self.film_bar(lang, days) if cities else ""
                ticket = self.ticket(nxt, lang) if nxt else self.ticket_shell()
                body = (hero + f'<section class="fsched" id="times" aria-labelledby="times-h"><h2 class="vh" id="times-h">{esc(L(FILM_T["times"], lang))}</h2>'
                        f'{bar}<div class="wrap lay"><div class="cgs"><p class="nc" data-nc hidden></p>{sched}<p class="empty" data-empty hidden></p></div>'
                        f'<div class="tkcol">{empty}{ticket}</div></div></section>{tabs}{dock}')
                title = (f"فيلم {t} في سينما الإمارات — المواعيد والأسعار، ويستاهل؟" if lang == "ar" else f"{t} in UAE cinemas — showtimes, prices and is it worth it?")
                desc = (f"{t}: {vword}. مواعيد العرض في سينمات الإمارات اليوم وبكرة، سعر التذكرة لكل قاعة، والسعر بعد خصم بطاقتك." if lang == "ar"
                        else f"{t}: {vword}. Showtimes in UAE cinemas today and tomorrow, ticket prices per hall, and the price after your card discount.")
                self.page(lang, ("film", fid), title, desc, body, graph, "film",
                          f' data-fid="{esc(fid)}" data-chains="{" ".join(sorted({self.cinemas[s["cinema"]]["chain"] for s in shows}))}"'
                          + (f' data-runtime="{int(f["runtime"])}"' if f.get("runtime") else ""),
                          og_image=f.get("poster_2x") or f.get("poster"))

    def archive_note(self, fid, lang):
        """An archived film: when it showed (or that it has ended), and the way back to what is showing now."""
        f = self.films[fid]
        span = span_dates(f.get("first_seen"), f.get("last_seen"), lang) if f.get("first_seen") and f.get("last_seen") else None
        say = ((f"عُرض في سينمات الإمارات من {span}" if lang == "ar" else f"Shown in UAE cinemas from {span}") if span
               else ("انتهى عرضه في السينما" if lang == "ar" else "No longer showing in cinemas"))
        return (f'<div class="archived"><p class="arch-s">{esc(say)}</p>'
                f'<p><a class="btn light" href="{P(lang)}">{"المعروض الحين" if lang == "ar" else "Showing now"}</a></p></div>')

    def similar(self, fid, lang, n=6):
        """Up to n films showing now: shared genre keys first, then by verdict, then by how much they show."""
        mine = set(genre_keys(self.films[fid]))
        rank = {"yes": 0, "mixed": 1, "unknown": 2, "skip": 3}
        pool = [x for x in self.showing if x != fid and self._by_film.get(x)]
        pool.sort(key=lambda x: (-len(mine & set(genre_keys(self.films[x]))), rank.get(self.vword(x, lang)[0], 2), -self.today_count.get(x, 0), x))
        if not pool[:n]: return ""
        tiles = "".join(self.film_tile(x, lang, self._by_film.get(x, [])) for x in pool[:n])
        return (f'<section class="tonight wrap similar"><div class="sec-h"><h2>{"أفلام معروضة الحين تشبهه" if lang == "ar" else "Showing now, in the same vein"}</h2></div>'
                f'<div class="posters grid">{tiles}</div></section>')

    def film_schedule(self, shows, cities, lang, mode, on=None):
        """city → cinema group → hall: the hall's price (once, or per day when days differ), then the time
        buttons per day. mode full = today + tomorrow with booking URLs; today = today only; plain = unlinked.
        Each city is a disclosure (UI redesign Task 4): the visitor's city open and first (main.js renderFilm; Dubai
        with no script), the others folded to «<city>  N سينمات». With script src/js/film.js lays each cinema's
        times out as the mock does: one row per day in time order, every button with its hall and its price after
        the card; the hall rows here are what a visitor with no script reads."""
        days = [(self.today, ("اليوم", "Today"))] + ([(self.tomorrow, ("بكرة", "Tomorrow"))] if mode in ("full", "compact") else [])
        out = []
        # Dubai (the script's default city) first, as the script will show it: no city moves above it at start-up (CLS)
        for city in sorted(cities, key=lambda c: c != "dubai"):
            cs = [s for s in shows if self.cinemas[s["cinema"]].get("city") == city and s["date"] in (d for d, _ in days)]
            if not cs: continue
            cids = list(dict.fromkeys(s["cinema"] for s in cs))
            n = ar_count(len(cids), FILM_T["n_cin"][0]) if lang == "ar" else f'{len(cids)} {FILM_T["n_cin"][1][len(cids) != 1]}'
            out.append(f'<details class="fcity{" here" if city == "dubai" else ""}" data-city="{city}"{" open" if city == "dubai" else ""}><summary><h2>{esc(L(CITY[city], lang))}</h2>'
                       f'<span class="fc-n">{esc(n)}</span></summary>')
            for cid in cids:
                chain = self.cinemas[cid]["chain"]
                ss = [s for s in cs if s["cinema"] == cid]
                out.append(f'<div class="cg" data-cin="{esc(cid)}" data-chain="{esc(chain)}"{self.geo_attrs(self.cinemas[cid])}>'
                           f'<div class="cg-h"><h3><a href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a></h3>'
                           f'<p class="cg-m"><span data-dist></span>{self.fresh(chain, lang)}</p></div>')
                for k in dict.fromkeys(self.hkey(s) for s in ss):
                    hs = [s for s in ss if self.hkey(s) == k]
                    # prices are sampled per show date (weekday/weekend differ): one price per hall when every
                    # day agrees, else one per day — so a live Friday price never stands for Saturday

                    def price_for(group):
                        withp = [s for s in group if any((p.get("aed") or 0) > 0 for p in s.get("prices") or [])]
                        priced = next((s for s in withp if not self.table_date(s)), None) or next(iter(withp), None)  # live first
                        if not priced: return None
                        low = min((p for p in priced["prices"] if (p.get("aed") or 0) > 0), key=lambda p: p["aed"])
                        return (("من " if lang == "ar" else "from ")
                                + self.pcell(low["aed"], chain, priced.get("hall") or "OTHER", k, cid, self.table_date(priced), lang))
                    hd = [(d, lab) for d, lab in days if any(s["date"] == d for s in hs)]
                    per_day = {d: price_for([s for s in hs if s["date"] == d]) for d, _ in hd}
                    known = {v for v in per_day.values() if v}
                    split = len(known) > 1 or (len(known) == 1 and None in per_day.values())
                    pc = "" if split else (next(iter(known)) if known else self.box(lang))
                    rows = "".join(f'<div class="times" data-d="{d}"><span class="dl">{esc(L(lab, lang))}</span>'
                                   + (f'<span class="pr">{per_day[d] or self.box(lang)}</span>' if split else "")
                                   + (f'<span class="tl">{" ".join(sorted({s["time"] for s in hs if s["date"] == d and not self.is_past(s)}))}</span>' if mode == "compact" else
                                      "".join(self.tbtn(s, lang, mode != "plain", False, on == self.sid(s))
                                              for s in sorted((s for s in hs if s["date"] == d), key=lambda s: s["time"])))
                                   + '</div>' for d, lab in hd)
                    out.append(f'<div class="hl" data-hall="{esc(hs[0].get("hall") or "OTHER")}" data-hk="{esc(k)}">'
                               f'<p class="hl-n"><span class="hn">{self.hall_html(hs[0], lang)}</span>' + (f'<span class="pr">{pc}</span>' if pc else "") + f'</p>{rows}</div>')
                out.append('</div>')
            out.append('</details>')
        if mode not in ("full", "compact") and len(days) == 1:
            out.append(f'<p class="hint">{"مواعيد بكرة في صفحة كل سينما." if lang == "ar" else "Tomorrow’s times are on each cinema’s page."}</p>')
        return "".join(out)

    # -------------------------------------------------- cards
    def example(self, chain, card, lang):
        """«تذكرة ستار العادية 42.00 33.60» (struck, then paid) from the cheapest priced seat this chain sells
        in a hall the card covers."""
        best = None
        for s in self.shows:
            if self.cinemas[s["cinema"]]["chain"] != chain: continue
            for p in s.get("prices") or []:
                a, _ = after(p["aed"], chain, s.get("hall") or "OTHER", card, self.rules, self.today, self.hkey(s), s["cinema"])
                if a is not None and (best is None or (s.get("hall") == "Standard", -p["aed"]) > (best[2].get("hall") == "Standard", -best[0])):
                    best = (p["aed"], a, s, p["seat"])
        if not best: return ""
        aed, a, s, seat = best
        hn = self.hname(s, lang)
        what = (f"تذكرة {self.h.chain_name(chain, lang)} {'العادية' if s.get('hall') == 'Standard' else hn} ({seat})" if lang == "ar"
                else f"A {self.h.chain_name(chain, lang)} {'Standard' if s.get('hall') == 'Standard' else hn} ticket ({seat})")
        pp = f' <small class="per">{esc(L(T["per_person"], lang))}</small>' if (rule_for(self.rules, chain, card) or {}).get("type") == "bogo" else ""
        return f'<p class="ex">{esc(what)} <s class="num">{money(aed)}</s> <b class="num">{money(a)}</b> <small>{esc(L(T["aed"], lang))}</small>{pp}</p>'

    def card_pages(self):
        chains = sorted({c["chain"] for c in self.cinemas.values()} | set(self.rules))
        for card in self.cards:
            cid = card["id"]
            for lang in ("ar", "en"):
                cn = card["name_ar"] if lang == "ar" else card["name_en"]
                body = f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, None))}'
                body += f'<h1 class="pt">{"خصم " + cn + " على السينما" if lang == "ar" else cn + " discounts at UAE cinemas"}</h1>'
                ok = [ch for ch in chains if rule_state(rule_for(self.rules, ch, cid), self.today) == "ok"]
                okn = ("، " if lang == "ar" else ", ").join(self.h.chain_name(ch, lang) for ch in ok)
                body += (f'<p class="lead">{(f"تنفع اليوم في: {okn}." if ok else f"ما لقينا خصم قائم لبطاقة {cn} في السينمات اليوم.") if lang == "ar" else (f"Works today at: {okn}." if ok else f"We found no current {cn} discount at UAE cinemas.")}'
                         f' {"كل سطر تحت فيه مصدره وتاريخ آخر فحص." if lang == "ar" else "Every line below carries its source and the date we checked it."}</p></section>')
                body += '<section class="wrap"><div class="rows cardrows">'
                faq = []
                for ch in chains:
                    r = rule_for(self.rules, ch, cid); st = rule_state(r, self.today)
                    if st == "unchecked": continue
                    body += self.card_row(card, ch, r, st, lang, label=self.h.chain_name(ch, lang))
                    if st == "ok": body += self.example(ch, cid, lang)
                    chn = self.h.chain_name(ch, lang)
                    q = f"هل خصم {cn} يشتغل في {chn}؟" if lang == "ar" else f"Does {cn} work at {chn}?"
                    if st == "ok":
                        a = (f"إيه، {rule_offer(r, lang)}" + (f" ({'، '.join(rule_terms(r, lang))})" if rule_terms(r, lang) else "") + f". تحققنا {r.get('checked')}." if lang == "ar"
                             else f"Yes, {rule_offer(r, lang)}" + (f" ({', '.join(rule_terms(r, lang))})" if rule_terms(r, lang) else "") + f". Checked {r.get('checked')}.")
                    elif st == "none_found":
                        a = (f"ما لقينا خصم {cn} في {chn} وقت آخر فحص ({r.get('checked')})." if lang == "ar" else f"We found no {cn} discount at {chn} when we last checked ({r.get('checked')}).")
                    elif st == "expired":
                        a = (f"كان في {rule_offer(r, lang)} لين {r.get('valid_until')}، والعرض انتهى." if lang == "ar" else f"There was {rule_offer(r, lang)} until {r.get('valid_until')}; it has ended.")
                    else: continue
                    faq.append((q, a))
                body += '</div></section>'
                if faq:
                    body += (f'<section class="wrap faq"><h2>{"أسئلة" if lang == "ar" else "Questions"}</h2>'
                             + "".join(f"<details><summary>{esc(q)}</summary><p>{dates(esc(a))}</p></details>" for q, a in faq) + '</section>')
                body += self.cards_strip(lang)
                title = (f"خصم {cn} على السينما — {okn or 'السينمات'}، كم توفّر؟" if lang == "ar" else f"{cn} cinema discount in the UAE — where it works and how much you save")
                desc = (f"وين ينفع خصم {cn} في سينمات الإمارات، كم يخصم، شروطه، وأمثلة على السعر قبل وبعد الخصم — من المصدر الرسمي وبتاريخ الفحص." if lang == "ar"
                        else f"Where the {cn} discount works at UAE cinemas, how much it takes off, its conditions and before/after prices — from the official source, dated.")
                graph = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
                         self.breadcrumb_ld(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, P(lang, "cards", cid)))]
                self.page(lang, ("cards", cid), title, desc, body, graph, "card", nav="cards")
        # index: every confirmed card × every chain
        for lang in ("ar", "en"):
            body = f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_cards"], lang), None))}'
            body += f'<h1 class="pt">{"خصومات السينما بالبطاقات" if lang == "ar" else "Cinema discounts by card"}</h1>'
            body += f'<p class="lead">{"كل بطاقة مقابل كل سلسلة، من المصدر الرسمي. الفراغ يعني ما لقينا خصم رسمي، مب إن السينما ترفض." if lang == "ar" else "Every card against every chain, from the official source. A blank means no official discount found — not that the cinema refuses it."}</p></section>'
            head = "".join(f'<th scope="col">{esc(self.h.chain_name(ch, lang))}</th>' for ch in chains)
            rows = ""
            for card in self.cards:
                cells = ""
                for ch in chains:
                    r = rule_for(self.rules, ch, card["id"]); st = rule_state(r, self.today)
                    txt = (f'<b class="num" dir="ltr">{"1+1" if r.get("type") == "bogo" else (f"{float(r.get("value") or 0):g} AED" if r.get("type") == "fixed" else f"{r.get("value", 0):g}%")}</b>') if st == "ok" else \
                          (f'<span class="nil">{esc(L(T["none_found"], lang))}</span>' if st == "none_found" else f'<span class="nil">{esc(L(T["expired"], lang))}</span>' if st == "expired" else "")
                    cells += f"<td>{txt}</td>"
                rows += f'<tr><th scope="row"><a href="{P(lang, "cards", card["id"])}">{esc(card["name_ar"] if lang == "ar" else card["name_en"])}</a></th>{cells}</tr>'
            body += (f'<section class="wrap"><div class="xwrap"><table class="matrix"><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
                     f'<p class="hint">{"1+1 = تذكرتين بسعر وحدة." if lang == "ar" else "1+1 = buy one, get one."}</p></section>')
            title = ("خصومات السينما في الإمارات — فزعة وإسعاد وعروض البنوك" if lang == "ar" else "UAE cinema discounts — Fazaa, Esaad and bank cards")
            desc = ("جدول واحد لكل خصومات السينما الرسمية في الإمارات: فزعة وإسعاد والبنوك، في فوكس وستار ونوفو وريل وروكسي وسيني رويال وسينما سيتي." if lang == "ar"
                    else "One table of every official UAE cinema discount: Fazaa, Esaad and banks, at VOX, Star, Novo, Reel, Roxy, Cine Royal and Cinemacity.")
            self.page(lang, ("cards",), title, desc, body, [self.breadcrumb_ld(lang, (L(UI["s_cards"], lang), P(lang, "cards")))], "cards", nav="cards")

    # -------------------------------------------------- halls
    def halls_page(self):
        for lang in ("ar", "en"):
            body = f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_halls"], lang), None))}'
            body += f'<h1 class="pt">{"القاعات المميزة في سينمات الإمارات" if lang == "ar" else "Premium cinema halls in the UAE"}</h1>'
            body += f'<p class="lead">{"كل سلسلة تسمّي قاعتها الغالية باسم. هني شو فيها فعلاً، وكم سعرها اليوم، ووين تلقاها." if lang == "ar" else "Every chain names its premium hall differently. Here is what is actually inside, what it costs today and where to find it."}</p></section>'
            faq = []
            for chain, c in self.h.y.items():
                body += f'<section class="wrap hchain"><h2>{esc(self.h.chain_name(chain, lang))}</h2><div class="halls">'
                for e in c.get("halls", []):
                    ss = [s for s in self.shows if self.cinemas[s["cinema"]]["chain"] == chain and self.hkey(s) == e["key"]]
                    ps = [p["aed"] for s in ss for p in s.get("prices") or [] if p.get("aed")]
                    where = sorted({s["cinema"] for s in ss})
                    rng = (f'{num(money(min(ps)))}' + (f' – {num(money(max(ps)))}' if max(ps) != min(ps) else "") + f' <small>{esc(L(T["aed"], lang))}</small>') if ps else ""
                    what = e.get("what_ar") if lang == "ar" else e.get("what_en")
                    conf = {"high": "", "medium": ("من مصدر غير رسمي" if lang == "ar" else "from a non-official source"),
                            "low": ("ما تأكدنا من التفاصيل" if lang == "ar" else "details not confirmed")}.get(e.get("confidence"), "")
                    hname = e.get("name") or e["key"]
                    latin = lang == "ar" and not ARABIC.search(hname)
                    body += (f'<div class="hall"><h3{" lang=\"en\"" if latin else ""}>{esc(hname)}</h3><p>{dates(esc(what))}'
                             + (f' <small class="weak">{esc(conf)}</small>' if conf else "")
                             + (f' <a class="src" href="{esc(e["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>' if e.get("source") else "") + '</p>'
                             + (f'<p class="rng">{"اليوم" if lang == "ar" else "Today"} {rng}</p>' if rng else "")
                             + (f'<p class="where">{"".join(f"<a href=\"{P(lang, self.cinemas[w]["city"], w)}\">{self.cname_html(w, lang)}</a>" for w in where)}</p>' if where else "")
                             + '</div>')
                    faq.append(((f"شو فيها قاعة {e.get('name') or e['key']} في {self.h.chain_name(chain, lang)}؟" if lang == "ar" else f"What is {e.get('name') or e['key']} at {self.h.chain_name(chain, lang)}?"), what))
                body += '</div></section>'
            title = ("قاعات السينما في الإمارات — GOLD وTHEATRE وIMAX وSUITES، شو الفرق وكم السعر؟" if lang == "ar" else "UAE premium cinema halls — GOLD, THEATRE, IMAX, SUITES: what’s the difference?")
            desc = ("شو الفرق بين قاعات فوكس جولد وثياتر وماكس، وستار سويتس، ونوفو سفن ستار، وروكسي بلاتينيوم، وريل دولبي، وكم سعرها اليوم." if lang == "ar"
                    else "The difference between VOX GOLD, THEATRE and MAX, Star Suites, Novo 7 Star, Roxy Platinum, Reel Dolby and more — and what they cost today.")
            graph = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq if a]},
                     self.breadcrumb_ld(lang, (L(UI["s_halls"], lang), P(lang, "halls")))]
            self.page(lang, ("halls",), title, desc, body, graph, "halls")

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

    def card_stubs(self):
        """A card listed in discounts.yaml with no confirmed discount today (homat) had a page on the old site;
        its old link (and the 301 onto this host) lands on a short noindex note and the way to every card,
        not a 404. Not in the sitemap, linked from nowhere."""
        confirmed = {c["id"] for c in self.cards}
        for card in self.disc.get("cards") or []:
            cid = card.get("id")
            if not cid or cid in confirmed or not FID.match(cid):
                continue
            for lang in ("ar", "en"):
                cn = card.get("name_ar") if lang == "ar" else card.get("name_en")
                cn = cn or cid
                body = (f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, None))}'
                        f'<h1 class="pt">{esc(cn)}</h1>'
                        f'<p class="lead">{"ما لقينا خصم مؤكد لهالبطاقة حالياً." if lang == "ar" else "We found no confirmed discount for this card right now."} '
                        f'<a href="{P(lang, "cards")}">{"كل خصومات البطاقات" if lang == "ar" else "Every card discount"}</a></p></section>')
                title = (f"{cn} — ما لقينا خصم مؤكد حالياً" if lang == "ar" else f"{cn} — no confirmed discount right now")
                self.page(lang, ("cards", cid), title, title, body, [], "card", nav="cards",
                          path=os.path.join(self.out, *(["en"] if lang == "en" else []), "cards", cid, "index.html"),
                          robots='<meta name="robots" content="noindex">')

    # -------------------------------------------------- 404
    def not_found(self):
        body = (f'<section class="head wrap nf"><h1 class="pt">ما لقينا هالصفحة</h1>'
                f'<p class="lead">يمكن الفيلم نزل من السينما، أو الرابط تغيّر. <a href="/">الأفلام المعروضة اليوم</a>.</p>'
                f'<p class="lead" lang="en" dir="ltr">We couldn’t find this page. <a href="/en/">Films showing today, in English</a>.</p></section>')
        self.page("ar", (), "ما لقينا هالصفحة — سينما", "الصفحة غير موجودة.", body, [], "404",
                  path=os.path.join(self.out, "404.html"), robots='<meta name="robots" content="noindex">')

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

    def offline(self):
        """The service worker's fallback when a page is not cached and there is no network: one self-contained
        file (its style inline, system fonts), so it looks right on the first offline hit with nothing cached."""
        page = """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ما في إنترنت — سينما</title><meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#0F0B0C"><meta name="color-scheme" content="dark">
<style>
body{margin:0;min-height:100vh;background:#0F0B0C radial-gradient(280px 220px at 70% 90px,rgba(122,22,38,.6),rgba(15,11,12,0)) no-repeat;color:#F1EAE0;
font:16px/1.7 "Readex Pro","Segoe UI",Tahoma,system-ui,sans-serif}
main{max-width:40rem;margin:0 auto;padding:48px 20px}
.m{font-weight:700;font-size:34px;color:#E2B659;text-decoration:none}
h1{font-size:36px;line-height:1.15;margin:40px 0 12px}
p{margin:0 0 14px;color:#C9BDAE}
a{color:#F1EAE0;text-decoration-color:#A89C8E;text-underline-offset:.2em}
[lang=en]{direction:ltr;text-align:left;font-size:14px;color:#A89C8E}
</style></head><body><main>
<a class="m" href="/">سينما</a>
<h1>ما في إنترنت الحين</h1>
<p>الصفحات اللي فتحتها قبل تشتغل بدون نت. ارجع لها، أو جرّب مرة ثانية لين يرجع الاتصال.</p>
<p><a href="/">الأفلام المعروضة اليوم</a></p>
<p lang="en">You are offline. Pages you opened before still work. <a href="/en/">Films today, in English</a>.</p>
</main></body></html>
"""
        self.write(os.path.join(self.out, "offline.html"), page)
