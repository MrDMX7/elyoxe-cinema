"""Data insights (phase 2, D): /prices/ — the price index per chain and hall today, the history chart once 30
days exist (inline SVG + the same numbers as a table), «زاد/نقص» over 30 days, and «أرخص وقت بالأسبوع» once 14
days exist (hidden before); /boxoffice/ — «الأكثر عرضاً هالأسبوع» by show and cinema count (not tickets, and
the page says so); /data/compare.json + the lazy chunk compare.js (two films side by side, on film pages and
/boxoffice/); «شي يشبه» on a showing film's page (similar.py).

History: price_history.jsonl (steps/history.py writes it on the runner; CINEMA_PRICE_HISTORY overrides the
path). The build never needs it: with none, the pages show today only.

W0-P2 (MASTER-PLAN §4.1 #17, #18, #20, #37): /prices/ is dated the day it was read (a late-night index built from
tomorrow's shows says so instead of carrying tomorrow's date) and its table is two columns on a phone; compare
reads the next times from the city's own day slices on the client (compare.json kept six per city from the build,
so after about 21:30 every film had «ما في عروض باقية»), drops the IMDb row (no OMDb key: always empty), and
takes critics and audience from the same place the film page does (film_rates)."""
import datetime as dt
import os
import re

import price_history as ph
import similar as simmod
from site_kit import (SITE, L, P, Page, Pages, Plugin, after, ar_count, esc, genre_label, human_date,
                      lang_words, money, num)

