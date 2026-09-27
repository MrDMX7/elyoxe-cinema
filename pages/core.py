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
JS = ("core", "pure", "disc", "flip", "prices", "near", "prayer", "home", "filters", "ticket", "trailer", "pwa", "main")
CSS = ()            # src/cinema.css is the base sheet; features append src/css/<name>.css
LAZY_JS = ()
DIRS = tuple(c for c, _, _ in CITIES) + ("film", "cards", "halls", "data", "assets", "en", "cinema")


def register(site):
    c = CorePages(site)
    return Plugin(pages=[Emit(c.home), Emit(c.city_pages), Emit(c.cinema_pages), Emit(c.film_pages), Emit(c.card_pages),
                         Emit(c.card_stubs), Emit(c.redirect_pages), Emit(c.halls_page), Emit(c.not_found), Emit(c.offline),
                         Emit(c.slices)])


class CorePages(Pages):
    # ================================================================ pages
    def home(self):
        films = sorted(self.showing, key=lambda fid: (-self.today_count.get(fid, 0), fid))
        for lang in ("ar", "en"):
            by_city = {c: len([x for x in self.cinemas.values() if x.get("city") == c]) for c, _, _ in CITIES}
            body = ""
            if films:
                fid = films[0]; f = self.films[fid]; v, vw = self.vword(fid, lang)
                vd = f.get("verdict") or {}
                say = vd.get("ar") if lang == "ar" else vd.get("en")
                facts = [x for x in [self.score(f, lang),
                                     (f'{"الجمهور" if lang == "ar" else "Audience"} {num(str((f.get("rt") or {})["audience"]) + "%")}'
                                      if (f.get("rt") or {}).get("audience") is not None and (f.get("rt") or {}).get("critics") is not None else ""),
                                     (num(f["runtime"]) + (" دقيقة" if lang == "ar" else " min")) if f.get("runtime") else ""] if x]
                mc = self.min_cell(self._by_film.get(fid, []), lang)
                trailer = (f'<a class="btn ghost" href="https://www.youtube-nocookie.com/embed/{esc(f["trailer"])}" data-trailer="{esc(f["trailer"])}" rel="noopener" target="_blank">'
                           f'<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>{"العرض الترويجي" if lang == "ar" else "Trailer"}</a>') if f.get("trailer") else ""
                feat = (f'<div class="feat"><p class="eyebrow">{"الأكثر عرضاً الليلة" if lang == "ar" else "Most shown tonight"}</p>'
                        f'<p class="feat-t"{self.title_attr(fid, lang)}><a href="{P(lang, "film", fid)}">{esc(self.ftitle(fid, lang))}</a></p>'
                        f'<p class="feat-m"><span class="vw v-{v}">{esc(vw)}</span>{"".join(f"<span>{x}</span>" for x in facts)}</p>'
                        + (f'<p class="feat-s">{dates(esc(say))}</p>' if say else "")
                        + f'<p class="feat-a"><a class="btn light" href="{P(lang, "film", fid)}">{"الأوقات والأسعار" if lang == "ar" else "Times and prices"}'
                        + (f'<span class="from" data-from="{esc(fid)}">{"من" if lang == "ar" else "from"} {mc[0]} {esc(L(T["aed"], lang))}</span>' if mc else "")
                        + f'</a>{trailer}</p></div>')
                body += f'<section class="hero">{self.backdrop(fid)}<div class="wrap hero-in">{feat}{self.me(lang, "dubai", "home")}</div></section>'
            else:
                body += f'<section class="hero"><div class="wrap hero-in">{self.me(lang, "dubai", "home")}</div></section>'
            body += (f'<h1 class="vh">{"كل سينما في الإمارات، والسعر بعد خصم بطاقتك" if lang == "ar" else "Every cinema in the UAE, priced after your card discount"}</h1>')
            body += self.posters_row(lang, films, self.shows, "الليلة" if lang == "ar" else "Tonight")
            body += self.slot("home.after_tonight", lang)
            body += (f'<section class="wrap cities" id="cities"><h2>{"السينمات حسب المدينة" if lang == "ar" else "Cinemas by city"}</h2><ul class="clist">'
                     + "".join(f'<li><a href="{P(lang, c)}">{esc(L((a, e), lang))}</a> <span class="n">{num(by_city[c])} {"سينما" if lang == "ar" else ("cinema" if by_city[c] == 1 else "cinemas")}</span></li>' for c, a, e in CITIES)
                     + '</ul></section>')
            hn = self.first_city_show(self.shows, ["dubai"])
            body += self.cards_strip(lang) + self.sources(lang) + (self.ticket(hn, lang, hidden=True) if hn else self.ticket_shell())
            title = ("سينما الإمارات اليوم — الأفلام والأسعار وخصم فزعة وإسعاد" if lang == "ar"
                     else "UAE cinemas today — films, ticket prices and card discounts")
            desc = ("مواعيد أفلام اليوم في كل سينمات الإمارات، سعر التذكرة لكل قاعة وفئة، والسعر بعد خصم فزعة وإسعاد وعروض البنوك، وهل الفيلم يستاهل."
                    if lang == "ar" else "Today’s showtimes at every UAE cinema, the ticket price per hall and seat class, the price after Fazaa, Esaad and bank offers, and whether the film is worth it.")
            graph = [{"@type": "WebSite", "name": L(UI["s_mark"], lang), "url": SITE + P(lang), "inLanguage": lang},
                     {"@type": "ItemList", "name": "Films", "itemListElement": [
                         {"@type": "ListItem", "position": i + 1, "url": SITE + P(lang, "film", fid), "name": self.ftitle(fid, lang)} for i, fid in enumerate(films)]},
                     self.breadcrumb_ld(lang)]
            self.page(lang, (), title, desc, body, graph, "home")

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
                    left = PAGE_TARGET - CHROME - len(body.encode()) - len(tk.encode()) - self.ld_size(graph0) - 600
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

    # -------------------------------------------------- film (film → cinemas → times → ticket)
    def film_pages(self):
        for fid, f in self.films.items():
            shows = self._by_film.get(fid, [])
            vd = f.get("verdict") or {}; v = vd.get("verdict") or "unknown"
            cities = [c for c, _, _ in CITIES if any(self.cinemas[s["cinema"]].get("city") == c for s in shows)]
            for lang in ("ar", "en"):
                t = self.ftitle(fid, lang)
                attr = self.title_attr(fid, lang)
                head = self.crumbs(lang, (t, None)) + f'<h1 class="ft"{attr}>{esc(t)}</h1>'
                if lang == "ar" and f.get("title_ar") and f.get("title"): head += f'<p class="fte" lang="en" dir="ltr">{esc(f["title"])}</p>'
                if f.get("rerelease"):
                    yr = f' <span class="num">{esc(f["year"])}</span>' if f.get("year") else ""
                    head += f'<p class="rr">{esc(L(RERELEASE, lang))}{" — من سنة" if lang == "ar" and yr else (" — first released" if yr else "")}{yr}</p>'
                facts = []
                rt = f.get("rt") or {}
                # the ratings sit under the verdict as two plain items, in reading order (not a mixed-language «basis»)
                rates = [f'<span>{esc(a if lang == "ar" else e)} {num(str(rt[k]) + "%")}</span>'
                         for k, a, e in (("critics", "النقاد", "Critics"), ("audience", "الجمهور", "Audience")) if rt.get(k) is not None]
                if not rates and vd.get("basis"):   # no rt block: the verdict's basis carries them («RT 96% (249 ناقد)، الجمهور 91%»)
                    b = str(vd["basis"])
                    for rx, a, e in ((r"\bRT (\d{1,3})%", "النقاد", "Critics"), (r"(?:الجمهور|[Aa]udience) (\d{1,3})%", "الجمهور", "Audience")):
                        m = re.search(rx, b)
                        if m: rates.append(f'<span>{esc(a if lang == "ar" else e)} {num(m.group(1) + "%")}</span>')
                if f.get("runtime"): facts.append(("المدة", "Runtime", num(f["runtime"]) + (" د" if lang == "ar" else " min")))
                if f.get("rating"): facts.append(("التصنيف", "Rating", f'<bdi class="num" dir="ltr">{esc(f["rating"])}</bdi>'))
                if f.get("lang"): facts.append(("اللغة", "Language", esc(lang_words(f["lang"], lang))))
                subs = [s["subs"] for s in shows if s.get("subs")]
                if subs:
                    top = max(set(subs), key=subs.count)
                    facts.append(("الترجمة", "Subtitles", esc(lang_words(top, lang))))
                gw = genre_words(f.get("genres"), lang)
                if gw: facts.append(("النوع", "Genre", esc(("، " if lang == "ar" else ", ").join(gw))))
                say = vd.get("ar") if lang == "ar" else vd.get("en")
                info = (f'<div class="verdict v-{v}"><p class="word">{esc(L(VERDICT.get(v, VERDICT["unknown"]), lang))}</p>'
                        + (f'<p class="say">{dates(esc(say))}</p>' if say else "") + '</div>'
                        + (f'<p class="basis rates">{"".join(rates)}</p>' if rates else
                           f'<p class="basis"><bdi>{dates(esc(str(vd["basis"]).replace(" · ", "، " if lang == "ar" else ", ")))}</bdi></p>'
                           if vd.get("basis") and vd["basis"] not in ("manual", "unknown", "template") else ""))
                syn = (f.get("synopsis_ar") if lang == "ar" else None) or f.get("synopsis") or f.get("overview")
                if syn: info += f'<p class="syn"{" lang=\"en\" dir=\"ltr\"" if lang == "ar" and not f.get("synopsis_ar") else ""}>{esc(syn)}</p>'
                info += '<dl class="facts">' + "".join(f'<div><dt>{esc(a if lang == "ar" else e)}</dt><dd>{val}</dd></div>' for a, e, val in facts) + '</dl>'
                if f.get("trailer"):
                    info += (f'<p class="trl"><a class="btn ghost" href="https://www.youtube-nocookie.com/embed/{esc(f["trailer"])}" data-trailer="{esc(f["trailer"])}" rel="noopener" target="_blank">'
                             f'<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>{"العرض الترويجي" if lang == "ar" else "Trailer"}</a></p>')
                info += self.slot("film.info", lang, fid=fid)
                if f.get("status") == "archived":
                    body = (f'<section class="fhero">{self.backdrop(fid, hero=True)}<div class="wrap fgrid">'
                            f'<div class="fposter">{self.poster(fid, lang, "pst hero", eager=True, size=(342, 513))}</div>'
                            f'<div class="finfo"><div class="fhead">{head}</div>{info}{self.archive_note(fid, lang)}</div></div></section>'
                            + self.similar(fid, lang))
                    title = (f"فيلم {t} — انتهى عرضه في سينما الإمارات، ويستاهل؟" if lang == "ar" else f"{t} — no longer in UAE cinemas; was it worth it?")
                    desc = (f"{t}: {L(VERDICT.get(v, VERDICT['unknown']), lang)}. التقييمات والمعلومات، ومتى عُرض في سينمات الإمارات، وشو المعروض الحين." if lang == "ar"
                            else f"{t}: {L(VERDICT.get(v, VERDICT['unknown']), lang)}. Ratings, facts, when it showed in UAE cinemas, and what is showing now.")
                    self.page(lang, ("film", fid), title, desc, body, [self.movie_ld(fid, lang), self.breadcrumb_ld(lang, (t, P(lang, "film", fid)))],
                              "film", f' data-fid="{esc(fid)}" data-archived="1"', og_image=f.get("poster_2x") or f.get("poster"))
                    continue
                info += self.me(lang, "dubai", "film")
                days = [d for d in (self.today, self.tomorrow) if any(s["date"] == d for s in shows)]
                tabs = "".join(f'<button type="button" class="chip" data-day="{d}" aria-pressed="{"true" if i == 0 else "false"}">{esc(L(T["today"] if d == self.today else T["tomorrow"], lang))}</button>' for i, d in enumerate(days))
                info += (f'<div class="bar js-only"><div class="chips days" role="group" aria-label="{"اليوم" if lang == "ar" else "Day"}">{tabs}</div></div>'
                         f'{self.controls(lang, sort=False, prayer=True)}<p class="empty" data-empty hidden></p>')
                nxt = self.first_city_show(shows, cities)
                if not cities:
                    sched = f'<p class="lead">{"ما لقينا عروض لهذا الفيلم في اليومين الجايين." if lang == "ar" else "No shows for this film in the next two days."}</p>'
                else:
                    # the schedule is most of the page's weight: render it as richly as fits what the rest leaves
                    graph0 = [self.movie_ld(fid, lang)] + [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:30]
                    fixed = len((head + info + self.backdrop(fid, hero=True) + self.poster(fid, lang, "pst hero", size=(342, 513))).encode())
                    left = PAGE_TARGET - CHROME - fixed - self.ld_size(graph0) - 4500 - 1200   # the ticket, the page's wrappers
                    # full, else compact: both keep today AND tomorrow (a page built late at night still has the next
                    # day's times when the visitor's «اليوم» has moved on)
                    sched, mode = self.fit(lambda m: self.film_schedule(shows, cities, lang, m, self.sid(nxt) if nxt else None), ("full", "compact"), left)
                    if mode not in ("full", "compact") and nxt and nxt["date"] != self.today: nxt = self.first_city_show([s for s in shows if s["date"] == self.today], cities) or nxt
                # a day tab only for a day the schedule actually has
                for d in days:
                    if f'data-d="{d}"' not in sched:
                        info = re.sub(r'<button type="button" class="chip" data-day="' + d + r'"[^>]*>[^<]*</button>', "", info)
                ticket = self.ticket(nxt, lang) if nxt else self.ticket_shell()
                body = (f'<section class="fhero">{self.backdrop(fid, hero=True)}<div class="wrap fgrid">'
                        f'<div class="fposter">{self.poster(fid, lang, "pst hero", eager=True, size=(342, 513))}</div>'
                        f'<div class="finfo"><div class="fhead">{head}</div>{info}<div class="cgs">{sched}</div></div>{ticket}</div></section>')
                vword = L(VERDICT.get(v, VERDICT["unknown"]), lang)
                title = (f"فيلم {t} في سينما الإمارات — المواعيد والأسعار، ويستاهل؟" if lang == "ar" else f"{t} in UAE cinemas — showtimes, prices and is it worth it?")
                desc = (f"{t}: {vword}. مواعيد العرض في سينمات الإمارات اليوم وبكرة، سعر التذكرة لكل قاعة، والسعر بعد خصم بطاقتك." if lang == "ar"
                        else f"{t}: {vword}. Showtimes in UAE cinemas today and tomorrow, ticket prices per hall, and the price after your card discount.")
                graph = [self.movie_ld(fid, lang)] + [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:30] + [self.breadcrumb_ld(lang, (t, P(lang, "film", fid)))]
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
        buttons per day. mode full = today + tomorrow with booking URLs; today = today only; plain = unlinked."""
        days = [(self.today, ("اليوم", "Today"))] + ([(self.tomorrow, ("بكرة", "Tomorrow"))] if mode in ("full", "compact") else [])
        out = []
        for city in cities:
            cs = [s for s in shows if self.cinemas[s["cinema"]].get("city") == city and s["date"] in (d for d, _ in days)]
            if not cs: continue
            out.append(f'<section class="fcity" data-city="{city}"><h2><a href="{P(lang, city)}">{esc(L(CITY[city], lang))}</a></h2>')
            for cid in dict.fromkeys(s["cinema"] for s in cs):
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
            out.append('</section>')
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
        chains = {ch: self.h.chain_name(ch, "ar") for ch in set(self.rules) | {c["chain"] for c in self.cinemas.values()}}
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
