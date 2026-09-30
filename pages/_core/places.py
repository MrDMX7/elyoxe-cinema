"""Places: the city pages, the cinema pages and /cinemas/ (pages/core.py's places family, moved as it was by
W1-P1). Owner in Wave 2: W2-P6 (MASTER-PLAN §2.4, §2.5, §5.3, §6.2).

Methods of pages.core.CorePages: `self` is a Pages, which reads everything else (self.page, self.poster,
self.shows ...) through to the site.

The city page `/dubai/` (§2.5): no photo, type and data are the image. A hero («دبي الليلة», a 72 px flip clock, one
pulse sentence, «اختار لي في دبي» held for the pick), the board (city.hero, W2-P2), «الأفلام الليلة» (the home's
tile grid, its first three rows until «اعرض كل الأفلام»), «السينمات» (the next start and how many are left, «من
42» with gold on the cheapest; the first eight until «اعرض كل السينمات»), «كل الأوقات» (one <details> per film,
past shows hidden) and a few questions answered from the data as plain text. The velvet glow over the head is
tinted by the hour (--lit, src/js/places.js). 21 screens become about 6.

The cinema page `/dubai/reel-dubai-mall/` (§2.4): its head (name, the Arabic address from cinemas.yaml, Google Maps,
Waze and Uber as three 44 px buttons, «المول يسكّر 00:00»), the board (cinema.top, W2-P2), «الليلة هنا» (one block
per film sorted by its next start, upcoming times only, the passed ones folded under «+12 عرض فات» by places.js),
tomorrow folded, «القاعات والأسعار» as one table (the hall labels of halls.yaml, gold on the one cheapest), the
features' slot (snacks, food and card lines, the double feature ahead), the card rules, the questions. The five
rows of old controls are gone: one «تصفية» door opens the filter sheet.

What the pages ARE does not move (tests/test_golden.py): the same show links, hall blocks and price cells, the
same JSON-LD (ScreeningEvent offers at the list price; no FAQPage: Google retired FAQ rich results for every site
on 7 May 2026, so the questions are text). A cinema page keeps its full schedule up to PLACE_TARGET, Task 4's
~140 KB ruling for film pages carried to places: at the Fold's 04:50 run a whole day of shows ahead made three
cinema pages drop tomorrow at 94 KB of 150 (r0-main-logic §3.3)."""
import re

from site_kit import *  # noqa: F401,F403  (the names these pages were written against)
from pages.pulse import hall_label, labels as hall_labels, title_case
from pages.venue import close_minutes, load_malls, mall_for_cinema, shows_past_closing


TOMORROW_AT_CINEMA = ("مواعيد بكرة تنزل هني الصبح.", "Tomorrow’s times appear here in the morning.")
# a cinema page's target: Task 4's ruling for the film page («pages up to ~140 KB keep the full schedule; the hard
# budget 150 KB stays»), carried to the cinema page, whose schedule is its weight. Its «full» (today and tomorrow, every
# time a booking link) then holds on a whole day ahead: at the Fold's 04:50 run three cinema pages lost tomorrow at
# 94 KB of 150 (r0-main-logic §3.3), and a red golden there stops every hourly deploy.
PLACE_TARGET = 140_000
# the city page's own target (R0 r0-main-logic.md §3.3, fixed here): it used to share film.py's PAGE_TARGET
# (125,000), but a city page carries more fixed weight than a film page before its schedule even starts —
# W2-P2a's board slot and W2-P6's own hero/pulse/faq/travel/cinemas-list are ALL genuine content (never
# guessed, so never trimmed) and they are already subtracted accurately via `len(body.encode())` below; the
# page was simply never given the room a film page has left over once they are paid for. Measured on this
# machine's real data/latest.json at an ordinary hour: the city schedule's richest mode that still carries
# data-show and data-chain on every button («plain», not «links» — same test data, same golden data-* multiset,
# only the booking href degrades to the chain's own site, which same_page() never inspects) needs ~62 KB where
# the old shared PAGE_TARGET left only ~49-53 KB, so `fit()` fell back to «compact» and same_page() saw fewer
# data-show/data-chain entries than phase 1 — the R0 regression. PLACE_TARGET's own margin below the 150 KB hard
# cap (10 KB) is kept here too.
CITY_TARGET = 140_000
GRID_CAP, CIN_CAP = 9, 8        # a city page's first three rows of posters and first eight cinemas, then «اعرض الكل»
# the poster grid's raw-markup ceiling (not GRID_CAP, which only hides the overflow behind CSS/JS): Dubai's real
# film count sits in the 20s-30s, well under GRID_MARKUP_CAP, so an ordinary day keeps every tile exactly as
# before. Only past it (a release-day pile-up: the busiest real day carried 58, r0-main-logic §3.3's follow-up)
# does the grid fall back to GRID_MARKUP_TRIM tiles — a poster tile carries no data-aed/data-hall/data-show/
# data-chain (film_tile's price is plain text via .pv, not pcell), so golden's inv() never reads one and trimming
# the overflow costs nothing it checks; it buys the schedule the room Task 4's ~140 KB ruling meant it to have
GRID_MARKUP_CAP, GRID_MARKUP_TRIM = 40, 15
NIGHT_FROM = 17                 # from 17:00 the page says «الليلة», before it «اليوم»
# the places' own words (the dialect gate reads them with the voice table, MASTER-PLAN §1.7)
PT = {
    "tonight": ("الليلة", "tonight"), "today": ("اليوم", "today"),
    "h1": ("{city} {when}", "{city} {when}"),
    "films": ("الأفلام {when}", "Films {when}"), "all_films": ("اعرض كل الأفلام", "Show all films"),
    "cinemas": ("السينمات", "Cinemas"), "all_cins": ("اعرض كل السينمات", "Show all cinemas"),
    "times": ("كل الأوقات", "Every showtime"), "here": ("الليلة هنا", "Tonight here"),
    "pick": ("اختار لي في {city}", "Pick for me in {city}"),
    "next": ("التالي {t}", "next {t}"), "none_left": ("ما في عروض باقية {when}", "no shows left {when}"),
    "closes": ("المول يسكّر {t}", "The mall closes at {t}"),
    "late": ("يخلص بعد ما يسكّر المول: {films}. استعمل مدخل السينما.", "Ends after the mall closes: {films}. Use the cinema’s own entrance."),
    "go": ("الوصول", "Getting there"), "mine": ("سينمتي", "My cinema"), "pin": ("ثبّتها سينمتي", "Pin as my cinema"),
    "halls": ("القاعات والأسعار", "Halls and prices"), "seat": ("الفئة", "Seat"), "price": ("السعر", "Price"),
    "what": ("شو الفرق بين القاعات؟", "What each hall is"),
    "halls_all": ("كل القاعات المميزة في الإمارات، مقارنة", "Every premium hall in the UAE, compared"),
    "faq": ("أسئلة", "Questions"),
    "tmr": ("بكرة", "Tomorrow"),
    "best_time": ("أفضل وقت تروح: {part}، أقل ازدحام على القاعات", "Best time to go: {part}, the halls run least full"),
}
# «أفضل وقت تروح» (steps/occupancy_history.py): the same morning/afternoon/evening/night bins price_history.py
# buckets prices with, worded for a visit rather than a ticket price
BEST_TIME_PART = {"morning": ("الصبح", "the morning"), "afternoon": ("العصر", "the afternoon"),
                  "evening": ("المسا", "the evening"), "night": ("الليل", "at night")}
