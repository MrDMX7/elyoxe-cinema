"""«الشاشة», home's billboard (W2-P1; MASTER-PLAN §2.1, §1.6, §1.3). Owner in Wave 2: W2-P1 (MASTER-PLAN §6.2).

One billboard for every visitor, whatever their city: slide 1 is the UAE's most-shown film tonight under the city-free
eyebrow «الأكثر عرضاً الليلة» (the server can't know a first visitor's city before paint; the city's own answer is the
board under it), and nothing on it changes after paint except by the visitor's own hand (a swipe, a card). The other
slides are films of the country's top 10 that have a trailer frame and are not «تجنّبه» (never promoted); from
Wednesday 18:00 to Saturday a new release may take slide 2. Every slide is written here, so a phone swipes a CSS
scroll-snap strip and a desktop cross-fades them (src/js/bill.js); only slide 1's picture loads with the page.

Methods of pages.core.CorePages: `self` is a Pages, which reads everything else (self.page, self.screen, self.shows
...) through to the site."""
import datetime as dt

from site_kit import *  # noqa: F401,F403  (the names these pages were written against)

# the billboard's own words (the voice table, MASTER-PLAN §1.7; the dialect gate reviews them in W4)
BILL_T = {
    "top": ("الأكثر عرضاً الليلة", "Most shown tonight"),
    "on": ("يعرض الليلة", "Showing tonight"),
    "new": ("جديد هالخميس", "New this Thursday"),
    "eve": ("بكرة ينزل", "Opens tomorrow"),
    "times": ("الأوقات", "Times"),                       # slide 1 when it is «تجنّبه»: honest, and no price on it
    "unknown": ("الحكم بعده", "No verdict yet"),          # §1.7: the single short line, no body text
    "door_no": ("عندك بطاقة؟ شوف سعرك", "Got a card? See your price"),
    "door_yes": ("السعر بعد خصم {card}", "Price after {card}"),
    "door_not": ("ما في خصم {card} في {chain}", "No {card} discount at {chain}"),
    "slide": ("شريحة", "slide"),
    "of": ("{i} من {n}", "{i} of {n}"),
}
PLAY = '<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>'


