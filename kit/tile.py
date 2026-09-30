"""Film tiles, the show card, the coming tile, a home row (rail) and the «كل الأفلام» grid (site_kit.Kit's tile
helpers, moved as they were by W1-P1). Owner: W1-P2, then W2-P4 (MASTER-PLAN §6.2).

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)
from kit.filters import EMPTY, KIDS_AM, KIDS_LATE, RESET, who_fits

# a row's price cells as Kit.pcell writes them (before any card: the list price)
LO_CELL = re.compile(r'<span class="p" data-aed="([0-9.]+)"')
# the verdict word on a tile (MASTER-PLAN §1.4, §1.7): an unknown verdict is the short «الحكم بعده», never a sentence
TILE_V = {"unknown": ("الحكم بعده", "No verdict yet")}


class TileKit:
    def _tile_release_seed(self):
        """Same idea as pages/_core/film.py's FilmPages._release_seed (the earliest `first_seen` across
        every film) -- kept as its own small copy here since TileKit methods run with `self` bound to the
        Site, not to a CorePages instance, so that mixin's method isn't reachable from here."""
        s = getattr(self, "_tile_release_seed_v", None)
        if s is None:
            s = min((str(x.get("first_seen")) for x in self.films.values() if x.get("first_seen")), default="")
            self._tile_release_seed_v = s
        return s

    def week_tag(self, fid, lang):
        """«جديد» for a film in its first week, «الأسبوع N» after — poster TILE views only (owner idea #284,
        round 3 QA), never the film page (film_about already shows the full release date there; this is not
        a replacement for it). Same `released`-over-`first_seen` preference and seed-date guard as the film
        page's own week line, so the two never disagree. Never an «آخر عرض» countdown: no chain feeds a
        last-showing date, so nothing here is ever inferred from one."""
        f = self.films.get(fid) or {}
        if f.get("status") == "archived":
            return None
        rel = f.get("released") or f.get("first_seen")
        if not rel or (not f.get("released") and str(rel) == self._tile_release_seed()):
            return None
        try:
            d0 = dt.date.fromisoformat(str(rel))
        except ValueError:
            return None
        wk = (self.now.date() - d0).days // 7 + 1
        if wk < 1:
            return None
        if wk == 1:
            return "جديد" if lang == "ar" else "New"
        return f"الأسبوع {wk}" if lang == "ar" else f"Week {wk}"

    def film_tile(self, fid, lang, shows, big=False, i=99, live=False, row=False, tag=None):
        """A film tile: the poster (2:3), the title in two lines (their height held, so tiles line up), and the line
        that differs between films. A `live` tile (home and city: its line is redrawn by src/js/home.js for the
        visitor's city, card and clock, MASTER-PLAN §2.1): «من 42» by day, «التالي 21:30 ريل دبي مول» after 17:00,
        «33.60 42» once a card is chosen (yours gold, the list price struck). A live tile in «كل الأفلام» opens with
        the verdict word (13 px Markazi, gold only for «يستاهل»); a row's tile does not (its row already says why it
        is there). Elsewhere (hubs, people, similar films) the older line: «من X درهم» or «السعر في الشباك».
        An optional corner tag («إعادة عرض»), and on a desktop pointer the hover panel home.js draws.
        `row`: a tile in a home row — only the id and runtime the price code reads, not the filter attributes
        (the rows are curated; the filter sheet filters the «كل الأفلام» grid, whose tiles carry them all)."""
        f = self.films[fid]; v, vw = self.vword(fid, lang)
        today = [s for s in shows if s["film"] == fid and s["date"] == self.today] or [s for s in shows if s["film"] == fid]
        mc = self.min_price(today) if live else self.min_cell(today, lang)
        cell = (f'<span class="pv"><span class="num">{money(mc[0])}</span></span>' if live else mc[0]) if mc else ""   # .pv: cinema.js reprices it
        ar = lang == "ar"
        if live: price = f'{L(HOME_T["from"], lang)} {cell}' if mc else self.box(lang)
        else: price = (f'{L(HOME_T["from"], lang)} {cell} {esc(L(T["aed"], lang))}' if ar else f'{L(HOME_T["from"], lang)} {esc(L(T["aed"], lang))} {cell}') if mc else self.box(lang)
        # tag precedence: an explicit tag the caller passed, then «إعادة عرض», then the جديد/الأسبوع N micro-label
        # (round 3 QA, owner idea #284) -- never stacked, so the corner never gets cluttered with two badges
        tag = tag or (L(RERELEASE, lang) if f.get("rerelease") else None)
        wk = None if (tag or row) else self.week_tag(fid, lang)   # not on a curated home row: no tag there (test_home)
        attrs = (f' data-fid="{esc(fid)}"' if row else self.film_attrs(fid, fits=live)) + f' data-v="{v}"'
        attrs += f' data-runtime="{int(f["runtime"])}"' if f.get("runtime") else ""
        if not row and f.get("lang"): attrs += f' data-lang="{esc(f["lang"])}"'
        sizes = POSTER_SIZES["tile row"] if row else POSTER_SIZES["tile"]
        word = (f'<span class="vw">{esc(L(TILE_V.get(v, (vw, vw)), lang))}</span>' if live and not row else "")   # its colour: the tile's v-*
        return (f'<a class="{"tile" if row else "film tile"} v-{v}" href="{P(lang, "film", fid)}"{attrs}>'
                + f'<span class="tp">{self.poster(fid, lang, eager=not row, lazy=row or i >= 1, sizes=sizes, srcset=not row, label=False)}'
                + (f'<span class="tag">{esc(tag)}</span>' if tag else "")
                + (f'<span class="tag wk">{esc(wk)}</span>' if wk else "") + '</span>'
                + f'<span class="t"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</span>'
                + word + f'<span class="m" data-cheap>{price}</span></a>')

    def show_card(self, s, lang):
        """«أرخص عرض الليلة»'s card (MASTER-PLAN §2.1): one show, not a film: the poster, the time and the cinema, and the
        show's cheapest price. It links to the show itself (/film/<fid>/#s-<key>, the show link of §2.2). The film's name
        is said to a screen reader (the poster carries it for the eye). home.js redraws the row from the city's slice
        for the visitor's city, card and clock (renderCheap), as it does every live tile's price (.pv)."""
        fid, cid = s["film"], s["cinema"]
        pr = min(p["aed"] for p in s["prices"] if p.get("aed") and p["aed"] > 0)
        return (f'<a class="tile shc" href="{P(lang, "film", fid)}#s-{self.show_key_of(s)}" data-film="{esc(fid)}">'
                + f'<span class="tp">{self.poster(fid, lang, lazy=True, sizes=POSTER_SIZES["tile row"], srcset=False, label=False)}</span>'
                + f'<span class="vh"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</span>'
                + f'<span class="st"><b class="num">{esc(s["time"])}</b> <bdi>{esc(self.cname(cid, lang))}</bdi></span>'
                + f'<span class="m"><span class="pv"><span class="num">{money(pr)}</span></span></span></a>')

    def coming_tile(self, fid, f, lang, tag=None):
        """A tile for a film the chains announced (data["coming"], not in self.films: no film page yet) — it links
        to «نازل الخميس», and says when instead of a price."""
        pc = hue(fid)
        t = (f.get("title_ar") if lang == "ar" else None) or f.get("title") or fid
        ta = ' lang="en" dir="ltr"' if lang == "ar" and not f.get("title_ar") else ""
        po = str(f.get("poster") or "")
        img = (f'<span class="pst img" style="--pc:{pc}"><span class="pst-t" aria-hidden="true"{ta}>{esc(t)}</span><img src="{esc(rel(po))}" width="342" height="513" alt="" decoding="async" loading="lazy"></span>'
               if SAFE_URL.match(po) or OUR_POSTER.match(po) else
               f'<span class="pst" style="--pc:{pc}"><span class="pst-t"{ta}>{esc(t)}</span></span>')
        when = human_date(f["release_date"], lang) if f.get("release_date") else ("قريباً" if lang == "ar" else "Coming soon")
        return (f'<a class="tile soon" href="{P(lang, "coming")}"><span class="tp">{img}'
                + (f'<span class="tag">{esc(tag)}</span>' if tag else "") + '</span>'
                + f'<span class="t"{ta}>{esc(t)}</span><span class="m">{esc(when)}</span></a>')

    def film_attrs(self, fid, fits=False):
        """What cinema.js filters a film by: its id and genre keys, then either the family/kids flags the genre chips read
        (the cinema page's «عائلي»/«للأطفال»), or, with `fits` («كل الأفلام»), the «مع منو» answers it passes
        (kit/filters.who_fits: data-fits, read by the grid here and by the pick, W2-P2b) and, for a film «العايلة» passes,
        its UAE rating (the pick's «مع منو» fit, MASTER-PLAN §3.1: G/PG 1, PG13 .5)."""
        f = self.films[fid]; a = f' data-fid="{esc(fid)}" data-genres="{esc(" ".join(genre_keys(f)))}"'
        if not fits:
            fam, kids = film_flags(f)
            return a + f' data-family="{int(fam)}" data-kids="{int(kids)}"'
        who = who_fits(f)
        return a + (f' data-fits="{who}"' if who else "") + (f' data-rating="{esc(f["rating"])}"' if "family" in who and f.get("rating") else "")

    def posters_row(self, lang, fids, shows, heading, city_label="", prayer=False, tags=None, yes=False, collapse=False):
        """«كل الأفلام» (UI redesign Task 3; the home and city pages): every film's tile in a grid (3 columns on
        a phone, 7 on a desktop) under two chips — «تصفية» (the filter sheet; its badge counts what is filtering)
        and the sort. The controls that sat in rows over the list are in the sheet, the one question on top
        (kit/filters.py); src/js/filters.js drives them. When nothing is left the line says so (§1.7), and under
        «العيال» after 20:00 it offers tomorrow morning instead.
        The two sheets go after the footer with the header's (self._sheets, emptied by page()) — once per page,
        like the section's ids: /summer/ draws one grid per city (fix round 1, I2); the later grids share them.
        `collapse` (r3-home, owner call 2026-09-30, home only): the grid sits behind one native `<details>` closed
        by default — a single «كل الأفلام (N)» button that expands the whole section in place, no script needed. A
        link to `#all` still opens it for a reader with no script: the fragment target (the inner `<section
        id="all">`) sits inside the `<details>`, which Chromium auto-opens for a same-document fragment navigation
        into a collapsed one. iPhone Safari (the owner's device) does not do this reliably, so with script,
        filters.js's bindFilters forces `details.allg.open = true` itself whenever a «الكل» row link's query
        (`?sort=`/`?f=`/`?who=`/`?fl=`) or an `#all` hash targets it, and again before the «اعرض N» sheet button's
        scroll — fix round, review Important #3."""
        first = not self._grid
        tiles = "".join(self.film_tile(fid, lang, shows, i=i, live=True, tag=(tags or {}).get(fid)) for i, fid in enumerate(fids))
        hid = ' id="all-h"' if first else ""
        head = (f'<div class="all-h"><h2{hid}>{esc(heading)}<span class="h-city" data-city-label>{esc(city_label)}</span> '
                f'<span class="all-n num" data-all-n>{len(fids)}</span></h2>'
                f'<button type="button" class="chip fchip js-only" data-sheet-open="sheet-filter">{icon("filter")}{esc(L(HOME_T["filter"], lang))}'
                f'<b class="fbadge num" data-fcount hidden>0</b></button>'
                f'<button type="button" class="chip js-only" data-sheet-open="sheet-sort">{esc(L(HOME_T["sort"], lang))}:&nbsp;'
                f'<span data-sort-name>{esc(L(HOME_T["sort_default"], lang))}</span></button></div>')
        if first: self._sheets.append(self.filter_sheet(lang, fids, prayer, yes) + self.sort_sheet(lang))
        self._grid = True
        sec = ' id="all" aria-labelledby="all-h"' if first else ""
        section = (f'<section class="all wrap"{sec}>{head}<div class="grid" data-films>{tiles}</div>'
                   f'<p class="empty" data-empty hidden>{esc(L(EMPTY, lang))} <button type="button" class="lnk" data-reset>{esc(L(RESET, lang))}</button></p>'
                   f'<p class="empty" data-kids-late hidden>{esc(L(KIDS_LATE, lang))} <button type="button" class="lnk" data-kids-am>{esc(L(KIDS_AM, lang))}</button></p></section>')
        if collapse and first:
            summary = f'<summary class="allg-sum wrap">{esc(heading)} <span class="num">({len(fids)})</span></summary>'
            return f'<details class="allg">{summary}{section}</details>'
        return section

    @staticmethod
    def lo(cells):
        """Gold is yours (MASTER-PLAN §1.5): with no card, the one cheapest price of a row is lit (class «lo»), the rest
        are screen light. The build lights it for the first paint and for a reader with no script; src/js/prices.js
        lows() lights it again after every repricing ([data-lo]), and a chosen card turns the after-card prices gold
        instead. A tie lights the first, as lows() does."""
        best = min(((float(m.group(1)), m.start()) for m in LO_CELL.finditer(cells)), default=None)
        if best is None: return cells
        i = best[1] + len('<span class="p')
        return cells[:i] + " lo" + cells[i:]

    def rail(self, lang, key, title, tiles, sub="", more=None, attrs=""):
        """A home row: its heading, which is the link to «الكل» when there is somewhere to go (the whole heading line
        is the target, at least 44 px tall, MASTER-PLAN §2.1 and §4.2 #15), an optional line under it (a door, a
        note), and — on a desktop pointer — two arrow buttons that page the strip. The strip scrolls sideways with a
        finger, a wheel or trackpad, or Tab through its tiles."""
        arrows = (f'<span class="arr js-only"><button type="button" class="icon" data-rail="-1" aria-label="{esc(L(HOME_T["prev"], lang))}">{icon("prev")}</button>'
                  f'<button type="button" class="icon" data-rail="1" aria-label="{esc(L(HOME_T["next"], lang))}">{icon("next")}</button></span>')
        h = f'<h2 id="r-{key}">{esc(title)}</h2>'
        head = (f'<a class="rail-a" href="{esc(more)}">{h}<span class="all-l">{esc(L(HOME_T["all"], lang))}</span></a>' if more else h)
        return (f'<section class="rail" aria-labelledby="r-{key}"{attrs}><div class="rail-h wrap">{head}{arrows}'
                + (f'<p class="sub">{sub}</p>' if sub else "")
                + f'</div><div class="strip" data-strip data-lo>{self.lo(tiles)}</div></section>')