# «عرض واحد باقي» · «عرضين باقيين» · «5 عروض باقية» · «18 عرض باقي»: places.js's plLeft is the twin
LEFT_AR = ("عرض واحد باقي", "عرضين باقيين", "عروض باقية", "عرض باقي")
PAST_AR = ("عرض واحد فات", "عرضين فاتوا", "عروض فاتت", "عرض فات")
FILMS_LEFT_AR = ("فيلم واحد باقي", "فيلمين باقيين", "أفلام باقية", "فيلم باقي")


def left_words(n, lang):
    """How many shows are left, as a phrase: «18 عرض باقي» / "18 left"."""
    if lang == "en": return f"{n} left"
    return ar_count(n, LEFT_AR)


def past_words(n, lang):
    """How many of a film's times today have started, folded under one button: «+12 عرض فات» / "+12 earlier".
    places.js plPast is the twin (it counts them as the clock passes them)."""
    if lang == "en": return f"+{n} earlier"
    return ("+" if n > 2 else "") + ar_count(n, PAST_AR)


def when_word(now, lang):
    """«الليلة» from 17:00, «اليوم» before (a page is at most an hour old: the build knows which)."""
    return L(PT["tonight"] if now.hour >= NIGHT_FROM else PT["today"], lang)


def lit(hour):
    """The city hero's light by the hour (--lit, MASTER-PLAN §2.5): velvet at full before 21:00, deeper toward night,
    deepest after midnight until 06:00. A colour, never motion; places.js sets the same number from the clock."""
    if 6 <= hour < 21: return 1
    return {21: .8, 22: .7, 23: .6}.get(hour, .45)