class BillPages:
    BILL_N = 5   # slides at most

    # -------------------------------------------------- which films
    def bill_pick(self, ranked):
        """The slides from films ranked by tonight's shows: the first as it is, whatever its verdict (its eyebrow and
        its verdict line say so), then the films of the top 10 that have a trailer frame and are not «تجنّبه»."""
        if not ranked: return []
        ok = lambda f: self.frame(f) is not None and self.vcode(f) != "skip"
        return (ranked[:1] + [f for f in ranked[1:10] if ok(f)])[:self.BILL_N]

    def vcode(self, fid):
        return (self.films[fid].get("verdict") or {}).get("verdict") or "unknown"

    def bill_new(self, ranked):
        """Wed 18:00 to Sat (Kit.week_phase): (fid, eyebrow key) of a new release that may take slide 2, else None.
        Wednesday evening: a film that opens tomorrow and already has shows («بكرة ينزل»); Thursday to Saturday: a film
        released since this Thursday with shows today («جديد هالخميس»). The most shown of them, never «تجنّبه»."""
        phase = self.week_phase(self.now)
        if phase == "rest": return None
        day = self.now.date()
        if phase == "wed-eve":
            want, key = {(day + dt.timedelta(days=1)).isoformat()}, "eve"
            count = lambda f: len(self._by_film.get(f, []))
        else:
            thu = day - dt.timedelta(days=day.weekday() - 3)
            want, key = {(thu + dt.timedelta(days=i)).isoformat() for i in range((day - thu).days + 1)}, "new"
            count = lambda f: self.today_count.get(f, 0)
        coming = self.d.get("coming") if isinstance(self.d.get("coming"), dict) else {}
        rel = lambda f: self.films[f].get("released") or (coming.get(f) or {}).get("release_date")
        new = [f for f in self.showing if rel(f) in want and count(f) > 0 and self.vcode(f) != "skip"]
        new.sort(key=lambda f: (-count(f), f))
        return (new[0], key) if new else None

    def bill_slides(self, ranked):
        """[(fid, eyebrow key)]: slide 1 «top», then the calendar's new release (Wed 18:00 to Sat), then «on»."""
        pick = self.bill_pick(ranked)
        if not pick: return []
        out = [(pick[0], "top")]
        nw = self.bill_new(ranked)
        if nw and nw[0] != pick[0]: out.append(nw)
        out += [(f, "on") for f in pick[1:] if not (nw and f == nw[0])]
        return out[:self.BILL_N]

    # -------------------------------------------------- what each slide says
    def bill_facts(self, fid, lang):
        """The desktop's facts line, each its own span (no dots): the critics' (or audience's) score, the runtime,
        the rating when the score did not already take its place, two genres. A phone has none (§2.1)."""
        f = self.films[fid]; rt = f.get("rt") or {}
        out = [self.score(f, lang)]
        if f.get("runtime"): out.append(f'{num(f["runtime"])} {L(HOME_T["min"], lang)}')
        if f.get("rating") and (rt.get("critics") is not None or rt.get("audience") is not None):
            out.append(f'<bdi class="num" dir="ltr">{esc(f["rating"])}</bdi>')
        g = genre_words(f.get("genres"), lang)[:2]
        if g: out.append(esc(("، " if lang == "ar" else ", ").join(g)))
        return [x for x in out if x]

    def bill_price(self, fid, lang):
        """The film's cheapest ticket in the whole country among the shows still to come when the page was built (today's,
        else tomorrow's), as a price cell the visitor's card reprices (prices.js); None when nothing is priced. The same
        for every visitor: the city-specific answer is the board's."""
        up = [s for s in self._by_film.get(fid, []) if not self.is_past(s)]
        for d in (self.today, self.tomorrow):
            mc = self.min_cell([s for s in up if s["date"] == d], lang)
            if mc: return mc[0]
        return None

    def bill_slide(self, i, n, fid, eye, lang):
        """One slide: the screen (Kit.screen: the frame, or the lit case), then the words — eyebrow, the title by its
        length, the verdict word opening its sentence, the desktop's facts, the velvet «الأوقات والأسعار من 42» and the
        icon-only trailer button. Slide 1's picture loads with the page; the others' wait for src/js/bill.js."""
        f = self.films[fid]; v = self.vcode(fid); ar = lang == "ar"
        sc = self.screen(fid, lang, first=i == 0)
        if i == 0 and sc["preload"]: self.site._preload = sc["preload"]
        h = P(lang, "film", fid); t = self.ftitle(fid, lang)
        vd = f.get("verdict") or {}; say = (vd.get("ar") if ar else vd.get("en")) if v != "unknown" else None
        word = L(BILL_T["unknown"], lang) if v == "unknown" else L(VERDICT[v], lang)
        verdict = (f'<p class="bill-v"><b class="v-{v}">{esc(word)}{"." if say else ""}</b>'
                   + (f" {dates(esc(say))}" if say else "") + "</p>")
        cell = None if v == "skip" and i == 0 else self.bill_price(fid, lang)
        go = (f'{esc(L(HOME_T["times"], lang))} <span class="from">{esc(L(HOME_T["from"], lang))} {cell}</span>' if cell
              else esc(L(BILL_T["times"] if v == "skip" and i == 0 else HOME_T["times"], lang)))
        tr = f.get("trailer")
        trailer = (f'<a class="btn ghost bill-tr" href="https://www.youtube-nocookie.com/embed/{esc(tr)}" data-trailer="{esc(tr)}" rel="noopener"'
                   f' target="_blank" aria-label="{esc(L(HOME_T["trailer"], lang))}">{PLAY}<span class="tr-w" aria-hidden="true">{esc(L(HOME_T["trailer"], lang))}</span></a>'
                   if tr else "")
        facts = "".join(f"<span>{x}</span>" for x in self.bill_facts(fid, lang))
        spill = f' data-spill="{";".join(sc["spill"])}"' if sc["spill"] else ""
        label = L(BILL_T["of"], lang).format(i=i + 1, n=n)
        return (f'<div class="slide {sc["kind"]}{" on" if i == 0 else ""}" role="group" aria-roledescription="{esc(L(BILL_T["slide"], lang))}"'
                f' aria-label="{esc(label)}"{spill}>{sc["layer"]}<div class="trk">{sc["case"]}</div>'
                f'<div class="bill-in"><p class="eyebrow">{esc(L(BILL_T[eye], lang))}</p>'
                f'<h2 class="bill-t" style="--tsize:{self.tsize(t)}px"><a href="{h}"{self.title_attr(fid, lang)}>{esc(t)}</a></h2>'
                f'{verdict}' + (f'<p class="bill-f">{facts}</p>' if facts else "")
                + f'<p class="cta"><a class="btn velvet bill-go" href="{h}">{go}</a>{trailer}</p></div></div>')

    # -------------------------------------------------- the billboard
    def billboard(self, lang, tops, today):
        """Home's first screen: every slide, the card door (the screen's one door, next to its first price) with the
        indicators at its inline end, the desktop's pause, and the screen's spill. `tops["*"]` ranks the country's
        films by tonight's shows (pages/_core/home.py); the cities' lists are not read (one billboard for everyone)."""
        ranked = [f for f in (tops.get("*") or []) if f in self.films]
        if not ranked: return ""
        slides = self.bill_slides(ranked)
        n = len(slides)
        body = "".join(self.bill_slide(i, n, fid, eye, lang) for i, (fid, eye) in enumerate(slides))
        dots = "".join(f'<button type="button" aria-label="{esc(self.ftitle(fid, lang))}" aria-pressed="{"true" if i == 0 else "false"}"><i></i></button>'
                       for i, (fid, _) in enumerate(slides)) if n > 1 else ""
        door = (f'<a class="door js-only" href="{P(lang, "cards")}" data-sheet-open="sheet-card" data-bill-door'
                f' data-no="{esc(L(BILL_T["door_no"], lang))}" data-yes="{esc(L(BILL_T["door_yes"], lang))}" data-not="{esc(L(BILL_T["door_not"], lang))}">'
                f'<span data-door-t>{esc(L(BILL_T["door_no"], lang))}</span> ▾</a>')
        nav = ("" if n < 2 else
               f'<div class="bill-nav js-only"><button type="button" class="bill-pp" data-bill-pp aria-pressed="false">'
               f'<span class="vh">{esc(L(HOME_T["pause"], lang))}</span></button>'
               f'<div class="dots" data-bill-dots role="group" aria-label="{esc(L(HOME_T["slides"], lang))}">{dots}</div></div>')
        # the screen's spill: slide 1's frame colours, written here so the first paint has them (bill.js follows a swipe)
        sp = (self.frame(slides[0][0]) or {}).get("spill")
        spill = (' data-spill style="' + "".join(f"--sp{k + 1}:{c};" for k, c in enumerate(sp)) + '"') if sp else ""
        return (f'<section class="bill" data-bill aria-roledescription="{"عرض" if lang == "ar" else "carousel"}" aria-label="{esc(L(HOME_T["slides"], lang))}"'
                f'{spill}><div class="bill-s" data-bill-s>{body}</div>'
                f'<div class="bill-foot">{door}{nav}</div><i class="bill-spill" aria-hidden="true"></i></section>')