CSS = ("insights",)
LAZY_JS = ("compare",)
JS = ("cmpload",)          # a few bytes: loads compare.js where a [data-cmp] box is (never on archived film pages)
DIRS = ("prices", "boxoffice")
PRICES = ("أسعار التذاكر", "Ticket prices")
BOX = ("الأكثر عرضاً", "Most shown")
CHART_DAYS, TIME_DAYS = 30, 14
DAYS_AR = ("الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
DAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
PART = {"morning": ("الصبح (قبل 12)", "morning (before 12)"), "afternoon": ("الظهر والعصر (12 إلى 5)", "afternoon (12 to 5)"),
        "evening": ("المسا (5 إلى 9)", "evening (5 to 9)"), "night": ("الليل (بعد 9)", "night (after 9)")}
AED = ("درهم", "AED")
QID = re.compile(r"^Q[0-9]+$")
DAYS = ("يوم واحد", "يومين", "أيام", "يوم")
# the verdict's basis, when a film has no rt block: «RT 96% (249 ناقد)، الجمهور 91%» (pages/core.py film_pages)
BASIS_RATES = (("critics", re.compile(r"\bRT (\d{1,3})%")), ("audience", re.compile(r"(?:الجمهور|[Aa]udience) (\d{1,3})%")))


def film_rates(f):
    """(critics, audience) exactly as the film page prints them: the rt block's numbers, else — only when the rt
    block has neither — the ones the verdict's basis carries. None where there is no number."""
    rt = f.get("rt") or {}
    got = {k: rt.get(k) for k in ("critics", "audience")}
    if got["critics"] is None and got["audience"] is None:
        basis = str((f.get("verdict") or {}).get("basis") or "")
        for k, rx in BASIS_RATES:
            m = rx.search(basis)
            if m: got[k] = int(m.group(1))
    return got["critics"], got["audience"]


history_path = ph.history_path


def register(site):
    ins = Insights(site)
    pages = [Page(("prices",), lang, lambda lang=lang: ins.prices(lang)) for lang in ("ar", "en")]
    pages += [Page(("boxoffice",), lang, lambda lang=lang: ins.boxoffice(lang)) for lang in ("ar", "en")]
    return Plugin(pages=pages, data={"data/compare.json": ins.compare_data},
                  slots={"film.info": ins.film_slot, "home.after_tonight": ins.home_links})


class Insights(Pages):
    def __init__(self, site):
        super().__init__(site)
        today = {"generated": self.d.get("generated"), "shows": self.shows, "cinemas": self.cinemas, "films": self.films}
        self.now_snap = ph.snapshot(today, self.h)
        self.hist = {d: v for d, v in ph.load(history_path()).items() if d < self.today}   # the past, as it was read
        self.all, _ = ph.merge(self.hist, self.now_snap)
        # the index is the fullest read from today on: a late-night run holds a few of today's shows and all of
        # tomorrow's, and a handful of shows is not «today's price»
        ahead = [d for d in sorted(self.now_snap) if d >= self.today and self.now_snap[d]["priced"]]
        self.idx_date = max(ahead, key=lambda d: (self.now_snap[d]["priced"], d == self.today)) if ahead else None
        # history readings: the past as recorded, plus the index day (a thin «today» stays out of the chart)
        self.full = self.all                    # the box office counts every date's schedule
        self.all = {d: v for d, v in self.all.items() if d < self.today or d == self.idx_date}
        self.hall_names = {}
        for s in self.shows:
            k = (self.cinemas[s["cinema"]]["chain"], self.hkey(s))
            if k not in self.hall_names: self.hall_names[k] = (self.hname(s, "ar"), self.hname(s, "en"))
        self._sim, self._pages = {}, None

    # -------------------------------------------------- helpers
    def aed(self, x, lang):
        return f'{num(money(x))} <small>{esc(L(AED, lang))}</small>'

    @staticmethod
    def count(n, ar_forms, en_forms, lang):
        """«88 عرض» / «عرضين» with the number in its own span; English "88 shows"."""
        if lang == "ar":
            t = ar_count(n, ar_forms)
            return t.replace(str(n), f'<span class="num">{n}</span>', 1) if str(n) in t else esc(t)
        return f'<span class="num">{n}</span> {en_forms[0] if n == 1 else en_forms[1]}'

    def chain(self, ch, lang):
        return self.h.chain_name(ch, lang)

    def hall(self, ch, key, lang):
        n = self.hall_names.get((ch, key))
        if n: return L(n, lang)
        return ("عادية" if lang == "ar" else "Standard") if key == "Standard" else key

    def head(self, lang, name, h1, lead):
        return (f'<section class="head wrap">{self.crumbs(lang, (L(name, lang), None))}<h1 class="pt">{esc(h1)}</h1>'
                f'<p class="lead">{lead}</p></section>')

    # -------------------------------------------------- /prices/
    def prices(self, lang):
        ar = lang == "ar"
        body = self.head(lang, PRICES, "أسعار تذاكر السينما في الإمارات" if ar else "Cinema ticket prices in the UAE",
                         esc("كم تدفع لكل سلسلة ولكل قاعة، من أنظمة الحجز نفسها، وكيف يتحرك السعر مع الأيام." if ar
                             else "What each chain charges per hall, read from their own booking systems, and how it moves over time."))
        body += self.index_section(lang)
        body += self.history_section(lang)
        body += self.time_section(lang)
        # the day the prices were read (the build's own day), even when a late-night index is built from tomorrow's
        # shows (index_section says so); and the chains it has
        day = human_date(self.today, lang) if self.idx_date else None
        names = sorted({self.chain(r[0], lang) for r in (self.now_snap[self.idx_date]["prices"] if self.idx_date else [])})
        names = ("، ".join(names[:-1]) + " و" + names[-1] if len(names) > 1 else "".join(names)) if ar else                 (", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names))
        title = ((f"أسعار تذاكر السينما في الإمارات، {day} — لكل سلسلة وقاعة" if day else "أسعار تذاكر السينما في الإمارات — لكل سلسلة وقاعة") if ar
                 else (f"UAE cinema ticket prices, {day} — per chain and hall" if day else "UAE cinema ticket prices — per chain and hall"))
        desc = ((f"وسيط سعر التذكرة في {names}، لكل قاعة، من أنظمة الحجز نفسها. آخر تحديث {day}." if day else "أسعار تذاكر السينما في الإمارات من أنظمة الحجز نفسها.") if ar
                else (f"The median ticket price at {names}, per hall, from their own booking systems. Updated {day}." if day else "UAE cinema ticket prices from the chains' own booking systems."))
        return {"title": title, "desc": desc, "body": body, "kind": "prices", "nav": "prices",
                "graph": [self.breadcrumb_ld(lang, (L(PRICES, lang), P(lang, "prices")))]}

    def index_section(self, lang):
        ar = lang == "ar"
        if not self.idx_date:
            return (f'<section class="wrap"><p class="hint">{"ما قرينا أسعار لأي عرض في هالتحديث. السعر في الشباك." if ar else "We could not read a price for any show in this refresh. Prices at the box office."}</p></section>')
        line = self.now_snap[self.idx_date]
        rows = [r for r in line["prices"] if r[2] == ""]
        chains = sorted({r[0] for r in rows}, key=lambda c: self.chain(c, lang))
        # the chain is a row of its own over its halls, so a phone keeps two columns (hall, median) and hides the rest
        th = ("القاعة", "الوسيط", "أرخص", "أغلى", "العروض") if ar else ("Hall", "Median", "Lowest", "Highest", "Shows")
        tb = ""
        for ch in chains:
            rs = sorted((r for r in rows if r[0] == ch), key=lambda r: (r[1] != "Standard", r[3]))
            tb += f'<tr class="pi-ch"><th colspan="{len(th)}" scope="colgroup">{esc(self.chain(ch, lang))}</th></tr>'
            for _, key, _, med, lo, hi, n in rs:
                tb += (f'<tr data-k="{esc(ch)}|{esc(key)}"><th scope="row"><bdi>{esc(self.hall(ch, key, lang))}</bdi></th>'
                       f'<td><b>{num(money(med))}</b></td><td>{num(money(lo))}</td><td>{num(money(hi))}</td><td>{num(n)}</td></tr>')
        when = human_date(self.today, lang)   # the day we read them
        hint = ("الرقم هو الوسيط لسعر أرخص مقعد في كل عرض قريناه من نظام حجز السينما، بالدرهم وقبل أي خصم بطاقة. نصف العروض أرخص منه ونصفها أغلى." if ar
                else "The median of the cheapest seat of every show we read from the chain's booking system, in AED before any card discount: half the shows cost less, half more.")
        if self.idx_date != self.today:   # a late-night read: most of tonight's shows are over, so tomorrow's make the index
            hint += (" الأرقام من عروض بكرة." if ar else " The numbers are from tomorrow’s shows.") if self.idx_date == self.tomorrow else \
                    (f" الأرقام من عروض {human_date(self.idx_date, lang)}." if ar else f" The numbers are from the shows of {human_date(self.idx_date, lang)}.")
        return (f'<section class="wrap pi"><h2>{("مؤشر الأسعار، " + when) if ar else "Price index, " + when}</h2>'
                f'<p class="hint">{esc(hint)}</p>'
                f'<div class="xwrap"><table class="matrix pidx"><thead><tr>{"".join(f"<th>{esc(x)}</th>" for x in th)}</tr></thead>'
                f'<tbody>{tb}</tbody></table></div>'
                f'<p class="links more"><a href="{P(lang, "halls")}">{"شو الفرق بين القاعات؟" if ar else "What is in each hall?"}</a> '
                f'<a href="{P(lang, "cards")}">{"السعر بعد خصم بطاقتك" if ar else "The price after your card"}</a></p></section>')

    def std_series(self):
        """{chain: [(date, median, n)]} Standard hall, whole UAE, over the history + today."""
        chains = sorted({r[0] for d in self.all.values() for r in d["prices"] if r[1] == "Standard" and r[2] == ""})
        return {ch: ph.series(self.all, ch, "Standard", "", upto=self.idx_date or self.today) for ch in chains}

    def history_section(self, lang):
        ar = lang == "ar"
        n = len(ph.days(self.all, self.idx_date or self.today))
        if n < CHART_DAYS:
            if not n: return ""
            first = human_date(min(ph.days(self.all, self.idx_date or self.today)[0], self.today), lang)   # never a day not yet come
            say = (f"نسجّل الأسعار من {first}، وعندنا الحين أسعار {ar_count(n, DAYS)}. الرسم وتغيّر السعر يطلعون هني لما يصير عندنا {CHART_DAYS} يوم."
                   if ar else f"We have recorded prices since {first}: {n} day{'s' if n != 1 else ''} so far. The chart and the 30-day change appear here once there are {CHART_DAYS}.")
            return f'<section class="wrap"><p class="hint hist-n">{esc(say)}</p></section>'
        ser = {ch: s for ch, s in self.std_series().items() if len(s) >= 2}
        if not ser: return ""
        dates = sorted({d for s in ser.values() for d, _, _ in s})[-180:]
        body = f'<section class="wrap ph"><h2>{"سعر القاعة العادية مع الأيام" if ar else "The regular hall's price over time"}</h2>'
        body += self.chart(ser, dates, lang) + self.changes(ser, lang) + self.chart_table(ser, dates, lang)
        return body + '</section>'

    def chart(self, ser, dates, lang):
        ar = lang == "ar"
        W, H, pl, pr, pt, pb = 640, 260, 44, 110, 14, 26
        vals = [m for s in ser.values() for d, m, _ in s if d in dates]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1: lo, hi = lo - 1, hi + 1
        ix = {d: i for i, d in enumerate(dates)}
        x = lambda d: pl + (W - pl - pr) * (ix[d] / max(1, len(dates) - 1))
        y = lambda v: pt + (H - pt - pb) * (1 - (v - lo) / (hi - lo))
        dash = ("", "6 4", "2 4", "10 3 2 3", "1 3", "8 8", "4 2")
        lines, labels = "", []
        for i, (ch, s) in enumerate(sorted(ser.items(), key=lambda kv: -kv[1][-1][1])):
            pts = [(x(d), y(m)) for d, m, _ in s if d in ix]
            if len(pts) < 2: continue
            da = f' stroke-dasharray="{dash[i % len(dash)]}"' if dash[i % len(dash)] else ""
            lines += f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" class="ln"{da}/>'
            labels.append([pts[-1][1], ch, s[-1][1]])
        labels.sort()
        for j in range(1, len(labels)):                     # direct labels, nudged apart
            labels[j][0] = max(labels[j][0], labels[j - 1][0] + 13)
        for yy, ch, v in labels:
            lines += f'<text x="{W - pr + 6}" y="{yy + 4:.1f}" class="lb">{esc(self.chain(ch, lang))} {money(v)}</text>'
        axis = (f'<text x="{pl - 6}" y="{y(hi) + 4:.1f}" class="ax" text-anchor="end">{money(hi)}</text>'
                f'<text x="{pl - 6}" y="{y(lo) + 4:.1f}" class="ax" text-anchor="end">{money(lo)}</text>'
                f'<line x1="{pl}" y1="{H - pb}" x2="{W - pr}" y2="{H - pb}" class="base"/>'
                f'<text x="{pl}" y="{H - 6}" class="ax">{dates[0]}</text>'
                f'<text x="{W - pr}" y="{H - 6}" class="ax" text-anchor="end">{dates[-1]}</text>')
        t = ("وسيط سعر أرخص مقعد في القاعة العادية لكل سلسلة، بالدرهم" if ar else "Median cheapest-seat price in the regular hall per chain, AED")
        dsc = (f"من {dates[0]} إلى {dates[-1]}. نفس الأرقام في الجدول تحت." if ar else f"From {dates[0]} to {dates[-1]}. The same numbers are in the table below.")
        return (f'<figure class="chart" dir="ltr"><svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="ch-t ch-d" preserveAspectRatio="xMidYMid meet">'
                f'<title id="ch-t">{esc(t)}</title><desc id="ch-d">{esc(dsc)}</desc>{axis}{lines}</svg>'
                f'<figcaption dir="{"rtl" if ar else "ltr"}">{esc(t)}</figcaption></figure>')

    def changes(self, ser, lang):
        """«زاد/نقص» per chain: the last day against the nearest day at least 30 days before it."""
        ar = lang == "ar"
        out = []
        for ch, s in sorted(ser.items(), key=lambda kv: self.chain(kv[0], lang)):
            last_d, last, _ = s[-1]
            cut = (dt.date.fromisoformat(last_d) - dt.timedelta(days=CHART_DAYS)).isoformat()
            before = [x for x in s if x[0] <= cut]
            if not before: continue
            d0, v0, _ = before[-1]
            diff = round(last - v0, 2)
            if abs(diff) < 0.01:
                say = f"ما تغيّر ({num(money(last))})" if ar else f"unchanged ({num(money(last))})"
            elif ar:
                say = f'{"زاد" if diff > 0 else "نقص"} {num(money(abs(diff)))} درهم، من {num(money(v0))} إلى {num(money(last))}'
            else:
                say = f'{"rose" if diff > 0 else "fell"} AED {num(money(abs(diff)))}, from {num(money(v0))} to {num(money(last))}'
            span = (f"من {human_date(d0, lang)} إلى {human_date(last_d, lang)}" if ar else f"{human_date(d0, lang)} to {human_date(last_d, lang)}")
            out.append(f'<li><b>{esc(self.chain(ch, lang))}</b> {say} <small>{esc(span)}</small></li>')
        return f'<ul class="chg">{"".join(out)}</ul>' if out else ""

    def chart_table(self, ser, dates, lang):
        ar = lang == "ar"
        chs = sorted(ser, key=lambda c: self.chain(c, lang))
        by = {ch: {d: m for d, m, _ in s} for ch, s in ser.items()}
        rows = "".join(f'<tr><th scope="row"><bdi class="num">{d}</bdi></th>'
                       + "".join(f'<td>{num(money(by[ch][d])) if d in by[ch] else ""}</td>' for ch in chs) + '</tr>'
                       for d in reversed(dates))
        return (f'<details class="chart-t"><summary>{"الأرقام يوم بيوم" if ar else "The numbers, day by day"}</summary>'
                f'<div class="xwrap"><table class="matrix"><thead><tr><th>{"اليوم" if ar else "Day"}</th>'
                + "".join(f'<th>{esc(self.chain(c, lang))}</th>' for c in chs) + f'</tr></thead><tbody>{rows}</tbody></table></div></details>')

    def time_section(self, lang):
        ar = lang == "ar"
        if len(ph.days(self.all, self.idx_date or self.today)) < TIME_DAYS: return ""
        rows = ""
        chains = sorted({r[0] for d in self.all.values() for r in d.get("parts") or [] if r[1] == "Standard"}, key=lambda c: self.chain(c, lang))
        for ch in chains:
            ct = ph.cheapest_time(self.all, ch, "Standard", upto=self.idx_date or self.today)
            if len(ct) < 2 or ct[0][2] >= ct[-1][2]: continue
            when = lambda r: f'{(DAYS_AR if ar else DAYS_EN)[r[0]]} {L(PART[r[1]], lang)}'
            rows += (f'<tr><th scope="row">{esc(self.chain(ch, lang))}</th><td>{esc(when(ct[0]))}</td><td><b>{num(money(ct[0][2]))}</b></td>'
                     f'<td>{esc(when(ct[-1]))}</td><td>{num(money(ct[-1][2]))}</td></tr>')
        if not rows: return ""
        th = ("السلسلة", "أرخص وقت", "المتوسط", "أغلى وقت", "المتوسط") if ar else ("Chain", "Cheapest time", "Average", "Dearest time", "Average")
        n = len(ph.days(self.all, self.idx_date or self.today))
        return (f'<section class="wrap pt-w" id="cheapest-time"><h2>{"أرخص وقت بالأسبوع" if ar else "The cheapest time of the week"}</h2>'
                f'<p class="hint">{esc(f"من {n} يوم سجّلناها: متوسط وسيط سعر أرخص مقعد في القاعة العادية لكل يوم ووقت، والوقت لازم يتكرر مرتين على الأقل." if ar else f"From the {n} days we recorded: the average of the regular hall’s median cheapest seat per day and time of day, counted only when that slot was seen at least twice.")}</p>'
                f'<div class="xwrap"><table class="matrix"><thead><tr>{"".join(f"<th>{esc(x)}</th>" for x in th)}</tr></thead><tbody>{rows}</tbody></table></div></section>')

    # -------------------------------------------------- /boxoffice/
    def week(self):
        end = max((d for d in self.full if d <= self.tomorrow), default=None)
        if not end: return [], []
        tot, used = ph.week_films(self.full, end)
        ranked = sorted(((f, v) for f, v in tot.items() if f in self.films), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
        return ranked[:20], used

    def boxoffice(self, lang):
        ar = lang == "ar"
        ranked, used = self.week()
        body = self.head(lang, BOX, "الأكثر عرضاً هالأسبوع في سينمات الإمارات" if ar else "Most shown in UAE cinemas this week",
                         esc("ترتيب الأفلام بعدد عروضها في جداول السينمات وبعدد السينمات اللي تعرضها. هذا عدد عروض، مب عدد تذاكر: ما نعرف كم تذكرة انباعت." if ar
                             else "Films ranked by how many shows the cinemas scheduled and how many cinemas show them. These are shows, not tickets sold: we do not know how many tickets were sold."))
        if ranked:
            span = (f'من {human_date(used[0], lang)} إلى {human_date(used[-1], lang)}، {ar_count(len(used), DAYS)}' if ar
                    else f'{human_date(used[0], lang)} to {human_date(used[-1], lang)}, {len(used)} day{"s" if len(used) != 1 else ""}')
            items = ""
            for fid, (n, c) in ranked:
                v, vw = self.vword(fid, lang)
                live = fid in self.showing and fid in self._by_film
                items += (f'<li data-fid="{esc(fid)}"><a href="{P(lang, "film", fid)}">{self.poster(fid, lang, "pst sm")}'
                          f'<span class="bo-t"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</span></a>'
                          f'<span class="bo-n">{self.count(n, ("عرض واحد", "عرضين", "عروض", "عرض"), ("show", "shows"), lang)}</span>'
                          f'<span class="bo-c">{self.count(c, ("سينما وحدة", "سينمتين", "سينمات", "سينما"), ("cinema", "cinemas"), lang)}</span>'
                          f'<span class="vw v-{v}">{esc(vw) if live else ""}</span></li>')
            body += (f'<section class="wrap bo-w"><p class="hint">{esc(span)}. {esc("السينمات: أكثر عدد سينمات عرضته في يوم واحد." if ar else "Cinemas: the most cinemas showing it on a single day.")}</p>'
                     f'<ol class="bo">{items}</ol></section>')
        body += self.compare_box(lang, "")
        title = "الأكثر عرضاً هالأسبوع — أفلام السينما في الإمارات" if ar else "Most shown films this week — UAE cinemas"
        desc = ("أي الأفلام معروضة أكثر في سينمات الإمارات هالأسبوع، بعدد العروض وعدد السينمات." if ar
                else "Which films UAE cinemas are showing most this week, by number of shows and cinemas.")
        graph = [{"@type": "ItemList", "name": title, "itemListOrder": "https://schema.org/ItemListOrderDescending",
                  "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": SITE + P(lang, "film", f), "name": self.ftitle(f, lang)}
                                      for i, (f, _) in enumerate(ranked)]},
                 self.breadcrumb_ld(lang, (L(BOX, lang), P(lang, "boxoffice")))]
        return {"title": title, "desc": desc, "body": body, "graph": graph, "kind": "boxoffice", "nav": "boxoffice"}

    # -------------------------------------------------- compare
    def compare_box(self, lang, fid):
        src = self.chunk_urls.get("compare", "")   # cmpload.js (main bundle) fetches the chunk only where a box is
        return (f'<section class="wrap cmp" data-cmp="{esc(fid)}" data-cmp-src="{esc(src)}" hidden><h2>{"قارن بين فيلمين" if lang == "ar" else "Compare two films"}</h2>'
                f'<div data-cmp-ui></div><div data-cmp-out></div></section>')

    def compare_data(self):
        """{t: today, f: {fid: [ar, en, verdict, critics, audience, runtime, rating]}, p: {fid: {city: [cheapest,
        {card: cheapest after it}]}}}. The next times are not here: compare.js reads them from the city's day
        slices (/data/<city>-<date>.json), which the visitor's clock filters, so they never run out at night."""
        f_, p_ = {}, {}
        cards = [c["id"] for c in self.cards]
        for fid in self.showing:
            ss = [s for s in self._by_film.get(fid, []) if s["date"] >= self.today]
            if not ss: continue
            f = self.films[fid]
            f_[fid] = [self.ftitle(fid, "ar"), self.ftitle(fid, "en"), self.vword(fid, "en")[0], *film_rates(f),
                       f.get("runtime"), f.get("rating")]
            best = {}
            for s in ss:
                c = self.cinemas[s["cinema"]]; city = c.get("city")
                code, _ = self.hall_code_label(s); hk = self.hkey(s)
                for p in s.get("prices") or []:
                    a = p.get("aed") or 0
                    if a <= 0: continue
                    b = best.setdefault(city, [None, {}])
                    if b[0] is None or a < b[0]: b[0] = a
                    for card in cards:
                        pay, _st = after(a, c["chain"], code, card, self.rules, self.today, hk, s["cinema"])
                        if pay is not None and pay < a and (card not in b[1] or pay < b[1][card]): b[1][card] = pay
            for city, b in best.items():   # a card only where it beats the plain cheapest ticket
                b[1] = {k: round(v, 2) for k, v in sorted(b[1].items()) if v < b[0]}
            p_[fid] = {c: [round(b[0], 2), b[1]] for c, b in sorted(best.items())}
        return {"t": self.today, "f": f_, "p": p_}

    # -------------------------------------------------- slots
    def film_slot(self, site, lang, fid):
        if self.films[fid].get("status") == "archived": return ""
        return self.similar_html(fid, lang) + self.compare_box(lang, fid)

    def person(self, pid, lang):
        """(name, href|None) from data["people"] — name_ar on Arabic pages, name_en on English, the other as a
        fallback; None when there is no name (a bare id such as «Q1» is never printed). A legacy name string that
        is not an id reads as itself. The link only when pages/people.py builds that person's page."""
        pp = self.d.get("people") or {}
        p = pp.get(pid) if isinstance(pp, dict) else None
        if isinstance(p, dict):
            n = (p.get("name_ar") if lang == "ar" else p.get("name_en")) or p.get("name_en") or p.get("name_ar")
        else:
            n = None if QID.match(pid) else pid
        if not n or QID.match(str(n)): return None          # a Wikidata label that is only the id is no name
        slug = p.get("slug") if isinstance(p, dict) else None
        return n, (P(lang, "people", slug) if slug and pid in self.person_pages() else None)

    def person_pages(self):
        if self._pages is None:
            try:
                from pages.people import People   # the people task's own rule for who gets a page
                self._pages = set(People(self.site).p) if any(m.__name__ == "pages.people" for m in self.site.modules) else set()
            except Exception:  # noqa: BLE001 - no people module: names without links
                self._pages = set()
        return self._pages

    def similar_html(self, fid, lang):
        if not self._sim:
            pool = [x for x in self.showing if self._by_film.get(x)]
            pp = simmod.people_of(self.films)
            self._sim = {x: simmod.similar(self.films, x, pool, n=4, weight=lambda y: self.today_count.get(y, 0), _pp=pp) for x in pool}
        rows = self._sim.get(fid) or []
        if not rows: return ""
        sep = "، " if lang == "ar" else ", "
        li = ""
        for x, _score, reasons in rows:
            why = []
            for kind, v in reasons:
                if len(why) == 2: break
                if kind == "person":
                    nh = self.person(v, lang)
                    if not nh: continue
                    n = esc(nh[0]); n = f'<a href="{nh[1]}">{n}</a>' if nh[1] else n
                    why.append(esc("فيه " if lang == "ar" else "with ") + f"<bdi>{n}</bdi>")
                elif kind == "genre": why.append(esc(genre_label(v, lang)))
                else: why.append(esc(lang_words(v, lang)))
            li += (f'<li><a href="{P(lang, "film", x)}">{self.poster(x, lang, "pst sm")}'
                   f'<span class="sim-t"{self.title_attr(x, lang)}>{esc(self.ftitle(x, lang))}</span></a>'
                   f'<span class="sim-w">{sep.join(why)}</span></li>')
        return f'<section class="sim"><h2>{"شي يشبه" if lang == "ar" else "Something like it"}</h2><ul class="sim-l">{li}</ul></section>'

    def home_links(self, site, lang):
        ar = lang == "ar"
        return (f'<section class="wrap insx"><p class="links more"><a href="{P(lang, "prices")}">{"أسعار التذاكر اليوم ومع الأيام" if ar else "Ticket prices, today and over time"}</a> '
                f'<a href="{P(lang, "boxoffice")}">{"الأكثر عرضاً هالأسبوع" if ar else "Most shown this week"}</a> '
                f'<a href="{P(lang, "q")}">{"أسئلة وأجوبة من الأرقام" if ar else "Questions answered from the numbers"}</a></p></section>')
