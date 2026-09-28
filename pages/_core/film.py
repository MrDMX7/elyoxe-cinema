"""The film page: hero, day bar, schedule, ticket column, dock and tabs; the archived film (pages/core.py's film
family, moved as it was by W1-P1). Owner in Wave 2: W2-P3; W2-P1 the hero's picture (MASTER-PLAN §6.2).

Methods of pages.core.CorePages: `self` is a Pages, which reads everything else (self.page, self.poster,
self.shows ...) through to the site."""
from site_kit import *  # noqa: F401,F403  (the names these pages were written against)


class FilmPages:
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
                none = f'<p class="lead">{esc(L(FILM_T["none"], lang))}</p>'
                # «أقرب عرض لك» between the hero and the day bar (W1-P1's slot, W2-P2 fills it); it counts in the budget
                first = self.slot("film.first", lang, fid=fid)
                if not cities:
                    sched = none
                else:
                    # the schedule is most of the page's weight: render it as richly as fits what the rest leaves
                    bar0 = self.film_bar(lang, days); sheet0 = self._sheets.pop()   # measured (bar and its «⋯» sheet), drawn for real below
                    fixed = len((hero + first + tabs + bar0 + sheet0).encode())
                    # the ticket as it will be drawn (measured, where this used to reserve 4.5 KB), the page's wrappers
                    tk0 = len((self.ticket(nxt, lang) if nxt else self.ticket_shell()).encode())
                    left = PAGE_TARGET - CHROME - fixed - self.ld_size(graph) - tk0 - len((empty + dock).encode()) - 1200
                    # full, else compact: both keep today AND tomorrow (a page built late at night still has the next
                    # day's times when the visitor's «اليوم» has moved on)
                    sched, mode = self.fit(lambda m: self.film_schedule(shows, cities, lang, m, self.sid(nxt) if nxt else None), ("full", "compact"), left)
                    if mode not in ("full", "compact") and nxt and nxt["date"] != self.today: nxt = self.first_city_show([s for s in shows if s["date"] == self.today], cities) or nxt
                    # every hall's times have started and the next day isn't listed (a film's last night, after its
                    # last start): the page says so, as for a film with no shows, and holds no ticket for a started show
                    # (W0-P1 I1; the branch's cities are <details class="fcity[ here]">)
                    if 'class="fcity' not in sched: sched, nxt = none, None
                # a day button only for a day the schedule actually has
                days = [d for d in days if f'data-d="{d}"' in sched]
                bar = self.film_bar(lang, days) if cities and days else ""
                ticket = self.ticket(nxt, lang) if nxt else self.ticket_shell()
                body = (hero + first + f'<section class="fsched" id="times" aria-labelledby="times-h"><h2 class="vh" id="times-h">{esc(L(FILM_T["times"], lang))}</h2>'
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
        shows = self.live_halls([s for s in shows if s["date"] in {d for d, _ in days}], lambda s: (s["cinema"], self.hkey(s)))
        # Dubai (the script's default city) first, as the script will show it: no city moves above it at start-up (CLS)
        for city in sorted(cities, key=lambda c: c != "dubai"):
            cs = [s for s in shows if self.cinemas[s["cinema"]].get("city") == city]
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
                    hd = [(d, lab) for d, lab in days if any(s["date"] == d and not (mode == "compact" and self.is_past(s)) for s in hs)]
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
