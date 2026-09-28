"""Places: the city pages, the cinema pages and /cinemas/ (pages/core.py's places family, moved as it was by
W1-P1). Owner in Wave 2: W2-P6 (MASTER-PLAN §6.2).

Methods of pages.core.CorePages: `self` is a Pages, which reads everything else (self.page, self.poster,
self.shows ...) through to the site."""
from site_kit import *  # noqa: F401,F403  (the names these pages were written against)


TOMORROW_AT_CINEMA = ("مواعيد بكرة تنزل هني الصبح.", "Tomorrow’s times appear here in the morning.")


class PlacesPages:
    def cinemas_page(self):
        """/cinemas/: every cinema by city — the header's «السينمات» and the city pill with no script."""
        for lang in ("ar", "en"):
            name = L(UI["s_cinemas"], lang)
            body = f'<section class="head wrap">{self.crumbs(lang, (name, None))}<h1 class="pt">{esc(name)}</h1></section>'
            for city, a, e in CITIES:
                cids = sorted((cid for cid, c in self.cinemas.items() if c.get("city") == city), key=lambda cid: self.cname(cid, lang))
                cn = L((a, e), lang)
                body += (f'<section class="wrap cities" id="{city}"><h2><a href="{P(lang, city)}">{esc(cn)}</a> '
                         f'<small>{ar_count_num(len(cids), CINEMAS_AR) if lang == "ar" else num(len(cids)) + (" cinema" if len(cids) == 1 else " cinemas")}</small></h2>')
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
                    nc, nf = len(cids), len(fids)
                    counts = (f"{ar_count(nc, CINEMAS_AR)} و{ar_count(nf, FILMS_AR)} اليوم" if lang == "ar" else
                              f"{nc} {'cinema' if nc == 1 else 'cinemas'} and {nf} {'film' if nf == 1 else 'films'} today")
                    body += (f'<p class="lead">{f"{counts}. السعر لكل قاعة من السينما نفسها، وينحسب بعد خصم بطاقتك." if lang == "ar" else f"{counts}. Every hall’s price comes from the cinema itself and is worked out after your card."}</p></section>')
                    body += self.slot("city.hero", lang, city=city)   # the board's rows (W1-P1's slot, W2-P2); in the budget below
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
                body += self.slot("cinema.top", lang, cid=cid, city=city)   # the board's rows (W1-P1's slot, W2-P2); in the budget below
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
                rest += '</div>'
                tk = lambda n: (self.ticket(n, lang) if n else self.ticket_shell()) + '</div>'
                # films with their times, today then tomorrow — as richly as fits what the rest of the page leaves
                th0 = self.theater_ld(cid, lang)
                th0["event"] = [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:40]
                left = PAGE_TARGET - CHROME - len(body.encode()) - len((rest + tk(nxt)).encode()) - self.ld_size([th0]) - 600
                sched, _ = self.fit(lambda m: self.cinema_schedule(shows, lang, m, self.sid(nxt) if nxt else None), ("full", "today", "plain", "compact"), left)
                on = nxt
                if not sched and any(s["date"] == self.today for s in shows):
                    # every time today has started and tomorrow's aren't listed yet: say when they come, no ticket
                    sched, on = f'<p class="hint">{L(TOMORROW_AT_CINEMA, lang)}</p>', None
                body += sched + rest + tk(on)
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
            ds = self.live_halls([s for s in shows if s["date"] == day], lambda s: (s["film"], self.hkey(s)))
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
            out.append(f'<p class="hint">{L(TOMORROW_AT_CINEMA, lang)}</p>')
        return "".join(out)
