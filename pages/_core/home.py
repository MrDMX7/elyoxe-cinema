"""Home: the page itself and its poster rows (pages/core.py's home family, moved as it was by W1-P1).
Owner in Wave 2: W2-P4 (rows and grid); W3-P1 and W4-P2 add their slot lines only (MASTER-PLAN §6.2).

Methods of pages.core.CorePages: `self` is a Pages, which reads everything else (self.page, self.poster,
self.shows ...) through to the site."""
import datetime as _dt
import re as _re

from site_kit import *  # noqa: F401,F403  (the names these pages were written against)

# the rows' words that are this package's (MASTER-PLAN §2.1; the dialect gate reviews them, §1.7)
ROW_T = {"cheap": ("أرخص عرض الليلة", "Cheapest show tonight"), "arabic": ("عربي وخليجي", "Arabic and Gulf"),
         "bollywood": ("بوليوود وجنوب الهند", "Bollywood and South India"),
         # the row's card door (§2.0, §2.1): with a card chosen home.js writes «بعد خصم فزعة» (CT after_card)
         "door": ("عندك بطاقة؟ شوف سعرك", "Got a card? See your price"),
         # §1.7: a failed city update keeps the server's prices and says so once
         "stale": ("ما قدرنا نحدّث الأوقات، هذي آخر نسخة من {t}", "Couldn’t refresh the times. This is the {t} copy.")}
N = 10          # tiles in a row
FIRST = 3       # a film already in an earlier row's first 3 slots starts at slot 4 or later (§2.1 de-duplication)
# insights' three links in the home.after_tonight slot (pages/insights.py home_links, untouched): r3-home 2026-09-30
# drops the «بالأرقام» row from home (owner call) — the paragraph is cut from the slot, and the links stay reachable
# from the footer (pages/insights.py's NavItems, kit/chrome.nav_links); the rest of the slot (the scores island, a
# seasonal banner) still passes through as it was.
NUMS = _re.compile(r'<section class="wrap insx"><p class="links more">(.*?)</p></section>', _re.S)
# a film's lead actor with a Wikimedia-licensed photo (People's own PHOTO check, pages/people.py, duplicated here to
# avoid importing the plugin: home.py only reads data["people"] and film["cast"], never People's page-building)
PHOTO = _re.compile(r"^/posters/people/[A-Za-z0-9._-]+\.webp$")


def dedupe(rows, first=FIRST):
    """[[fid…]…] in page order -> each row reordered so that no film sits in the first `first` slots of two rows: a
    row's first slots take its films not already up front in an earlier row, in its own order, and the rest follow in
    their order. A row with fewer than 4 films, or too few new ones to open with, comes back as None (not drawn).
    src/js/home.js lead() is its twin for the rows the script re-sorts for the visitor's city."""
    seen, out = set(), []
    for r in rows:
        fresh = [f for f in r if f not in seen]
        if len(r) < 4 or len(fresh) < first:
            out.append(None); continue
        head = fresh[:first]
        out.append(head + [f for f in r if f not in head])
        seen.update(head)
    return out