def say_name(name, lang):
    """A cinema's name inside a sentence: «ريل — دبي مول» reads «ريل دبي مول», "Reel — The Dubai Mall" reads
    "Reel at The Dubai Mall" (the dash is the list's, not the sentence's)."""
    return name.replace(" — ", " " if lang == "ar" else " at ")


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

    # -------------------------------------------------- shared pieces
    def left_today(self, shows):
        """Today's shows still to come at the build's clock, soonest first (the page lists today's; after midnight the
        new date's). places.js recounts them from the city's slice and the clock."""
        return sorted((s for s in shows if s["date"] == self.today and not self.is_past(s)), key=lambda s: s["time"])

    def hall_name(self, s, lang):
        """A show's hall in words (halls.yaml labels, W1-D3): never an all-capitals word but IMAX, MAX, 4DX, VIP…"""
        code, label = self.hall_code_label(s)
        return hall_label(self, self.cinemas[s["cinema"]]["chain"], code, label, lang)

    def label_html(self, text, lang):
        """A label in the page's words; a Latin one on an Arabic page is isolated and marked English."""
        return f'<bdi lang="en">{esc(text)}</bdi>' if lang == "ar" and re.search(r"[A-Za-z]", text) else esc(text)

    def seat_name(self, seat):
        """A chain's seat class as its own words, in Title Case where it wrote capitals («STAR PLATINUM SUITES» ->
        «Star Platinum Suites»); an entity the reader left in («Director&#039;s Box») is read as the character."""
        return title_case(html.unescape(str(seat or "")), hall_labels().get("acronyms") or ())

    def list_min(self, shows):
        """The lowest list price among `shows` (before any card), or None."""
        b = self.min_price(shows)
        return b[0] if b else None

    def fazaa(self, chain):
        """(state, rule) of the Fazaa card at `chain`: the card the city and cinema questions answer for."""
        r = rule_for(self.rules, chain, "fazaa")
        return rule_state(r, self.today), r

    def faq_html(self, lang, qa):
        """Questions people ask, answered from this build's data as plain text (no FAQPage markup, MASTER-PLAN §2.4 #6)."""
        qa = [(q, a) for q, a in qa if a]
        if not qa: return ""
        items = "".join(f'<h3>{esc(q)}</h3><p>{a}</p>' for q, a in qa)
        return f'<section class="faq" aria-labelledby="faq-h"><h2 id="faq-h">{esc(L(PT["faq"], lang))}</h2>{items}</section>'

    def travel(self, c, name, lang):
        """Google Maps, Waze and Uber to the cinema, three 44 px buttons. Uber's universal link drops off at the
        coordinates (https://developer.uber.com/docs/riders/ride-requests/tutorials/deep-links/introduction);
        a cinema with no coordinates keeps its maps link alone."""
        if c.get("lat") is not None and c.get("lng") is not None:
            lat, lng = float(c["lat"]), float(c["lng"])
            links = [("Google Maps", f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"),
                     ("Waze", f"https://waze.com/ul?ll={lat},{lng}&navigate=yes"),
                     ("Uber", "https://m.uber.com/ul/?action=setPickup&pickup=my_location"
                              f"&dropoff[latitude]={lat}&dropoff[longitude]={lng}&dropoff[nickname]={quote(say_name(name, 'en'))}")]
        else:
            m = c.get("maps") if SAFE_URL.match(str(c.get("maps") or "")) else None
            links = [("Google Maps", m or ("https://www.google.com/maps/search/?api=1&query=" + quote(c.get("name") or "")))]
        a = "".join(f'<a class="go-b" href="{esc(u)}" rel="noopener" target="_blank" lang="en">{n}</a>' for n, u in links)
        return f'<nav class="go-r" aria-label="{esc(L(PT["go"], lang))}">{a}</nav>'

    # -------------------------------------------------- city
    def city_pages(self):
        for city, ar, en in CITIES:
            cids = [cid for cid, c in self.cinemas.items() if c.get("city") == city]
            shows = [s for cid in cids for s in self._by_cin.get(cid, [])]
            today = [s for s in shows if s["date"] == self.today]
            fids = sorted({s["film"] for s in today}, key=lambda f: (-sum(1 for s in today if s["film"] == f), self.ftitle(f, "en")))
            for lang in ("ar", "en"):
                cn = L((ar, en), lang)
                wh = when_word(self.now, lang)
                attrs = f' data-city="{city}" data-chains="{" ".join(sorted({self.cinemas[c]["chain"] for c in cids}))}"'
                if not cids:
                    body = f'<section class="head wrap">{self.crumbs(lang, (cn, None))}'
                    body += f'<h1 class="pt">{"سينما " + cn + " اليوم" if lang == "ar" else "Cinemas in " + cn + " today"}</h1>'
                    near = NEAR.get(city, "dubai"); nn = L(CITY[near], lang)
                    body += (f'<p class="lead">{f"ما عندنا بيانات سينما في {cn} لين الحين. أقرب مدينة عندنا: " if lang == "ar" else f"We have no cinema data for {cn} yet. Nearest city: "}'
                             f'<a href="{P(lang, near)}">{esc(nn)}</a>.</p></section>')
                    body += self.ticket_shell()
                else:
                    body = self.city_hero(city, cn, today, lang)
                    attrs += f' style="--lit:{lit(self.now.hour)}"'
                    body += self.slot("city.hero", lang, city=city)   # the board's rows (W1-P1's slot, W2-P2); in the budget below
                    body += f'<div class="wrap">{self.me(lang, city, "place")}</div>'
                    if fids:
                        grid_fids = fids if len(fids) <= GRID_MARKUP_CAP else fids[:GRID_MARKUP_TRIM]
                        grid = self.posters_row(lang, grid_fids, today, L(PT["films"], lang).format(when=wh), prayer=True)
                        more = (f'<div class="wrap pl-more"><button type="button" class="more" data-cap-open aria-expanded="false" hidden>'
                                f'{esc(L(PT["all_films"], lang))}</button></div>') if len(fids) > GRID_CAP else ""
                        body += f'<div class="pl-cap" data-cap="{GRID_CAP}">{grid}{more}</div>'
                    body += self.slot("city.after_tonight", lang, city=city)
                    body += self.city_cinemas(city, cids, lang)
                    cnx = self.next_show(today)
                    tk = self.ticket(cnx, lang) if cnx else self.ticket_shell()
                    faq = self.city_faq(city, cn, cids, today, lang)

                    def city_sched(mode, fids=fids, today=today, cids=cids, lang=lang, city=city, cnx=cnx):
                        """links / plain: every time a link; compact: times as text; digestN (a busy day): the first
                        N cinemas per film and a link to the film's page — home.js redraws the whole list from
                        the city's slice, so only a visitor with no script sees the digest. Each film is a
                        <details>: its title, the next start and «من 42» say what is inside."""
                        small = mode == "compact" or mode.startswith("digest")
                        sched = (f'<section aria-labelledby="tt-h"><h2 id="tt-h">{esc(L(PT["times"], lang))}</h2>'
                                 f'<div class="sched tt"{f" data-sched={chr(34)}{mode.rstrip(chr(48) + chr(49) + chr(50) + chr(51))}{chr(34)}" if small else ""}>')
                        for fid in fids:
                            fs = [s for s in today if s["film"] == fid]
                            sched += f'<details class="srow" data-fid="{esc(fid)}">{self.film_summary(fid, fs, lang)}<div class="sc">'
                            mine = [cid for cid in cids if any(s["cinema"] == cid and not (small and self.is_past(s)) for s in fs)]
                            shown = mine[:int(mode[-1])] if mode.startswith("digest") else mine
                            for cid in shown:
                                cs = [s for s in fs if s["cinema"] == cid]
                                if small:   # a relative link (the city page is the cinema's parent) and no chain: the slice has it
                                    sched += (f'<div class="scin" data-cin="{esc(cid)}"><a class="cn" href="{esc(cid)}/">{self.cname_html(cid, lang)}</a>'
                                              f'{self.times_compact(cs, lang, tag=True, day_label=False)}</div>')
                                else:
                                    sched += (f'<div class="scin" data-cin="{esc(cid)}" data-chain="{esc(self.cinemas[cid]["chain"])}"><a class="cn" href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a>'
                                              f'{self.hall_times(cs, lang, links=mode == "links", on=self.sid(cnx) if cnx else None)}</div>')
                            if len(mine) > len(shown):
                                n = len(mine) - len(shown)
                                sched += (f'<a class="more" href="{P(lang, "film", fid)}">{f"و{n} سينما ثانية" if lang == "ar" else f"and {n} more cinemas"}</a>')
                            sched += '</div></details>'
                        return sched + '</div></section>'
                    graph0 = [{"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": self.theater_ld(c, lang)} for i, c in enumerate(cids)]}]
                    # the filter and sort sheets (posters_row) ride after the footer: counted here like the body
                    left = (CITY_TARGET - CHROME - len(body.encode()) - len("".join(self._sheets).encode()) - len(tk.encode()) - len(faq.encode())
                            - self.ld_size(graph0) - 600)
                    # digest0 (an extreme day: every cinema on its own line drops to a bare count) is the last
                    # resort under the 130 KB soft cap the busiest real day still has to clear (tests/test_build.py
                    # test_real_latest_at_its_busiest_stays_within_budget) — a fixed city page's board, hero, posters
                    # and cinemas list alone already run ~100 KB on a 58-film Dubai day, so even digest1 can overshoot
                    sched, _ = self.fit(city_sched, ("links", "plain", "compact", "digest3", "digest2", "digest1", "digest0"), left)
                    body += f'<div class="wrap split"><div class="main">{sched}{faq}</div>{tk}</div>'
                title = (f"سينما {cn} اليوم — الأفلام والأسعار وخصم فزعة" if lang == "ar" else f"{cn} cinemas today — films, prices and card discounts")
                names = ("، " if lang == "ar" else ", ").join(self.cname(c, lang) for c in cids[:6])
                desc = (f"أفلام سينمات {cn} اليوم ومواعيدها، سعر التذكرة لكل قاعة، والسعر بعد خصم فزعة وإسعاد والبنوك. {names}" if lang == "ar"
                        else f"Films and showtimes at {cn} cinemas today, ticket prices per hall, and the price after Fazaa, Esaad and bank cards. {names}")
                graph = [{"@type": "ItemList", "name": title, "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "item": self.theater_ld(cid, lang)} for i, cid in enumerate(cids)]},
                    self.breadcrumb_ld(lang, (cn, P(lang, city)))]
                self.page(lang, (city,), title, desc, body, graph, "city", attrs, nav="cinemas")

    def city_hero(self, city, cn, today, lang):
        """«دبي الليلة», the city's clock on 72 px flip tiles (the colon in seat grey), one pulse sentence and the
        pick's place. The clock and the sentence are the build's; places.js moves them on with the UAE clock."""
        wh = when_word(self.now, lang)
        t = self.now.strftime("%H:%M")
        tiles = "".join(f'<span class="c" aria-hidden="true">:</span>' if ch == ":" else f'<span class="d" aria-hidden="true">{ch}</span>' for ch in t)
        # «اختار لي في دبي» is the pick's (W2-P2b's pick.js binds [data-pick] and shows it); until then its place is held
        # invisible (visibility, so nothing moves when it arrives) and it is never a control that does nothing
        pick = (f'<button type="button" class="btn ghost pl-pick" data-pick="{esc(city)}" data-hold hidden>'
                f'{esc(L(PT["pick"], lang).format(city=cn))}</button>')
        return (f'<section class="head wrap chero">{self.crumbs(lang, (cn, None))}'
                f'<div class="ch-t"><h1 class="pt">{esc(L(PT["h1"], lang).format(city=cn, when=wh))}</h1>{pick}</div>'
                f'<p class="cclock" data-cclock dir="ltr"><span class="vh">{t}</span>{tiles}</p>'
                f'<p class="pulse" data-pulse aria-live="polite">{esc(self.pulse_text(today, cn, lang))}</p></section>')

    def pulse_text(self, today, cn, lang):
        """«214 عرض باقي الليلة، 38 تبدأ خلال ساعة» (places.js plPulse is the twin, from the city's slice)."""
        up = self.left_today(today)
        wh = when_word(self.now, lang)
        if not up: return L(T["now_none"], lang).format(city=cn)
        hm = self.now.strftime("%H:%M"); later = (self.now + dt.timedelta(hours=1)).strftime("%H:%M")
        soon = sum(1 for s in up if hm <= s["time"] <= later) if later > hm else sum(1 for s in up if s["time"] >= hm)
        return pulse_words(len(up), soon, wh, lang)

    def city_cinemas(self, city, cids, lang):
        """«السينمات»: each cinema's next start and how many are left today, «من 42» (gold only on the cheapest, lows()
        over [data-lo]); busiest first with no location, nearest first with one (near.js), a ♥ first from W3-P1."""
        order = sorted(cids, key=lambda c: (-len(self.left_today(self._by_cin.get(c, []))), self.cname(c, "en")))
        rows = ""
        for cid in order:
            c = self.cinemas[cid]; pr = self.cinema_prices(cid)
            # the lowest known price in any hall (an unpriced Standard hall must not hide a priced one)
            low = min(((a, h["code"], k, h["asof"]) for k, h in pr.items() for a in h["seats"].values()), default=None)
            rows += (f'<div class="row cin" data-cin="{esc(cid)}"{self.geo_attrs(c)}><a class="nm" href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a>'
                     f'<span class="sub"><span data-dist></span><span data-cnext>{esc(self.next_line(self._by_cin.get(cid, []), lang))}</span>{self.fresh(c["chain"], lang)}</span>'
                     f'<span class="from">{("من " if lang == "ar" else "from ") + self.pcell(low[0], c["chain"], low[1], low[2], cid, low[3], lang) if low else self.box(lang)}</span></div>')
        more = (f'<button type="button" class="more" data-cap-open aria-expanded="false" hidden>{esc(L(PT["all_cins"], lang))}</button>'
                if len(cids) > CIN_CAP else "")
        return (f'<section class="wrap cins" aria-labelledby="cins-h"><h2 id="cins-h">{esc(L(PT["cinemas"], lang))}</h2>'
                f'<div class="pl-cap" data-cap="{CIN_CAP}"><div class="rows" data-lo>{rows}</div>{more}</div></section>')

    def next_line(self, shows, lang):
        """«التالي 21:30، 18 عرض باقي» for a cinema today, or «ما في عروض باقية اليوم» (places.js plNext is the twin)."""
        up = self.left_today(shows)
        if not up: return L(PT["none_left"], lang).format(when=L(PT["today"], lang))
        return L(PT["next"], lang).format(t=up[0]["time"]) + ("، " if lang == "ar" else ", ") + left_words(len(up), lang)

    def film_summary(self, fid, fs, lang):
        """A film's line in «كل الأوقات»: its title (isolated, so a long Latin title loses its end, never its start),
        the next start and «من 42» (the list price; places.js reprices it after the card from the slice)."""
        up = self.left_today(fs)
        lo = self.list_min(up or fs)
        nx = f'<span class="nx num" data-nx>{esc(up[0]["time"]) if up else ""}</span>'
        fr = (f'<span class="fr" data-fr>{esc(L(HOME_T["from"], lang))} <span class="pv"><span class="num">{money(lo)}</span></span></span>' if lo else
              '<span class="fr" data-fr></span>')
        return f'<summary class="sf"><bdi class="t"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</bdi>{nx}{fr}</summary>'

    def hall_times(self, shows, lang, links=True, on=None):
        """One cinema's times on a city page, one run per hall with the hall named once in words (the old per-button
        tag spelled every hall's code: KIDS, PREMIER). Every button is Kit.tbtn's, show ids and all."""
        out = []
        for d in sorted({s["date"] for s in shows}):
            ds = sorted((s for s in shows if s["date"] == d), key=lambda s: s["time"])
            keys = sorted(dict.fromkeys(self.hkey(s) for s in ds), key=lambda k: k != "Standard")
            runs = []
            for k in keys:
                hs = [s for s in ds if self.hkey(s) == k]
                tag = "" if k == "Standard" else f'<small class="hn">{self.label_html(self.hall_name(hs[0], lang), lang)}</small>'
                runs.append(f'<span class="tr">{tag}' + "".join(self.tbtn(s, lang, links, False, on is not None and self.sid(s) == on) for s in hs) + '</span>')
            out.append(f'<div class="times" data-d="{d}">{"".join(runs)}</div>')
        return "".join(out)

    def city_faq(self, city, cn, cids, today, lang):
        """«كم سعر التذكرة في دبي الليلة؟ فيه خصم فزعة؟ وين أرخص IMAX؟», each answered only when the data can."""
        ar = lang == "ar"
        up = self.left_today(today)
        priced = [(p["aed"], s) for s in up for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
        qa = []
        wh = when_word(self.now, lang)
        if priced:
            lo, s1 = min(priced, key=lambda x: x[0]); hi, s2 = max(priced, key=lambda x: x[0])
            n1, n2 = say_name(self.cname(s1["cinema"], lang), lang), say_name(self.cname(s2["cinema"], lang), lang)
            h2 = self.hall_name(s2, lang)
            a = (f"أرخص تذكرة {wh} بـ{money(lo)} درهم في {esc(n1)}. أغلاها بـ{money(hi)} درهم، {self.label_html(h2, lang)} في {esc(n2)}. هذي الأسعار قبل خصم البطاقة."
                 if ar else f"The cheapest ticket {wh} is AED {money(lo)} at {esc(n1)}. The dearest is AED {money(hi)}, {esc(h2)} at {esc(n2)}. Prices before any card.")
            qa.append((f"كم سعر التذكرة في {cn} {wh}؟" if ar else f"How much is a cinema ticket in {cn} {wh}?", a))
        # Fazaa, chain by chain: where the card takes something off, and where we checked and it takes nothing
        chains = sorted({self.cinemas[c]["chain"] for c in cids}, key=lambda ch: self.h.chain_name(ch, lang))
        ok, no = [], []
        for ch in chains:
            st, r = self.fazaa(ch)
            if st == "ok": ok.append(f"في {self.h.chain_name(ch, lang)} {rule_offer(r, lang)}" if ar else f"{rule_offer(r, lang)} at {self.h.chain_name(ch, lang)}")
            elif st == "none_found": no.append(self.h.chain_name(ch, lang))
        if ok or no:
            a = ""
            if ok: a += (f"إيه، {'، و'.join(ok)}." if ar else f"Yes: {', '.join(ok)}.")
            if no: a += (" " if a else "") + (f"ما في خصم فزعة في {' و'.join(no)}." if ar else f"No Fazaa discount at {' or '.join(no)}.")
            qa.append((f"فيه خصم فزعة في {cn}؟" if ar else f"Is there a Fazaa discount in {cn}?", dates(esc(a))))
        imax = [(aed, s) for aed, s in priced if self.hkey(s) == "IMAX"]
        if imax:
            p, s = min(imax, key=lambda x: x[0])
            n = say_name(self.cname(s["cinema"], lang), lang)
            qa.append((f"وين أرخص IMAX في {cn}؟" if ar else f"Where is the cheapest IMAX in {cn}?",
                       f"أرخص IMAX {wh} بـ{money(p)} درهم في {esc(n)}." if ar else f"The cheapest IMAX {wh} is AED {money(p)} at {esc(n)}."))
        return self.faq_html(lang, qa)

    # -------------------------------------------------- cinema (the second flow: cinema → films → times → ticket)
    def cinema_pages(self):
        malls = load_malls()
        for cid, c in self.cinemas.items():
            city, chain = c.get("city"), c["chain"]
            pr = self.cinema_prices(cid)
            shows = self._by_cin.get(cid, [])
            nxt = self.next_show(shows)
            cfids = sorted({s["film"] for s in shows})
            for lang in ("ar", "en"):
                cn, name = L(CITY.get(city, (city, city)), lang), self.cname(cid, lang)
                body = self.cinema_head(cid, c, cn, name, lang, malls)
                body += self.slot("cinema.top", lang, cid=cid, city=city)   # the board's rows (W1-P1's slot, W2-P2); in the budget below
                body += f'<div class="wrap">{self.me(lang, city, "cinema")}</div>'
                body += '<div class="wrap split"><div class="main">'
                # «الليلة هنا», its one door: the filter sheet (the five rows of old controls are gone, MASTER-PLAN §2.4)
                here = ""
                if cfids:
                    self._sheets.append(self.filter_sheet(lang, cfids, prayer=True))
                    here = (f'<div class="sec-h here-h"><h2 id="here-h">{esc(L(PT["here"], lang))} <small>{esc(human_date(self.today, lang))}</small></h2>'
                            f'<button type="button" class="chip fchip js-only" data-sheet-open="sheet-filter">{icon("filter")}{esc(L(HOME_T["filter"], lang))}'
                            f'<b class="fbadge num" data-fcount hidden>0</b></button></div><p class="empty" data-empty hidden></p>')
                rest = self.halls_table(cid, chain, pr, lang)
                rest += self.slot("cinema.after_halls", lang, cid=cid)
                # cards (confirmed only)
                rows = ""
                for card in self.cards:
                    r = rule_for(self.rules, chain, card["id"]); st = rule_state(r, self.today)
                    if st == "unchecked": continue
                    rows += self.card_row(card, chain, r, st, lang, P(lang, "cards", card["id"]))
                if rows:
                    rest += f'<section><h2>{"البطاقات في " + self.h.chain_name(chain, lang) if lang == "ar" else "Cards at " + self.h.chain_name(chain, lang)}</h2><div class="rows">{rows}</div></section>'
                rest += self.cinema_faq(cid, chain, name, shows, pr, lang)
                rest += '</div>'
                tk = lambda n: (self.ticket(n, lang) if n else self.ticket_shell()) + '</div>'
                # films with their times, today then tomorrow — as richly as fits what the rest of the page leaves
                th0 = self.theater_ld(cid, lang)
                th0["event"] = [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:40]
                left = (PLACE_TARGET - CHROME - len(body.encode()) - len(here.encode()) - len((rest + tk(nxt)).encode())
                        - len("".join(self._sheets).encode()) - self.ld_size([th0]) - 600)
                sched, _ = self.fit(lambda m: self.cinema_schedule(shows, lang, m, self.sid(nxt) if nxt else None), ("full", "today", "plain", "compact"), left)
                on = nxt
                if not sched and any(s["date"] == self.today for s in shows):
                    # every time today has started and tomorrow's aren't listed yet: say when they come, no ticket
                    sched, on = f'<p class="hint">{L(TOMORROW_AT_CINEMA, lang)}</p>', None
                body += (f'<section class="here" aria-labelledby="here-h">{here}{sched}</section>' if here else sched) + rest + tk(on)
                title = (f"{name} — أسعار التذاكر ومواعيد اليوم وخصم البطاقات" if lang == "ar" else f"{name} — ticket prices, today’s showtimes and card discounts")
                desc = (f"مواعيد أفلام {name} اليوم، سعر التذكرة لكل قاعة وفئة، شو الفرق بين القاعات، والسعر بعد خصم فزعة وإسعاد والبنوك." if lang == "ar"
                        else f"Today’s showtimes at {name}, ticket prices per hall and seat class, what each hall offers, and the price after Fazaa, Esaad and bank cards.")
                th = self.theater_ld(cid, lang)
                th["event"] = [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:40]
                graph = [th, self.breadcrumb_ld(lang, (cn, P(lang, city)), (name, P(lang, city, cid)))]
                self.page(lang, (city, cid), title, desc, body, graph, "cinema",
                          f' data-city="{city}" data-chains="{chain}" data-cin="{esc(cid)}"', nav="cinemas")

    def cinema_head(self, cid, c, cn, name, lang, malls):
        """Breadcrumbs; the name (--fs-h1) with «سينمتي» held for W3-P1 (the bookmark, data-fav: hidden until me.js binds
        it, never a control that does nothing); the address in the page's language (cinemas.yaml address_ar, flagged
        for the owner's review there); Google Maps, Waze, Uber; «المول يسكّر 00:00» (malls.yaml: absent, never guessed)
        and the films that end after it; the chain's read time. near.js adds «تبعد عنك 3.1 كم» to .meta."""
        city, chain = c.get("city"), c["chain"]
        ar = lang == "ar"
        mark = ('<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true" '
                'focusable="false"><path d="M6 3h12v18l-6-4-6 4z"/></svg>')
        # «سينمتي» (round3-gaps: W3-P1 never shipped, so this stayed hidden): src/js/fav.js unhides it, keeps the pin
        # in cinema.me {cins} (the key filters.js's «وين: سينمتي» already reads) and swaps the label when pressed
        fav = (f'<button type="button" class="fav" data-fav="{esc(cid)}" data-city="{esc(city or "")}" aria-pressed="false" hidden'
               f' data-on="{esc(L(PT["mine"], lang))}" data-off="{esc(L(PT["pin"], lang))}">{mark}'
               f'<span class="fav-l">{esc(L(PT["pin"], lang))}</span></button>')
        photo = c.get("photo")
        bd = ""
        if isinstance(photo, dict) and photo.get("w1280") and photo.get("w640"):
            bd = (f'<div class="chead-bd" aria-hidden="true"><picture>'
                  f'<source media="(min-width:768px)" srcset="{esc(rel(photo["w1280"]))}">'
                  f'<img src="{esc(rel(photo["w640"]))}" alt="" loading="eager" fetchpriority="high" decoding="async" '
                  f'width="{photo.get("w") or 640}" height="{photo.get("h") or 360}"></picture></div>')
        out = (f'<section class="head wrap chead{" chead-photo" if bd else ""}">{bd}{self.crumbs(lang, (cn, P(lang, city)), (name, None))}'
               f'<div class="ch-t"><h1 class="pt"{" lang=\"en\"" if self.cname_is_en(cid, lang) else ""}>{esc(name)}</h1>{fav}</div>')
        a_ar = (self.names.get(cid) or {}).get("address_ar")
        a_en = c.get("address") or ("" if cid in self.names else c.get("mall")) or ""
        if ar and a_ar: out += f'<p class="ch-a">{esc(a_ar)}</p>'
        elif a_en: out += f'<p class="ch-a">{f"<bdi lang=\"en\">{esc(a_en)}</bdi>" if ar else esc(a_en)}</p>'
        out += self.travel(c, self.cname(cid, "en"), lang)
        meta = []
        _mid, mall = mall_for_cinema(malls, cid)
        close = close_minutes(mall, self.today) if mall else None
        if close is not None:
            hh, mm = divmod(close % 1440, 60)
            meta.append(f'<span class="closes">{esc(L(PT["closes"], lang).format(t=f"{hh:02d}:{mm:02d}"))}</span>')
        fr = self.fresh(chain, lang, always=True)
        if fr: meta.append(fr)
        out += f'<p class="meta">{"".join(meta)}</p>'
        if close is not None:
            late = shows_past_closing([s for s in self._by_cin.get(cid, []) if s["date"] == self.today], mall, self.today)
            if late:
                films = sorted({self.ftitle(s["film"], lang) for s in late})
                names = ("، " if ar else ", ").join(f"<bdi>{esc(t)}</bdi>" for t in films[:4])   # a Latin title in an Arabic line
                out += f'<p class="mall-late">{esc(L(PT["late"], lang)).replace("{films}", names)}</p>'
        bt = c.get("best_time")
        if isinstance(bt, dict) and bt.get("part") in BEST_TIME_PART:
            part = esc(L(BEST_TIME_PART[bt["part"]], lang))
            out += f'<p class="best-time">{esc(L(PT["best_time"], lang)).replace("{part}", part)}</p>'
        return out + '</section>'

    def halls_table(self, cid, chain, pr, lang):
        """«القاعات والأسعار» as one table: a hall's name heads its seats (halls.yaml labels), every seat priced before
        any card (the cells prices.js reprices), gold on the one cheapest (lows() lights one per table). What each
        hall is follows, folded; /halls/ compares them all."""
        ar = lang == "ar"
        body, what = "", ""
        for k, h in pr.items():
            e = self.h.match(chain, h["code"], h["label"])
            hn = self.label_html(hall_label(self, chain, h["code"], h["label"], lang), lang)
            seats = sorted(h["seats"].items(), key=lambda x: x[1])
            if seats:
                body += (f'<tbody><tr class="hh"><th colspan="2" scope="rowgroup">{hn}</th></tr>'
                         + "".join(f'<tr><th scope="row">{self.label_html(self.seat_name(seat), lang)}</th><td>{self.pcell(aed, chain, h["code"], k, cid, h["asof"], lang)}</td></tr>'
                                   for seat, aed in seats) + '</tbody>')
            else:
                body += f'<tbody><tr class="hh"><th scope="row">{hn}</th><td>{self.box(lang)}</td></tr></tbody>'
            w = (e.get("what_ar") if ar else e.get("what_en")) if e else ""
            if w:
                note = f' <small class="weak">{"ما تأكدنا من التفاصيل" if ar else "details not confirmed"}</small>' if e.get("confidence") == "low" else ""
                src = f' <a class="src" href="{esc(e["source"])}" rel="noopener" target="_blank">{"المصدر" if ar else "Source"}</a>' if e.get("source") else ""
                what += f'<dt>{hn}</dt><dd>{dates(esc(w))}{note}{src}</dd>'
        table = (f'<table class="prices hp"><thead><tr><th scope="col">{esc(L(PT["seat"], lang))}</th>'
                 f'<th scope="col">{esc(L(PT["price"], lang))} <small>{esc(L(T["aed"], lang))}</small></th></tr></thead>{body}</table>')
        what = f'<details class="hwhat"><summary>{esc(L(PT["what"], lang))}</summary><dl>{what}</dl></details>' if what else ""
        return (f'<section class="halls-s"><h2>{esc(L(PT["halls"], lang))}</h2>{table}{what}'
                f'<p class="hint"><a href="{P(lang, "halls")}">{esc(L(PT["halls_all"], lang))}</a></p></section>')

    def cinema_faq(self, cid, chain, name, shows, pr, lang):
        """«شو الأفلام اليوم في ريل دبي مول؟ كم سعر التذكرة؟ فيه خصم فزعة؟», answered from the data, as text."""
        ar = lang == "ar"
        nm = esc(say_name(name, lang))
        qa = []
        up = self.left_today(shows)
        fids = sorted({s["film"] for s in up}, key=lambda f: min(s["time"] for s in up if s["film"] == f))
        if fids:
            ts = [f"<bdi>{esc(self.ftitle(f, lang))}</bdi>" for f in fids]
            head = (ar_count(len(fids), FILMS_LEFT_AR) + " اليوم" if ar else f"{len(fids)} {'film' if len(fids) == 1 else 'films'} left today")
            lst = ("، " if ar else ", ").join(ts[:5]) + (("، وغيرها" if ar else ", and more") if len(ts) > 5 else "")
            qa.append((f"شو الأفلام اليوم في {nm}؟" if ar else f"What’s on today at {nm}?", f"{esc(head)}: {lst}."))
        priced = [(a, k, seat) for k, h in pr.items() for seat, a in h["seats"].items()]
        if priced:
            lo = min(priced, key=lambda x: x[0]); hi = max(priced, key=lambda x: x[0])
            hl = lambda k: self.label_html(hall_label(self, chain, pr[k]["code"], pr[k]["label"], lang), lang)
            if lo[0] == hi[0]:
                a = (f"التذكرة بـ{money(lo[0])} درهم. هذا السعر قبل خصم البطاقة." if ar else f"A ticket is AED {money(lo[0])}, before any card.")
            else:
                a = (f"أرخص تذكرة بـ{money(lo[0])} درهم في {hl(lo[1])}. أغلاها بـ{money(hi[0])} درهم في {hl(hi[1])}. هذي الأسعار قبل خصم البطاقة."
                     if ar else f"From AED {money(lo[0])} ({hl(lo[1])}) to AED {money(hi[0])} ({hl(hi[1])}), before any card.")
            qa.append((f"كم سعر التذكرة في {nm}؟" if ar else f"How much is a ticket at {nm}?", a))
        st, r = self.fazaa(chain)
        cn = self.h.chain_name(chain, lang)
        if st == "ok":
            terms = rule_terms(r, lang)
            a = (f"إيه، {rule_offer(r, lang)}" if ar else f"Yes, {rule_offer(r, lang)}") + (("، " if ar else ", ") + ("، " if ar else ", ").join(terms) if terms else "") + "."
            qa.append((f"فيه خصم فزعة في {cn}؟" if ar else f"Is there a Fazaa discount at {cn}?", dates(esc(a))))
        elif st == "none_found":
            qa.append((f"فيه خصم فزعة في {cn}؟" if ar else f"Is there a Fazaa discount at {cn}?",
                       esc(f"ما في خصم فزعة في {cn}." if ar else f"No Fazaa discount at {cn}.")))
        return self.faq_html(lang, qa)

    def cinema_schedule(self, shows, lang, mode, on=None):
        """The films at one cinema: poster, title, verdict, then each hall's time buttons. mode full = today +
        tomorrow with booking URLs; today = today only; plain = today, no booking URLs on the buttons.
        «الليلة هنا»: today's films sorted by their next start (those with nothing to come last), every hall in
        words; the times already started are the client's to fold (places.js, «+12 عرض فات»). Tomorrow folds."""
        out = []
        days = ((self.today, ("اليوم", "Today")), (self.tomorrow, ("بكرة", "Tomorrow")))
        hm = self.now.strftime("%H:%M")
        for day, lab in days[:2 if mode in ("full", "compact") else 1]:
            ds = self.live_halls([s for s in shows if s["date"] == day], lambda s: (s["film"], self.hkey(s)))
            if not ds: continue
            nxt = lambda f: min((s["time"] for s in ds if s["film"] == f and (day > self.today or s["time"] >= hm)), default="99:99")
            fids = sorted({s["film"] for s in ds}, key=lambda f: (nxt(f), -sum(1 for s in ds if s["film"] == f), self.ftitle(f, "en")))
            if day == self.today:
                out.append(f'<section class="day" data-d="{day}"><div class="cfilms">')
            else:
                out.append(f'<details class="day later" data-d="{day}"><summary><h2>{esc(L(lab, lang))} <small>{esc(human_date(day, lang))}</small></h2></summary><div class="cfilms">')
            for fid in fids:
                fs = [s for s in ds if s["film"] == fid]
                v, vw = self.vword(fid, lang)
                out.append(f'<div class="cf"{self.film_attrs(fid)} data-v="{v}"><a class="cf-p" href="{P(lang, "film", fid)}" tabindex="-1" aria-hidden="true">{self.poster(fid, lang, "pst sm")}</a>'
                           f'<div class="cf-b"><h3><a href="{P(lang, "film", fid)}"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</a></h3>'
                           f'<p class="cf-m"><span class="vw v-{v}">{esc(vw)}</span>{self.score(self.films[fid], lang)}</p>')
                for k in dict.fromkeys(self.hkey(s) for s in fs):
                    hs = [s for s in fs if self.hkey(s) == k]
                    out.append(f'<div class="hl" data-hall="{esc(hs[0].get("hall") or "OTHER")}" data-hk="{esc(k)}"><span class="hn">{self.label_html(self.hall_name(hs[0], lang), lang)}</span>'
                               + (self.times_compact(hs, lang, day_label=False) if mode == "compact" else
                                  self.times(hs, lang, links=mode != "plain", day_label=False, on=on)) + '</div>')
                out.append('</div></div>')
            out.append('</div></section>' if day == self.today else '</div></details>')
        if mode not in ("full", "compact"):
            out.append(f'<p class="hint">{L(TOMORROW_AT_CINEMA, lang)}</p>')
        return "".join(out)


def pulse_words(left, soon, when, lang):
    """«214 عرض باقي الليلة، 38 تبدأ خلال ساعة» / "214 shows left tonight, 38 start within the hour"; with none
    starting within the hour, the first half alone. places.js plPulse is the twin."""
    if lang == "en":
        s = f"{left} {'show' if left == 1 else 'shows'} left {when}"
        if soon: s += f", {soon} {'starts' if soon == 1 else 'start'} within the hour"
        return s
    s = f"{ar_count(left, LEFT_AR)} {when}"
    if soon: s += "، " + ("واحد منها يبدأ خلال ساعة" if soon == 1 else f"{soon} تبدأ خلال ساعة")
    return s
