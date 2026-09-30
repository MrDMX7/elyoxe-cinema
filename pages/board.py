"""«اللوحة», the board (legend W2-P2a; MASTER-PLAN §1.1, §1.3, §2.1, §2.2, §5.3 W2-P2): what starts next near you, one
tap from a priced ticket. A departures board: the time on split-flap tiles, the film, the cinema, «بعد N د» in live
green within 30 minutes, the price (gold only when it is yours). It moves only when a minute passes.

Where it stands (the slots W1-P1 declared; this module edits no core page):
  home.after_bill   home, under the billboard: «يبدأ قريب منك», its city as plain text, a flip clock, 3 rows in a
                    fixed 168 px box (6 in two columns on a desktop), «اللوحة كاملة» (5 more, a <details>), and the
                    page's id="now" (the manifest's «الحين» shortcut, /#now, lands here with no script: §4.2 #40)
  city.hero         a city page: that city's next 8 rows (the page's own hero is its head, W2-P6)
  cinema.top        a cinema page: that cinema's next 3 rows
  notfound.body     the 404: three rows from the visitor's city (a dead link still lands two taps from a chain)
  film.first        a showing film's page: «أقرب عرض لك», one row held in a 56 px box, filled by src/js/board-live.js
                    from the city's shows (no script: hidden)
(sources.body «كيف نختار لك» and «اختار لي» are the pick's, W2-P2b; offline.body waits for W2-P10's offline page.)

A row is a plain link to its show, /film/<fid>/#s-<key> (the show link of §2.2, the key Kit.show_key), so a row → the
ticket's «احجز» is 2 taps, and with no script the film page scrolls to that time.

The rows (pick(), the twin of CB.pick in src/js/board-paint.js; tests/test_w2_p2a.py holds them equal): upcoming starts
in time order; one row per film on the whole board; any three rows in a row hold at most two of one cinema (one
cinema's own board has no such limit); a minute three films or more share is one row, «21:00 5 أفلام», which with
script opens a small sheet of those shows.

The island: every board carries its rows as a compact object (island()), 12 per city over the next 2 hours, 3 per half
hour, so an hour-old page still has a board before the city's shows arrive; after 22:00 the 2 hours run past midnight
into the next date's shows (every show carries its own date and time, and both dates are in the data).
  - Home and the 404 follow the visitor's city: they carry every city's rows and the renderer (src/js/board-paint.js)
    inline, right after the box, so a saved city is on the board in the first frame (no Dubai flash for Sharjah, and
    the box is fixed: no layout shift). Their server-drawn rows are Dubai's at the build's time (no script: a board).
  - A city's or a cinema's board is that place's: the server draws its rows, and the renderer comes as a lazy chunk
    after start-up (the pages' schedules are sized to what the page has left, so every inline byte would cost times).
The bundle carries only src/js/board.js, the few helpers the lazy half (src/js/board-live.js) reads.

A first visit to home (no saved city, /geo not asked yet): the box and its head keep their place and the rows wait
(geo-wait: visibility, never display) until src/js/geo.js picks the network's city; Dubai's show after 1.5 s."""
import datetime as dt
import json
import os
import re

from site_kit import CITIES, CITY, HOME_T, L, P, Plugin, esc, minify_lite, money

CSS = ("board", "pick")
JS = ("board",)                       # the bundle: only the helpers the lazy half reads (K.bd)
LAZY_JS = ("board-paint", "board-live", "pick")
# «اختار لي» (W2-P2b, §3.1) rides the same K.bd it reads here: home and the 404 hold its button (below); a city
# page already holds one of its own (pages/_core/places.py's city_hero), so it gets the chunk too, for free
PAGE_JS = {"home": ("board-live", "pick"), "404": ("board-live", "pick"), "film": ("board-live",),
           "city": ("board-paint", "board-live", "pick"), "cinema": ("board-paint", "board-live")}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAINT = os.path.join(ROOT, "src", "js", "board-paint.js")

