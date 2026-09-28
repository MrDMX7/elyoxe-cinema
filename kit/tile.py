"""Film tiles, the coming tile, a home row (rail) and the «كل الأفلام» grid (site_kit.Kit's tile helpers, moved as
they were by W1-P1). Owner: W1-P2, then W2-P4 (MASTER-PLAN §6.2).

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)


class TileKit:
    def film_tile(self, fid, lang, shows, big=False, i=99, live=False, row=False, tag=None):
        """A film tile (UI redesign Task 3): the poster (2:3), the title on one line, «من X درهم» (the cheapest
        ticket, which cinema.js reprices after the visitor's card) or «السعر في الشباك», an optional corner tag
        («الخميس»/«آخر أسبوع»/«إعادة عرض»), and — on a desktop pointer only — a panel over the poster's foot with
        the verdict word and the next time (cinema.js fills [data-next]), laid over it, so nothing moves.
        `row`: a tile in a home row — only the id and runtime the price code reads, not the filter attributes
        (the rows are curated; the filter sheet filters the «كل الأفلام» grid, whose tiles carry them all)."""
        f = self.films[fid]; v, vw = self.vword(fid, lang)
        today = [s for s in shows if s["film"] == fid and s["date"] == self.today] or [s for s in shows if s["film"] == fid]
        mc = self.min_price(today) if live else self.min_cell(today, lang)
        cell = (f'<span class="pv"><span class="num">{money(mc[0])}</span></span>' if live else mc[0]) if mc else ""   # .pv: cinema.js reprices it
        ar = lang == "ar"
        price = (f'{L(HOME_T["from"], lang)} {cell} {esc(L(T["aed"], lang))}' if ar else f'{L(HOME_T["from"], lang)} {esc(L(T["aed"], lang))} {cell}') if mc else self.box(lang)
        tag = tag or (L(RERELEASE, lang) if f.get("rerelease") else None)
        attrs = (f' data-fid="{esc(fid)}"' if row else self.film_attrs(fid)) + f' data-v="{v}"'
        attrs += f' data-runtime="{int(f["runtime"])}"' if f.get("runtime") else ""
        if not row and f.get("lang"): attrs += f' data-lang="{esc(f["lang"])}"'
        sizes = POSTER_SIZES["tile row"] if row else POSTER_SIZES["tile"]
        return (f'<a class="{"tile" if row else "film tile"} v-{v}" href="{P(lang, "film", fid)}"{attrs}>'
                + f'<span class="tp">{self.poster(fid, lang, eager=not row, lazy=row or i >= 1, sizes=sizes, srcset=not row, label=False)}'
                + (f'<span class="tag">{esc(tag)}</span>' if tag else "") + '</span>'
                + f'<span class="t"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</span>'
                + f'<span class="m" data-cheap>{price}</span></a>')

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

    def film_attrs(self, fid):
        """What cinema.js filters a film by: its id, genre keys and the family/kids flags."""
        f = self.films[fid]; fam, kids = film_flags(f)
        return f' data-fid="{esc(fid)}" data-genres="{esc(" ".join(genre_keys(f)))}" data-family="{int(fam)}" data-kids="{int(kids)}"'

    def posters_row(self, lang, fids, shows, heading, city_label="", prayer=False, tags=None, yes=False):
        """«كل الأفلام» (UI redesign Task 3; the home and city pages): every film's tile in a grid (3 columns on
        a phone, 7 on a desktop) under two chips — «تصفية» (the filter sheet; its badge counts what is filtering)
        and the sort. The controls that sat in rows over the list (genre, «مع منو رايح؟», «يخلص قبل», the sort,
        the prayer switch) are in the sheet now, with the language; src/js/filters.js drives them as before.
        The two sheets go after the footer with the header's (self._sheets, emptied by page()) — once per page,
        like the section's ids: /summer/ draws one grid per city (fix round 1, I2); the later grids share them."""
        ar = lang == "ar"
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
        return (f'<section class="all wrap"{sec}>{head}<div class="grid" data-films>{tiles}</div>'
                f'<p class="empty" data-empty hidden></p></section>')

    def rail(self, lang, key, title, tiles, sub="", more=None, attrs=""):
        """A home row (UI redesign Task 3): its heading, an optional line beside it, «الكل» when there is somewhere
        to go, and — on a desktop pointer — two arrow buttons that page the strip. The strip scrolls sideways
        with a finger, a wheel or trackpad, or Tab through its tiles."""
        arrows = (f'<span class="arr js-only"><button type="button" class="icon" data-rail="-1" aria-label="{esc(L(HOME_T["prev"], lang))}">{icon("prev")}</button>'
                  f'<button type="button" class="icon" data-rail="1" aria-label="{esc(L(HOME_T["next"], lang))}">{icon("next")}</button></span>')
        return (f'<section class="rail" aria-labelledby="r-{key}"{attrs}><div class="rail-h wrap"><h2 id="r-{key}">{esc(title)}</h2>'
                + (f'<span class="sub">{sub}</span>' if sub else "")
                + (f'<a class="all-l" href="{esc(more)}">{esc(L(HOME_T["all"], lang))}</a>' if more else "")
                + f'{arrows}</div><div class="strip" data-strip>{tiles}</div></section>')
