"""Film × city SEO pages: /film/<fid>/<city>/ and /en/film/<fid>/<city>/ (roadmap #256/#258) — one page per
(film, city) pair that actually has a show today or tomorrow, so the page count tracks the day's real schedule
instead of the full films × 8-cities matrix (most of which would be empty and would only cost phone build time).

Deliberately light: no day bar, no ticket sidebar, no dock, no tabs — a plain per-cinema schedule (reusing the
site's own schedule primitives: self.hkey, self.pcell, self.times, self.tbtn) and two links back (to the film's
own page, for the ticket flow, and to the city hub). This module needs nothing from pages/_core/film.py's
film_schedule, which lives on CorePages and is built only inside pages/core.py's register() — every helper used
here is a plain Kit method, reachable straight off `site`.

Wiring: pages/_core/film.py's film_schedule links each city's <summary> to its own page here when one was built
(the film page's own «city sections», per the spec) — see the one-line change there, guarded by
`getattr(site, "city_seo_urls", None)` so a build without this module (or a golden-fixture build) is unaffected."""
from site_kit import CITY, FILM_T, L, P, Page, Plugin, ar_count, esc


MAX_PAIRS = 600  # a safety ceiling on the phone's build time, well above the ~260 pairs today's real data makes;
                  # a data glitch that widens every film to every city can't make this module's cost unbounded


class SeoCity:
    def __init__(self, site):
        self.s = site
        # {(fid, city): [shows]}, today/tomorrow only, skipping archived films (they have nothing to show)
        pairs = {}
        for sh in site.shows:
            fid = sh["film"]
            if site.films.get(fid, {}).get("status") == "archived" or sh["date"] not in (site.today, site.tomorrow):
                continue
            city = site.cinemas.get(sh["cinema"], {}).get("city")
            if city not in CITY:
                continue
            pairs.setdefault((fid, city), []).append(sh)
        # drop a hall whose times have all passed (film_schedule's own contract: a hall heading always has a
        # time to come), keyed like film_schedule does since one page can span several cinemas — done here,
        # before registration, so a pair a build's clock empties out never becomes a Page at all
        pairs = {k: site.live_halls(v, lambda sh: (sh["cinema"], site.hkey(sh))) for k, v in pairs.items()}
        pairs = {k: v for k, v in pairs.items() if v}
        # busiest pairs first, so a day that somehow blows past the ceiling still keeps the ones worth the most
        self.pairs = dict(sorted(pairs.items(), key=lambda kv: -len(kv[1]))[:MAX_PAIRS])

    def _cinema_block(self, lang, cid, shows):
        s = self.s
        chain = s.cinemas[cid]["chain"]
        halls = {}
        for sh in shows:
            halls.setdefault(s.hkey(sh), []).append(sh)
        rows = []
        for k, hs in halls.items():
            best = s.min_price(hs)
            code = s.hall_code_label(hs[0])[0]
            pc = s.pcell(best[0], chain, code, k, cid, s.table_date(best[1]), lang) if best else s.box(lang)
            # times_compact: this page has no ticket dock to wire the full tbtn attributes to, and the full
            # form's per-show data attributes are what pushed a busy city page over the 150 KB budget
            rows.append(f'<div class="hl" data-hall="{esc(code)}" data-hk="{esc(k)}"><p class="hl-n">'
                        f'<span class="hn">{s.hall_html(hs[0], lang)}</span><span class="pr">{pc}</span></p>{s.times_compact(hs, lang, day_label=True)}</div>')
        return (f'<div class="cg" data-cin="{esc(cid)}" data-chain="{esc(chain)}"{s.geo_attrs(s.cinemas[cid])}>'
                f'<div class="cg-h"><h3><a href="{P(lang, s.cinemas[cid]["city"], cid)}">{s.cname_html(cid, lang)}</a></h3>'
                f'<p class="cg-m">{s.fresh(chain, lang)}</p></div>{"".join(rows)}</div>')

    def build(self, fid, city, lang):
        s, ar = self.s, lang == "ar"
        shows = self.pairs.get((fid, city))  # already live_halls-filtered in __init__: never empty when present
        if not shows:
            return None
        t, cname = s.ftitle(fid, lang), L(CITY[city], lang)
        cids = list(dict.fromkeys(sh["cinema"] for sh in shows))
        blocks = "".join(self._cinema_block(lang, cid, [sh for sh in shows if sh["cinema"] == cid]) for cid in cids)
        n = ar_count(len(cids), FILM_T["n_cin"][0]) if ar else f'{len(cids)} {FILM_T["n_cin"][1][len(cids) != 1]}'
        film_href, city_href = P(lang, "film", fid), P(lang, city)
        head = (s.crumbs(lang, (t, film_href), (cname, None)) + f'<h1 class="ft"{s.title_attr(fid, lang)}>{esc(t)}</h1>'
                f'<p class="fte">{esc(cname)} — {esc(n)}</p>')
        # two links, not one joined with a middle dot (the identity bans it); a plain second line reads clean
        # in both languages and sits inside .fsched's own .wrap, so it gets the page's 16px gutter like everything else
        back = (f'<p class="pp-src"><a href="{film_href}">{"كل مواعيد الفيلم" if ar else "All showtimes for this film"}</a></p>'
                f'<p class="pp-src"><a href="{city_href}">{"السينمات في " + esc(cname) if ar else "Cinemas in " + esc(cname)}</a></p>')
        body = f'<section class="head wrap pp">{head}</section><section class="wrap lay fsched">{blocks}{back}</section>'
        title = f"{t} في {cname}: الأوقات والأسعار" if ar else f"{t} in {cname}: showtimes and prices"
        desc = (f"مواعيد عرض {t} في سينمات {cname} اليوم وبكرة، وسعر التذكرة لكل قاعة." if ar
                else f"Showtimes for {t} in {cname} cinemas today and tomorrow, with the ticket price for each hall.")
        graph = ([s.movie_ld(fid, lang)] + [s.screening_ld(sh, lang) for sh in shows[:30]]
                  + [s.breadcrumb_ld(lang, (t, film_href), (cname, P(lang, "film", fid, city)))])
        return {"title": title, "desc": desc, "body": body, "kind": "film", "graph": graph, "nav": "films",
                "og_image": s.films[fid].get("poster_2x") or s.films[fid].get("poster")}


def register(site):
    sc = SeoCity(site)
    pages = [Page(("film", fid, city), lang, (lambda fid=fid, city=city, lang=lang: sc.build(fid, city, lang)))
             for fid, city in sorted(sc.pairs) for lang in ("ar", "en")]
    # pages/_core/film.py reads this to link a city section (film_schedule's <summary>) to its own page here,
    # only for a pair this module actually built (a film with no show today/tomorrow in that city gets no link)
    site.city_seo_urls = {(fid, city) for fid, city in sc.pairs}
    return Plugin(pages=pages)