# the board's words (MASTER-PLAN §1.7 voice; the new ones are listed in the package report for the dialect gate)
BOARD_T = {
    "head": HOME_T["near"],                                   # «يبدأ قريب منك»
    "in": (" في ", " in "),                                   # 297, r4-home: joins the head to the chosen city
    "now": ("الحين", "now"),
    "more": ("اللوحة كاملة", "The whole board"),
    "z": ("يبدأ الحين", "starting now"),
    "n": ("بعد {n} د", "in {n} min"),
    "x": ("{n} أفلام", "{n} films"),                          # «21:00 3 أفلام»: a minute three films share
    "x11": ("{n} فيلم", "{n} films"),                         # eleven and more: «11 فيلم»
    "w": ("جاري التحديث…", "Refreshing…"),                   # every row passed and no shows in yet (§1.7)
    "h": ("{n} تبدأ خلال ساعة", "{n} start within the hour"),   # a desktop only (§1.2 #11)
    "at": ("يبدأ الساعة {t}", "Starting at {t}"),             # the shared minute's sheet
    "first": ("أقرب عرض لك", "Your nearest show"),            # film.first
    "city": ("أقرب العروض في {city}", "Next shows in {city}"),   # a city page's board (the page's hero is its head)
    "cinema": ("أقرب العروض هني", "Next shows here"),         # a cinema page's board
    "pick": ("اختار لي", "Pick for me"),                      # the pick's entry (W2-P2b, §2.1, §3.1): held until
                                                               # pick.js binds it (data-hold hidden), then it answers
}

HOME_N, HOME_ND, HOME_M = 3, 6, 5   # rows in the fixed box (a desktop: two columns of 3), rows under «اللوحة كاملة»
CITY_N, CINEMA_N, NF_N = 8, 3, 3
SPAN, PER, BUCKETS = 30, 3, 4       # the island: 3 entries per half hour over the next 2 hours
CINEMA_ROWS = 12                    # one cinema's island: its next 12 starts, one per film
UAE = dt.timezone(dt.timedelta(hours=4))


def near_row_holds_now():
    """Core's home still drawing the old near row with id="now" (legend before W2-P4, which deletes that row and
    merges first, MASTER-PLAN §6.1): the board then leaves the id to it, so a page never carries two. Once W2-P4 is in,
    this is False and the board is the one «الحين» target. W2-QA deletes this check with the rest of the old row."""
    try:
        with open(os.path.join(ROOT, "pages", "_core", "home.py"), encoding="utf-8") as f:
            return 'id="now" data-near-row' in f.read()
    except OSError:
        return False


NEAR_NOW = near_row_holds_now()


def minute(date, time):
    """UAE wall-clock «date time» as whole minutes since the epoch (CB.at's twin)."""
    return int(dt.datetime.fromisoformat(f"{date}T{time}:00").replace(tzinfo=UAE).timestamp()) // 60


def hm(m):
    """Minutes since the epoch → «HH:MM» on the UAE clock (CB.hm's twin)."""
    return dt.datetime.fromtimestamp(m * 60, UAE).strftime("%H:%M")


def epoch_min(now):
    """The build's time (site.now) in minutes since the epoch; a naive time is UAE time (never the machine's zone)."""
    return int((now if now.tzinfo else now.replace(tzinfo=UAE)).timestamp()) // 60


WORD = re.compile(r"[\w$]")


def squeeze(js):
    """minify_lite, then the blanks the parser does not need, for the one script inlined on a page (home and the 404
    carry the renderer: every byte there is paid on each visit). A run of spaces outside a string or a regex literal
    goes, except between two word characters (and between two «+» or two «-»); line breaks stay, so a statement never
    joins the next. Written for src/js/board-paint.js (tests/test_w2_p2a.py runs what it gives in node)."""
    src, out, i, prev = minify_lite(js), [], 0, "\n"
    while i < len(src):
        ch = src[i]
        if ch in "\"'":
            j = i + 1
            while src[j] != ch: j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1]); prev, i = ch, j + 1
        elif ch == "/" and prev in "(,=:[!&|?{};\n":            # a regex literal (never a division there)
            j, cls = i + 1, False
            while cls or src[j] != "/":
                if src[j] == "\\": j += 1
                elif src[j] in "[]": cls = src[j] == "["
                j += 1
            j += 1
            while j < len(src) and src[j].isalpha(): j += 1
            out.append(src[i:j]); prev, i = "/", j
        elif ch in " \t":
            j = i
            while j < len(src) and src[j] in " \t": j += 1
            nxt = src[j] if j < len(src) else ""
            if WORD.match(prev) and nxt and WORD.match(nxt) or prev == nxt and prev in "+-": out.append(" ")
            i = j
        else:
            out.append(ch); prev, i = ch, i + 1
    return "".join(out)