class HomePages:
    # ================================================================ pages
    def home(self):
        """The home page (UI redesign Task 3; MASTER-PLAN §2.1, reordered by r3-home 2026-09-30): the billboard, the
        board (W2-P2's home.after_bill slot), the Thursday band (W2-P7's home.after_board), the rows, «نجوم الليلة»,
        then «كل الأفلام» collapsed behind one button with the filter sheet inside it. «بالأرقام» is gone (strip_nums).
        The cities grid, the cards list and the chains' freshness live in the header's sheets, /cinemas/, /cards/ and
        /sources/ now."""
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
            # Wave 2's places on home (W1-P1): the board under the billboard, then the Thursday band (MASTER-PLAN §1.2 #2).
            # The near row «يبدأ قريب منك» that sat here is deleted (W2-P4): the board takes its place and carries id="now".
            # Until the board fills its slot, an empty anchor keeps the manifest's «الحين» shortcut (/#now) landing here
            body += self.slot("home.after_bill", lang) or '<div id="now"></div>'
            body += self.slot("home.after_board", lang)
            # a failed city update keeps the server's prices and says so, once (§1.7; home.js shows it, never .off tiles)
            body += f'<p class="stale-l wrap" data-stale hidden>{esc(L(ROW_T["stale"], lang).format(t=self.uae_now().strftime("%H:%M")))}</p>'
            body += self.home_rows(lang, films)
            body += self.strip_nums(self.slot("home.after_tonight", lang))
            body += self.stars_row(lang, films)
            body += self.posters_row(lang, films, self.shows, L(HOME_T["all_films"], lang), prayer=True, yes=True, collapse=True)
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
    def uae_now(self):
        """The build's own time on the UAE wall clock, naive."""
        n = self.now
        return n.astimezone(_dt.timezone(_dt.timedelta(hours=4))).replace(tzinfo=None) if n.tzinfo else n

    def night_shows(self, city="dubai"):
        """The shows still to start tonight in `city` at the build's time: from now to 03:00 (UAE cinemas run 00:30 and
        01:30 shows, dated the next day), in start order."""
        now = self.uae_now()
        end = _dt.datetime.combine(now.date() + _dt.timedelta(days=0 if now.hour < 3 else 1), _dt.time(3))
        out = []
        for s in self.shows:
            if self.cinemas[s["cinema"]].get("city") != city: continue
            try: at = _dt.datetime.fromisoformat(f'{s["date"]}T{s["time"]}')
            except ValueError: continue
            if now <= at < end: out.append((at, s))
        return [s for _, s in sorted(out, key=lambda x: x[0])]

    def cheap_shows(self, city="dubai"):
        """«أرخص عرض الليلة» (MASTER-PLAN §2.1, §4.2 #22): each film's cheapest show still to start tonight (the soonest
        of equal prices), cheapest first. It replaces «أرخص لك الليلة», whose 42, 42, 42 told no story: a show card
        says which time and where. The build draws Dubai's for the first paint; home.js redraws it for the visitor's
        city and card (renderCheap)."""
        best = {}
        for s in self.night_shows(city):
            pr = [p["aed"] for p in s.get("prices") or [] if p.get("aed") and p["aed"] > 0]
            if not pr: continue
            k = (min(pr), s["date"], s["time"])
            if s["film"] not in best or k < best[s["film"]][0]: best[s["film"]] = (k, s)
        return [s for _, s in sorted(best.values(), key=lambda x: (x[0], x[1]["film"]))]

    def family_fit(self, fid):
        """How well a film suits «العايلة» (the same scale as the pick's «مع منو» fit, MASTER-PLAN §3.1): a children's
        film, or animation or the family genre, 2; rated G or PG, 1; else (PG13) 0. Orders the «للعائلة» row."""
        f = self.films[fid]
        if film_flags(f)[1] or set(genre_keys(f)) & {"animation", "family"}: return 2
        return 1 if str(f.get("rating") or "").upper().replace(" ", "") in ("G", "PG") else 0

    def home_rows(self, lang, films):
        """The rows, in the spec's order (r3-home, owner reorder 2026-09-30; MASTER-PLAN §2.1 otherwise): the old
        separate «الأكثر عرضاً الليلة» row is gone — the billboard's slide 1 already carries it (pages/_core/bill.py
        bill_pick), so the row said the same thing twice. So: «الأعلى تقييماً» (renamed «يستاهل»), «أرخص عرض الليلة»
        (show cards), «للعائلة» (the «مع منو: العايلة» rule, kit/filters.who_fits, the best suited first), «قريباً في
        السينما» (renamed «نازل الخميس»; Sunday to Wednesday 18:00 — from then to Saturday the Thursday band, W2-P7,
        says it), «عربي وخليجي», «بوليوود وجنوب الهند» (pages/bollywood.py's languages). A film already in the first 3
        slots of an earlier row starts at slot 4 or later, and a row with fewer than 4 films (or too few new ones to
        open with) is not drawn. No tag repeats its row's name. «آخر فرصة» and the «آخر أسبوع» tags are deleted (§4.2
        #23: the data behind them flags every film older than 14 days). The heading is the link to «الكل»: a page, or
        «كل الأفلام» with the matching sort or filter chosen (?sort= / ?f= / ?who= / ?fl=, read by src/js/filters.js)."""
        home = P(lang)
        keys = {it.key for it in self.nav_items}
        from kit.filters import who_fits
        cheap = self.cheap_shows("dubai")
        by = {s["film"]: s for s in cheap}
        door = (f'<button type="button" class="lnk door" data-sheet-open="sheet-card" data-door="{esc(L(ROW_T["door"], lang))}">'
                f'{esc(L(ROW_T["door"], lang))}<span aria-hidden="true"> ▾</span></button>')
        family = sorted((f for f in films if "family" in who_fits(self.films[f]).split()), key=lambda f: -self.family_fit(f))
        from pages.bollywood import LANG_KEYS as BW_LANGS
        spec = [("yes", HOME_T["yes"], [f for f in films if (self.films[f].get("verdict") or {}).get("verdict") == "yes"],
                 home + "?f=yes#all", esc(L(HOME_T["yes_sub"], lang)), ""),
                ("cheap", ROW_T["cheap"], [s["film"] for s in cheap], home + "?sort=price#all", door, " data-rail-cheap"),
                ("family", HOME_T["family"], family, home + "?who=family#all", "", ""),
                ("arabic", ROW_T["arabic"], [f for f in films if str(self.films[f].get("lang") or "").lower() in ("arabic", "ar")],
                 P(lang, "arabic") if "arabic" in keys else home + "?fl=Arabic#all", "", ""),
                ("bollywood", ROW_T["bollywood"], [f for f in films if str(self.films[f].get("lang") or "").lower() in BW_LANGS],
                 P(lang, "bollywood") if "bollywood" in keys else home + "#all", "", "")]
        out = {}
        for (key, title, _, more, sub, attrs), o in zip(spec, dedupe([x[2] for x in spec])):
            if not o: continue
            if key == "cheap": tiles = "".join(self.show_card(by[f], lang) for f in o[:N])
            else: tiles = "".join(self.film_tile(f, lang, self.shows, row=True, live=True) for f in o[:N])
            out[key] = self.rail(lang, key, L(title, lang), tiles, sub=sub, more=more, attrs=attrs)
        coming = self.d.get("coming") or {}
        if coming and "thursday" in keys and self.week_phase(self.now) == "rest":
            from pages.coming import fold_near_duplicates
            items = sorted(fold_near_duplicates(coming), key=lambda kv: (not kv[1].get("release_date"), kv[1].get("release_date") or "", kv[1]["title"]))
            items = [(k, f) for k, f in items if not f.get("release_date") or f["release_date"] >= self.today]
            if len(items) >= 4:
                # no «الخميس» tag: the row is «قريباً في السينما», and each tile says its own date
                out["coming"] = self.rail(lang, "coming", L(HOME_T["coming"], lang), "".join(self.coming_tile(k, f, lang) for k, f in items[:N]),
                                          more=P(lang, "coming"))
        return "".join(out[k] for k in ("yes", "cheap", "family", "coming", "arabic", "bollywood") if k in out)

    def strip_nums(self, slot):
        """r3-home 2026-09-30 (owner call): the home.after_tonight slot's «بالأرقام» paragraph (insights' three links,
        /prices/, /boxoffice/, /q/) is cut from the home page — those pages stay reachable from the footer
        (pages/insights.py's NavItems, kit/chrome.nav_links). The rest of the slot (the scores island, a seasonal
        banner) still passes through as it was."""
        m = NUMS.search(slot)
        return slot[:m.start()] + slot[m.end():] if m else slot

    # -------------------------------------------------- home: «نجوم الليلة»
    def _lead(self, fid, lang, seen_q):
        """The first name in a film's cast with a real (Wikimedia-licensed) photo and a name, else None — a film with
        no such actor is skipped (owner rule), never filled with an initials box."""
        people = self.d.get("people") or {}
        for q in (self.films[fid].get("cast") or []):
            if not isinstance(q, str) or q in seen_q: continue
            p = people.get(q)
            if not isinstance(p, dict): continue
            ph = p.get("photo") or {}
            if not (PHOTO.match(str(ph.get("src") or "")) and PHOTO.match(str(ph.get("src2x") or ""))): continue
            nm = (p.get("name_ar") if lang == "ar" else p.get("name_en")) or p.get("name_en") or p.get("name_ar")
            if not nm: continue
            return q, ph, nm
        return None

    def star_tile(self, fid, ph, nm, lang):
        """One «نجوم الليلة» tile: a square (no radius, the workspace rule) portrait, the actor's name, the film's
        title under it. It links to the film (not the person page): a pick here is a way into tonight's show, not a
        detour to a filmography."""
        return (f'<a class="tile star" href="{P(lang, "film", fid)}">'
                f'<span class="tp"><img src="{esc(ph["src"])}" srcset="{esc(ph["src"])} 160w, {esc(ph["src2x"])} 320w" sizes="120px"'
                f' width="160" height="160" alt="" loading="lazy" decoding="async"></span>'
                f'<span class="t">{esc(nm)}</span><span class="m">{esc(self.ftitle(fid, lang))}</span></a>')

    def stars_row(self, lang, films):
        """«نجوم الليلة» (r3-home, owner idea 2026-09-30): the lead actor of tonight's most-shown film, then of its
        top-rated («الأعلى تقييماً») film — each only when they have a real photo (self._lead skips a film without
        one, moving to the next candidate rather than falling back to initials). Sits right before «كل الأفلام», the
        row's own doorway into the grid."""
        if not films: return ""
        yes = [f for f in films if (self.films[f].get("verdict") or {}).get("verdict") == "yes"]
        seen_f, seen_q, picks = set(), set(), []
        for pool in (films, yes):
            for fid in pool:
                if fid in seen_f: continue
                lead = self._lead(fid, lang, seen_q)
                if not lead: continue
                q, ph, nm = lead
                seen_f.add(fid); seen_q.add(q)
                picks.append((fid, ph, nm))
                break
        if not picks: return ""
        tiles = "".join(self.star_tile(fid, ph, nm, lang) for fid, ph, nm in picks)
        return self.rail(lang, "stars", L(HOME_T["stars"], lang), tiles)