def pick(rows, now, n, free=False):
    """What starts next (CB.pick's twin; rows in the board's order, each {at, f: [fid,…], c: [cid,…], …}). One row per
    film; any three rows in a row hold at most two of one cinema unless `free`; a minute three films or more share
    (not already on the board) is one entry {at, x: [each film's first row]}."""
    out, used = [], set()
    rows = [r for r in rows if r["at"] >= now]
    i = 0
    while i < len(rows) and len(out) < n:
        a, g = rows[i]["at"], []
        while i < len(rows) and rows[i]["at"] == a:
            g.append(rows[i]); i += 1
        x, one = [], set()
        for r in g:
            if r["f"][0] not in used and r["f"][0] not in one:
                one.add(r["f"][0]); x.append(r)
        if len(x) > 2:
            used |= one
            out.append({"at": a, "x": x})
            continue
        for r in g:
            if len(out) >= n or r["f"][0] in used: continue
            if (not free and len(out) >= 2 and "r" in out[-1] and "r" in out[-2]
                    and out[-1]["r"]["c"][0] == r["c"][0] == out[-2]["r"]["c"][0]):
                continue
            used.add(r["f"][0])
            out.append({"at": a, "r": r})
    return out


XCAP = 3   # a collapsed minute's stored member cap (island size, §5.3 W2-P2 budget; the true count survives as 'gx')


def flat(entries, cap=XCAP):
    """The rows an island keeps for these entries: each single row, each shared minute's rows — capped to `cap`
    members with the true count stamped on each kept member as 'gx' (row_html/CB.row show gx over the member count
    when it is set). A peak-hour minute that collapses many films no longer carries every one of them into the
    island (fix round, review §Important 1-3): the sheet gets the rest once the slice is in (board-live.js's CB.src,
    which replaces the island's rows with the city's real ones within the first second on every page that has one)."""
    out = []
    for e in entries:
        if "x" in e:
            members = e["x"]
            kept = [dict(r, gx=len(members)) for r in members[:cap]] if len(members) > cap else members
            out.extend(kept)
        else:
            out.append(e["r"])
    return out


def href(e, isl):
    """CB.href's twin: a row's show link (a shared minute's, its first film's), also its identity from minute to minute."""
    r = e["r"] if "r" in e else e["x"][0]
    return f'{isl["b"]}film/{r["f"][0]}/#s-{r["k"]}'


def time_html(t):
    """CB.time's twin: the time for a screen reader («20:40», where the tiles alone read «2 0 : 4 0»), then one flip tile
    per digit; the colon is the dull part."""
    return f'<span class="vh">{t}</span><span class="bt" aria-hidden="true">' + "".join("<b>:</b>" if ch == ":" else f"<i>{ch}</i>" for ch in t) + "</span>"


def row_html(e, now, isl):
    """CB.row's twin (one entry of pick(), escaped strings as the island holds them)."""
    s = isl["s"]
    r = e["r"] if "r" in e else e["x"][0]
    en = lambda o: ' lang="en" dir="ltr"' if o else ""
    n = e["at"] - now
    z = "" if n > 30 else f'<span class="bs">{s["n"].replace("{n}", str(n)) if n > 0 else s["z"]}</span>'
    h = f'<a class="br{" bx" if "x" in e else ""}" href="{href(e, isl)}">{time_html(hm(e["at"]))}<span class="bm">'
    if "x" in e:
        nx = e["x"][0].get("gx") or len(e["x"])   # gx: the true count when the island capped the stored members
        return (h + f'<span class="bf">{(s["x11"] if nx > 10 else s["x"]).replace("{n}", str(nx))}</span><span class="bc">'
                + s["sep"].join(f'<bdi{en(x["f"][2])}>{x["f"][1]}</bdi>' for x in e["x"]) + f'</span></span><span class="be">{z}</span></a>')
    chain = r["c"][3] if len(r["c"]) > 3 else r["c"][0].split("-")[0]
    cell = (f'<span class="p" data-aed="{r["p"]}" data-chain="{chain}" data-hall="{r["h"][0]}" data-hk="{r["h"][1]}" '
            f'data-cin="{r["c"][0]}"><span class="num">{r["p"]}</span></span>') if r["p"] else ""
    return (h + f'<bdi class="bf"{en(r["f"][2])}>{r["f"][1]}</bdi><span class="bc"><bdi{en(r["c"][2])}>{r["c"][1]}</bdi></span></span>'
            f'<span class="be">{z}{cell}</span></a>')


class Board:
    def __init__(self, site):
        self.s = site
        self.now = epoch_min(site.now)
        self._rows = None
        self._paint = None

    # ------------------------------------------------ every show as the board reads it
    def rows(self):
        """Every show (every date in the data) as {at, s, fid, cid, key, price}, in the board's order: start, then
        cinema, film and key (board-live.js sorts a city's shows the same way when it knows no distance)."""
        if self._rows is None:
            out = []
            for sh in self.s.shows:
                # a live price only: a table price carries a date the row has no room to say (§1.2 #8)
                ps = [p["aed"] for p in sh.get("prices") or [] if (p.get("aed") or 0) > 0]
                price = money(min(ps)) if ps and not self.s.table_date(sh) else 0
                out.append({"at": minute(sh["date"], sh["time"]), "s": sh, "fid": sh["film"], "cid": sh["cinema"],
                            "key": self.s.show_key_of(sh), "price": price})
            out.sort(key=lambda r: (r["at"], r["cid"], r["fid"], r["key"]))
            self._rows = out
        return self._rows

    def city_of(self, cid):
        return self.s.cinemas[cid].get("city")

    @staticmethod
    def as_row(r):
        """A show in pick()'s shape (the island's rows before they are indexed)."""
        return {"at": r["at"], "f": [r["fid"]], "c": [r["cid"]], "src": r}

    def city_rows(self, city, now=None):
        """A city's island: 3 entries per half hour over the next 2 hours, each half hour chosen by the board's own rule
        on its own (a film may come back in a later half hour: when its earlier row has passed, the painter shows it
        again, as the city's shows would; the painter applies the rule across the whole board at the visitor's minute)."""
        now = self.now if now is None else now
        rs = [self.as_row(r) for r in self.rows() if self.city_of(r["cid"]) == city and now <= r["at"] < now + SPAN * BUCKETS]
        out = []
        for b in range(BUCKETS):
            t = now + SPAN * b
            out += flat(pick([r for r in rs if t <= r["at"] < t + SPAN], t, PER))
        # gx lives on the as_row wrapper (flat()'s copy), never on the cached show dict (self._rows is shared state)
        return [dict(x["src"], gx=x["gx"]) if "gx" in x else x["src"] for x in out]

    def cinema_rows(self, cid):
        """A cinema's island: its next 12 starts, whatever the film (the painter keeps one row per film)."""
        return [r for r in self.rows() if r["cid"] == cid and r["at"] >= self.now][:CINEMA_ROWS]

    def next_at(self, kind, key):
        """The next future show beyond the window (a city's, or one cinema's), for the honest fallback when the box
        has nothing left tonight (fix round, review §Important 5): «جاري التحديث…» only while a slice is genuinely
        pending, never for hours after the city's last show."""
        rs = ([r["at"] for r in self.rows() if r["cid"] == key and r["at"] >= self.now] if kind == "cinema" else
              [r["at"] for r in self.rows() if self.city_of(r["cid"]) == key and r["at"] >= self.now])
        return min(rs) if rs else None

    # ------------------------------------------------ the island
    def island(self, lang, groups, n, m=0, scope="city", free=False, names=False, hold=False, nd=0):
        """The page's rows as the object src/js/board-paint.js reads (its header says the fields). `groups`: {city or
        cinema id: [rows]} already chosen. Titles and names are escaped here, once."""
        films, cins, halls, dates, fi, ci, hi, di, rows = [], [], [], [], {}, {}, {}, {}, {}
        for key, rs in groups.items():
            out = []
            for r in rs:
                sh, fid, cid = r["s"], r["fid"], r["cid"]
                if fid not in fi:
                    fi[fid] = len(films)
                    films.append([fid, esc(self.s.ftitle(fid, lang)), 1 if self.s.title_attr(fid, lang) else 0])
                if cid not in ci:
                    ci[cid] = len(cins)
                    chain = self.s.cinemas[cid]["chain"]
                    c = [cid, esc(self.s.cname(cid, lang)), 1 if self.s.cname_is_en(cid, lang) else 0]
                    if cid.split("-")[0] != chain: c.append(chain)
                    cins.append(c)
                h = (sh.get("hall") or "OTHER", self.s.hkey(sh))
                if h not in hi:
                    hi[h] = len(halls); halls.append(list(h))
                if sh["date"] not in di:
                    di[sh["date"]] = len(dates); dates.append(sh["date"])
                row = [di[sh["date"]], sh["time"], fi[fid], ci[cid], hi[h], r["price"], r["key"]]
                if "gx" in r: row.append(r["gx"])   # a capped shared-minute member's true count (index 7)
                out.append(row)
            rows[key] = out
        s = {k: L(BOARD_T[k], lang) for k in ("z", "n", "x", "x11", "w", "at")} | {"sep": "، " if lang == "ar" else ", "}
        if nd: s["h"] = L(BOARD_T["h"], lang)
        isl = {"d": dates, "f": films, "c": cins, "h": halls, "r": rows, "b": P(lang), "g": scope, "n": n, "m": m, "s": s}
        if nd: isl["nd"] = nd
        if free: isl["o"] = 1
        if hold: isl["w"] = 1
        if names: isl["cn"] = {c: L((a, e), lang) for c, a, e in CITIES}
        return isl

    @staticmethod
    def expand(isl, key):
        """CB.rows's twin: the island's rows for a key as row objects (escaped strings, as the script sees them).
        A capped shared-minute member carries the true count as x[7] ('gx')."""
        out = []
        for x in isl["r"].get(key, []):
            r = {"at": minute(isl["d"][x[0]], x[1]), "f": isl["f"][x[2]], "c": isl["c"][x[3]], "h": isl["h"][x[4]], "p": x[5], "k": x[6]}
            if len(x) > 7: r["gx"] = x[7]
            out.append(r)
        return out

    def paint_js(self):
        if self._paint is None:
            with open(PAINT, encoding="utf-8") as f:
                self._paint = squeeze(f.read())
        return self._paint

    def script(self, isl, inline):
        """The island: inline with the renderer where the board follows the visitor's city (drawn before the first
        paint), else as data for the «board-paint» chunk."""
        data = json.dumps(isl, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
        if inline:
            return "<script>(function(){" + self.paint_js() + "\ncbPaint(" + data + ",document.currentScript.parentNode)})()</script>"
        return '<script type="application/json" data-island>' + data + "</script>"

    @staticmethod
    def rows_html(isl, key, now, next_at=None):
        """CB.draw's first paint at `now`: the box's rows; with no card the one cheapest price in the box is lit (.lo, the
        first on a tie). The rows under «اللوحة كاملة» are the script's (with no script the <details> stays hidden).
        With nothing to show, «جاري التحديث…» only stands for a slice genuinely pending; past the city's last show it
        names the next one instead (`next_at`, fix round review §Important 5)."""
        es = pick(Board.expand(isl, key), now, isl["n"], isl.get("o", 0))
        box = [row_html(e, now, isl) for e in es]
        ps = [(float(e["r"]["p"]), i) for i, e in enumerate(es) if "r" in e and e["r"]["p"]]
        if ps:
            lo = min(ps)[1]
            box[lo] = box[lo].replace('<span class="p" ', '<span class="p lo" ', 1)
        if box:
            return "".join(box)
        msg = isl["s"]["at"].replace("{t}", hm(next_at)) if next_at is not None else isl["s"]["w"]
        return f'<p class="bw">{msg}</p>'

    @staticmethod
    def pick_btn(lang):
        """«اختار لي» (W2-P2b, §2.1, §3.1): held invisible (never absent, so nothing moves when pick.js binds it,
        the same contract as places.py's city button) until that chunk decides a show and shows itself. Its
        `data-pick` is empty, meaning "the visitor's own city" (places.py's own button instead names its city)."""
        return (f'<button type="button" class="btn ghost pl-pick" data-pick="" data-hold hidden>'
                f'{esc(L(BOARD_T["pick"], lang))}</button>')

    # ------------------------------------------------ the slots
    def board(self, lang, isl, key, kind, head=False, label=None, inline=False, now_id=False, pick=False):
        """The board's markup: a head (or only a label), the fixed box, «اللوحة كاملة» (when the island has more rows
        for it), the island (with the renderer, inline). `pick`: the board also holds «اختار لي» (home, the 404,
        §3.1 "used by") — inside the head next to its h2 when there is one, else its own line above the rows."""
        attrs = (' id="now"' if now_id else "") + (' aria-labelledby="bh-t"' if head else f' aria-label="{esc(label)}"')
        h = ""
        if head:
            t = hm(self.now)
            # the chosen city sits in the heading itself, not a separate line («يبدأ قريب منك في العين», 297,
            # r4-home) — data-board-city still updates live when the city pill changes (board-paint.js CB.draw);
            # .bh-city hides with the rest of .bh-c while a first visit waits on /geo (board.css .geo-wait)
            h = (f'<div class="bh"><div class="bh-top"><h2 id="bh-t">{esc(L(BOARD_T["head"], lang))}'
                 f'<span class="bh-city" data-board-city-wrap>{esc(L(BOARD_T["in"], lang))}<span data-board-city>{esc(L(CITY[key], lang))}</span></span></h2>'
                 + (self.pick_btn(lang) if pick else "") + '</div>'
                 f'<p class="bh-s"><i class="bh-l" aria-hidden="true"></i><span class="bh-c">{esc(L(BOARD_T["now"], lang))}</span>'
                 f'<span class="bk" data-board-clock data-t="{t}">{time_html(t)}</span><span class="bh-n" data-board-n></span></p></div>')
        elif pick:
            h = f'<div class="bh bh-nolabel">{self.pick_btn(lang)}</div>'
        mo = ""
        if isl["m"]:
            mo = (f'<details class="bmore" hidden><summary>{esc(L(BOARD_T["more"], lang))}</summary>'
                  f'<div class="brs" data-brs-more></div></details>')
        nx = self.next_at(kind, key)
        return (f'<section class="board wrap b-{kind}" data-board="{kind}"{attrs} style="--bn:{isl["n"]}">{h}'
                f'<div class="brs" data-brs data-lo>{self.rows_html(isl, key, self.now, nx)}</div>{mo}{self.script(isl, inline)}</section>')

    def sheet(self, lang):
        """The shared minute's sheet (a row «21:00 5 أفلام» opens it; board-live.js fills it), once per page."""
        self.s._sheets.append(self.s.sheet("sheet-board", BOARD_T["at"], '<div class="brs" data-bsheet></div>', lang))

    def home(self, site, lang):
        groups = {c: self.city_rows(c) for c, _, _ in CITIES}
        isl = self.island(lang, groups, HOME_N, HOME_M, names=True, hold=True, nd=HOME_ND)
        self.sheet(lang)
        return self.board(lang, isl, "dubai", "home", head=True, inline=True, now_id=not NEAR_NOW, pick=True)

    def city(self, site, lang, city):
        isl = self.island(lang, {city: self.city_rows(city)}, CITY_N, scope=city)
        self.sheet(lang)
        return self.board(lang, isl, city, "city", label=L(BOARD_T["city"], lang).replace("{city}", L(CITY[city], lang)))

    def cinema(self, site, lang, cid, city):
        rs = self.cinema_rows(cid)
        if not rs: return ""
        isl = self.island(lang, {cid: rs}, CINEMA_N, scope=cid, free=True)
        return self.board(lang, isl, cid, "cinema", label=L(BOARD_T["cinema"], lang))

    def notfound(self, site, lang):
        groups = {c: self.city_rows(c) for c, _, _ in CITIES}
        isl = self.island(lang, groups, NF_N, names=True)
        self.sheet(lang)
        return self.board(lang, isl, "dubai", "404", label=L(BOARD_T["head"], lang), inline=True, pick=True)

    def film_first(self, site, lang, fid):
        """«أقرب عرض لك»: a held 56 px box when the film shows in the visitor's city (decided before the first paint by a
        line of script against the cities the build knows), filled by board-live.js from the city's shows: the soonest
        show the visitor can still reach. No script: hidden."""
        cities = sorted({self.city_of(r["cid"]) for r in self.rows() if r["fid"] == fid and r["at"] >= self.now})
        if not cities: return ""
        strings = {"l": L(BOARD_T["first"], lang), "n": L(BOARD_T["n"], lang), "sep": "، " if lang == "ar" else ", "}
        return (f'<div class="bff wrap" data-board="film" data-cities="{" ".join(cities)}" '
                f'data-s="{esc(json.dumps(strings, ensure_ascii=False, separators=(",", ":")))}" data-hold hidden></div>'
                '<script>(function(b){var c;try{c=localStorage.getItem("cinema.city")}catch(e){}'
                'if((" "+b.getAttribute("data-cities")+" ").indexOf(" "+(c||"dubai")+" ")>=0)b.classList.add("hold")})'
                '(document.currentScript.previousElementSibling)</script>')


def register(site):
    b = Board(site)
    return Plugin(slots={"home.after_bill": b.home, "city.hero": b.city, "cinema.top": b.cinema,
                         "notfound.body": b.notfound, "film.first": b.film_first}, page_js=PAGE_JS)
