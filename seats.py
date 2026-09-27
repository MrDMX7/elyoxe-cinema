"""Inside the hall: each chain's seat-layout response as one hall map, the best free seat, and a capped
occupancy sampler for shows about to start (phase 2, spec B; docs/superpowers/specs/2026-09-27-phase2-design.md).

The hall map (`normalise(chain, raw)`):

    {"rows": [{"name": "G", "seats": [{"id", "x", "col", "status", "cls"}]}],
     "screen_side": "top" | "bottom", "classes": [{"name", "aed"}]}

rows are in the chain's own drawing order, screen_side says on which end of that list the screen is;
x is the seat's 0-based grid column (aisles keep their width), col the number printed on it, cls its seat
class, status one of free | taken | blocked | wheelchair (a wheelchair space still on sale). Aisles are not
seats; a row with no seat is dropped. classes carries each class's price where the same response states it.

Per chain (what each response exposes, and how the screen end was established):

| chain | response | seats / status | screen end |
|---|---|---|---|
| star | GET seat-layout/<ss_id> `Records[]` | srt_id 2/12/13 or "No Seat" = aisle; seat_reserve_type_id 8 = taken, covidBlocked = blocked, sst_seat_type "Wheelchair" or sl_seat_status 3 = wheelchair (the site's own cell classes, index-*.js) | top: sl_row_num 1 first; the cheapest class (STAR SELECT) sits in rows 1–5 of a NORMAL hall |
| cineroyal | POST getSeatsByScreenRef `rowSeats` | image B_Img_011 = aisle; seatFlag 0 = blocked, internetBooked 0 = taken (the page's seatClicked() refuses both) | bottom: rows by rowName as the page sorts them; the dearest tier (Premium) is row A, the cheapest (Standard) the last rows |
| novo | GET seat-layout/cinemas/<cid>/sessions/<sid> `data.areas[].row[]` | {} = aisle; Vista status 0 empty, 1 sold, other = blocked | top: Vista lists the row nearest the screen first |
| cinemacity | POST launch/seatpreview/<uuid> `seatsLayoutModel.rows[]` | isASeat false = aisle; status 1 sold, isUnavailable or another status = blocked; no price (that is GetTickets) | top: as Novo |
| reel | POST seats/getSeatLayout `Sourcedata.AreaEntityList[]` | Status Space = aisle, Empty, Sold, Special = wheelchair (counted in Sessions.json SeatsAvailable), other = blocked | top: the first row is the area named "Premium Front" |
| vox | GET /booking/<order>/seats (HTML) | td.blank = aisle; .sold = taken; .wheelchair = wheelchair; a disabled input = blocked; class name from the legend li with the same data-area | top: the screen block precedes the table and the dearer "Preferred View" rows are the last |
| roxy | GET /en/seat-selection/<cinema>/<session>/<nid>/… (HTML, public: no login, no cookie) | div.seat without an input = aisle; .sold (status 7) = taken; input.wheelchair = wheelchair; status 0 = free, other = blocked; class from the input's screen-type, price from the legend span[seat-category][price-in-aed] | top: the screen image precedes the rows, and the dearer "Premium View" rows are the last |

A shape is kept per physical screen where the chain names it (Star screen_name, Cine Royal screenRefId, Cinema
City screen name, Reel ScreenName); VOX, Novo and Roxy name none, so theirs are kept per hall label, and a label
seen with more than one shape gets no drawing and no seat total (steps/occupancy.py). A show's own fresh sample is
always its own map.

Nothing here selects, holds or releases a seat, and nothing logs in (Reel's anonymous guest token, the one its
price reader uses, is not an account — ruled acceptable in fix round 1): the sampler makes exactly the read calls
the readers already make for prices (VOX/Reel/Novo open the same anonymous seat-less order the chain's own
page opens, and VOX/Reel abandon it through the page's own link, as the readers do).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

DUBAI = ZoneInfo("Asia/Dubai")
STATUS = ("free", "taken", "blocked", "wheelchair")
SUPPORTED = ("star", "cineroyal", "novo", "cinemacity", "reel", "vox", "roxy")

FRESH_MIN = 90            # occupancy older than this is never shown
WINDOW_H = 3              # sample shows starting within the next 3 hours
MAX_REQ = 60              # HTTP requests per chain per run (every redirect and retry counts)
GAP_S = 1.0               # at least this many seconds between two requests to one chain
RESAMPLE_MIN = 45         # a show sampled this recently is not sampled again
RUN_BUDGET_S = 240        # wall clock for the whole sampler (chains run side by side)
TARGET = 2 / 3            # the best row: two thirds of the way back from the screen


# ---------------------------------------------------------------- normalisers
def _seat(sid, x, col, status, cls):
    return {"id": str(sid), "x": int(x), "col": "" if col is None else str(col), "status": status, "cls": cls or ""}


def _hall(rows, side, prices=None):
    rows = [r for r in rows if r["seats"]]
    if not rows:
        return None
    seen = []
    for r in rows:
        for s in r["seats"]:
            if s["cls"] not in seen: seen.append(s["cls"])
    prices = prices or {}
    return {"rows": rows, "screen_side": side, "classes": [{"name": c, "aed": prices.get(c)} for c in seen]}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


_ROW_NAME = re.compile(r"^([A-Za-z]{1,2})(\d+)$")


def _star(raw):
    recs = raw.get("Records") if isinstance(raw, dict) else None
    if not recs:
        return None
    by_row, prices = {}, {}
    for r in recs:
        by_row.setdefault(int(r.get("sl_row_num") or 0), []).append(r)
    rows = []
    x0 = min(int(r.get("sl_col_num") or 0) for r in recs)
    for n in sorted(by_row):
        seats, name = [], None
        for r in sorted(by_row[n], key=lambda r: int(r.get("sl_col_num") or 0)):
            if r.get("srt_id") in (2, 12, 13) or (r.get("srt_name") or "").lower() == "no seat" or not r.get("sl_seat_name"):
                continue
            label = str(r["sl_seat_name"])
            m = _ROW_NAME.match(label)
            rn, col = (m.group(1), m.group(2)) if m else (label.split("-", 1) if "-" in label else (str(n), label))
            name = name or rn
            cls = (r.get("sst_seat_type") or "").strip()
            if _num(r.get("seat_price")) and cls: prices.setdefault(cls, _num(r.get("seat_price")))
            if str(r.get("seat_reserve_type_id")) == "8" or r.get("is_booking_done") is True:
                st = "taken"
            elif r.get("covidBlocked") or r.get("covidBlockedTemp"):
                st = "blocked"
            elif cls.lower() == "wheelchair" or str(r.get("sl_seat_status")) == "3":
                st = "wheelchair"
            else:
                st = "free"
            seats.append(_seat(label, int(r.get("sl_col_num") or 0) - x0, col, st, cls))
        rows.append({"name": name or str(n), "seats": seats})
    return _hall(rows, "top", prices)


def _cineroyal(raw):
    rs = raw.get("rowSeats") if isinstance(raw, dict) else None
    if not rs:
        return None
    prices = {p.get("tierName"): _num(p.get("unitPrice")) for p in raw.get("prices") or [] if p.get("tierName")}
    rows = []
    for row in sorted(rs.values(), key=lambda r: ((r.get("seats") or [{}])[0].get("rowName") or "")):
        seats, name = [], None
        for s in row.get("seats") or []:
            name = name or s.get("rowName")
            if "B_Img_011" in (s.get("image") or ""):
                continue
            st = "blocked" if s.get("seatFlag") == 0 else "taken" if s.get("internetBooked") == 0 else "free"
            seats.append(_seat(s.get("seatId") or f"{s.get('rowName')}/{s.get('colName')}", int(s.get("colNo") or 0),
                               s.get("colName"), st, s.get("tierName") or row.get("tierName")))
        rows.append({"name": name or "", "seats": seats})
    return _hall(rows, "bottom", prices)


def _vista_status(code):
    return "free" if code == 0 else "taken" if code == 1 else "blocked"


def _novo(raw):
    d = (raw or {}).get("data") if isinstance(raw, dict) else None
    if not d or not d.get("areas"):
        return None
    rows, prices = [], {}
    for a in d["areas"]:
        cls = (a.get("name") or "").strip()
        if _num(a.get("priceInCents")): prices.setdefault(cls, round(a["priceInCents"] / 100, 2))
        for r in a.get("row") or []:
            seats = [_seat(f"{r.get('name')}{s.get('name')}", i, s.get("name"), _vista_status(s.get("status")), cls)
                     for i, s in enumerate(r.get("seats") or []) if s and s.get("id") not in (None, "")]
            rows.append({"name": r.get("name") or "", "seats": seats})
    return _hall(rows, "top", prices)


def _cinemacity(raw):
    lay = (((raw or {}).get("selectSeatsModel") or {}).get("seatsLayoutModel")) if isinstance(raw, dict) else None
    if not lay or not lay.get("rows"):
        return None
    area = {str(a.get("areaNumber")): (a.get("name") or "").strip() for a in lay.get("areas") or []}
    rows = []
    for r in lay["rows"]:
        seats = []
        for i, s in enumerate(r.get("seats") or []):
            if not s.get("isASeat"):
                continue
            st = "blocked" if s.get("isUnavailable") else _vista_status(s.get("status"))
            seats.append(_seat(s.get("seatName") or f"{r.get('physicalName')}{s.get('text')}", i, s.get("text"), st,
                               area.get(str(s.get("areaId")), "")))
        rows.append({"name": r.get("physicalName") or "", "seats": seats})
    return _hall(rows, "top")


_REEL = {"empty": "free", "sold": "taken", "special": "wheelchair"}


def _reel(raw):
    src = (raw or {}).get("Sourcedata") if isinstance(raw, dict) else None
    if not isinstance(src, dict) or not src.get("AreaEntityList"):
        return None
    tickets = {}
    for t in src.get("TicketList") or []:
        if not t.get("IsFreeTicket") and _num(t.get("PriceInAed")): tickets.setdefault(t.get("AreaCode"), float(t["PriceInAed"]))
    rows, prices = [], {}
    for a in src["AreaEntityList"]:
        cls = (a.get("AreaDescription") or "").strip()
        if tickets.get(a.get("AreaCode")): prices.setdefault(cls, tickets[a.get("AreaCode")])
        for r in a.get("rowEntityList") or []:
            seats = []
            for i, s in enumerate(r.get("seatEntityList") or []):
                code = (s.get("Status") or "").strip().lower()
                if code in ("space", "") or not s.get("Id"):
                    continue
                seats.append(_seat(f"{r.get('PhysicalName')}{s.get('Id')}", i, s.get("Id"), _REEL.get(code, "blocked"), cls))
            rows.append({"name": r.get("PhysicalName") or "", "seats": seats})
    return _hall(rows, "top", prices)


_AED = re.compile(r"([\d.]+)\s*AED")


def _vox(raw):
    if not isinstance(raw, str) or "seat-selection" not in raw:
        return None
    from bs4 import BeautifulSoup   # the VOX reader's own parser
    soup = BeautifulSoup(raw, "lxml")
    legend, prices = {}, {}
    for li in soup.select("li.seat[data-area][data-label]"):
        legend.setdefault(li["data-area"], li["data-label"].strip())
        m = _AED.search(li.get("data-price") or "")
        if m and _num(m.group(1)): prices.setdefault(li["data-label"].strip(), float(m.group(1)))
    table = soup.select_one("form#seat-selection table") or soup.select_one("table")
    if table is None:
        return None
    rows = []
    for tr in table.select("tbody tr"):
        seats, name = [], None
        for i, td in enumerate(tr.find_all("td")):
            cl = td.get("class") or []
            if "blank" in cl:
                continue
            lab = td.find("label")
            label = (lab.get("title") if lab else None) or (td.get_text(strip=True) or f"{i}")
            rn, _, col = label.partition("-")
            name = name or rn
            inp = td.find("input")
            st = ("taken" if "sold" in cl else "wheelchair" if "wheelchair" in cl
                  else "blocked" if inp is None or inp.has_attr("disabled") else "free")
            seats.append(_seat(label, i, col or label, st, legend.get(td.get("data-area"), "")))
        rows.append({"name": name or "", "seats": seats})
    return _hall(rows, "top", prices)


def _roxy(raw):
    if not isinstance(raw, str) or "seats-row" not in raw:
        return None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw, "lxml")
    prices = {}
    for sp in soup.select("span[seat-category][price-in-aed]"):
        if _num(sp.get("price-in-aed")): prices.setdefault(sp["seat-category"].strip(), float(sp["price-in-aed"]))
    rows = []
    for tr in soup.select(".seats-row"):
        cells = [d for d in tr.find_all("div", recursive=False) if "letter" not in (d.get("class") or [])]
        seats, name = [], None
        for x, d in enumerate(cells):
            inp = d.find("input")
            if inp is None:
                continue
            name = name or inp.get("row-name")
            label = inp.get("value") or inp.get("column") or f"{name}{x}"
            code = str(inp.get("status") or "")
            st = ("taken" if "sold" in (d.get("class") or []) or code == "7"
                  else "wheelchair" if "wheelchair" in (inp.get("class") or []) else "free" if code == "0" else "blocked")
            seats.append(_seat(label, x, inp.get("seat-id") or label, st, (inp.get("screen-type") or "").strip()))
        rows.append({"name": name or "", "seats": seats})
    return _hall(rows, "top", prices)


NORMALISERS = {"roxy": _roxy, "star": _star, "cineroyal": _cineroyal, "novo": _novo, "cinemacity": _cinemacity, "reel": _reel, "vox": _vox}


def normalise(chain, raw):
    """The hall map for one chain's seat-layout response, or None (unknown chain, empty or unexpected shape)."""
    fn = NORMALISERS.get(chain)
    if fn is None or raw is None:
        return None
    try:
        return fn(raw)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------- counts, best seat, compact form
def counts(hall):
    """{"free", "total"}: seats on sale now (wheelchair spaces included, as the chains count them) of all seats."""
    seats = [s for r in hall["rows"] for s in r["seats"]]
    return {"free": sum(s["status"] in ("free", "wheelchair") for s in seats), "total": len(seats)}


def best_seat(hall, statuses=True):
    """The best free seat: rows 55–75 % of the way back from the screen, the middle third of the columns,
    the dearest class that has one (closest to two thirds back, then to the centre, within it). statuses=False: the best
    place in the hall whatever is sold (a shape with no live status). {"row", "id", "col", "cls"} or None."""
    rows = hall["rows"] if hall.get("screen_side", "top") == "top" else list(reversed(hall["rows"]))
    n = len(rows)
    if not n:
        return None
    xs = [s["x"] for r in rows for s in r["seats"]]
    lo, hi = min(xs), max(xs)
    width = hi - lo + 1
    left, right = lo + width / 3, lo + 2 * width / 3
    centre = (lo + hi) / 2
    depth = [i / (n - 1) if n > 1 else 0.0 for i in range(n)]
    ok_rows = [i for i in range(n) if 0.55 <= depth[i] <= 0.75]
    if not ok_rows:   # a short hall: the one row closest to two thirds back
        ok_rows = [min(range(n), key=lambda i: abs(depth[i] - TARGET))]
    rank = sorted(hall.get("classes") or [], key=lambda c: -(c.get("aed") or 0))
    order = [c["name"] for c in rank] + sorted({s["cls"] for r in rows for s in r["seats"]} - {c["name"] for c in rank})
    for cls in order:
        cand = [(round(abs(depth[i] - TARGET), 6), abs(s["x"] - centre), rows[i]["name"], s)
                for i in ok_rows for s in rows[i]["seats"]
                if s["cls"] == cls and left <= s["x"] < right and (s["status"] == "free" or not statuses and s["status"] != "blocked")]
        if cand:
            _, _, row, s = min(cand, key=lambda c: (c[0], c[1]))
            return {"row": row, "id": s["id"], "col": s["col"], "x": s["x"], "cls": cls}
    return None


def expand(shape, status=None):
    """compact()'s shape (and optionally its status rows) back into a hall map; with no status every seat is
    "free" (a shape tells where seats are, not who bought them). Seat ids are "<row>@<x>"."""
    classes = [c for c, _ in shape.get("c") or []]
    back = {v: k for k, v in _ST.items()}
    rows = []
    for i, (name, cells) in enumerate(shape.get("r") or []):
        st = status[i] if status and i < len(status) else None
        seats = []
        for x, ch in enumerate(cells):
            if ch == ".":
                continue
            k = _DIGITS.index(ch) if ch in _DIGITS else 0
            seats.append(_seat(f"{name}@{x}", x, None, back.get(st[x], "free") if st and x < len(st) else "free",
                               classes[k] if k < len(classes) else ""))
        rows.append({"name": name, "seats": seats})
    return {"rows": [r for r in rows if r["seats"]], "screen_side": shape.get("s") or "top",
            "classes": [{"name": c, "aed": a} for c, a in shape.get("c") or []]}


_ST = {"free": "o", "taken": "x", "blocked": "b", "wheelchair": "w"}
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def compact(hall):
    """(shape, status) for the site: shape = {"s": screen side, "c": [[class, aed]], "r": [[row, cells]]} with
    one character per grid column ("." aisle, else the class's index); status = one string per row, "." aisle,
    o free, x taken, b blocked, w wheelchair."""
    classes = [c["name"] for c in hall["classes"]][:len(_DIGITS)]
    shape_rows, status = [], []
    for r in hall["rows"]:
        width = max(s["x"] for s in r["seats"]) + 1
        cells, st = ["."] * width, ["."] * width
        for s in r["seats"]:
            cells[s["x"]] = _DIGITS[classes.index(s["cls"])] if s["cls"] in classes else "0"
            st[s["x"]] = _ST[s["status"]]
        shape_rows.append([r["name"], "".join(cells)])
        status.append("".join(st))
    shape = {"s": hall["screen_side"], "c": [[c["name"], c["aed"]] for c in hall["classes"]], "r": shape_rows}
    return shape, status


def shape_key(shape):
    return hashlib.sha1(json.dumps(shape, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- layouts kept from the price sampling
_LOCK = threading.Lock()
KEPT: dict = {}   # "cinema|hall_label|screen" -> {"shape", "at", "date"}: filled while the readers sample prices


def hall_key(cinema, hall_label, screen=None):
    """A hall shape's key: the physical screen when the chain names it, else "#<shape key>" (keep())."""
    return f"{cinema}|{hall_label or ''}|{screen or ''}"


def keep(chain, cinema, hall_label, date, raw, screen=None):
    """Readers' hook: the seat-layout response they fetched for a price, kept as that screen's shape (or the
    label's, with screen None). Never raises."""
    try:
        hall = normalise(chain, raw)
        if hall:
            shape, _ = compact(hall)
            # no screen named: one entry per distinct shape, so a label covering two screens shows as two
            key = hall_key(cinema, hall_label, screen) if screen else hall_key(cinema, hall_label, "#" + shape_key(shape))
            with _LOCK:
                KEPT[key] = {
                    "shape": shape, "at": datetime.now(DUBAI).isoformat(timespec="seconds"), "date": date}
    except Exception:  # noqa: BLE001 - a map is a bonus; the price sample must never suffer for it
        pass


# ---------------------------------------------------------------- the occupancy sampler
class _Stop(BaseException):
    """Ends a chain's sampling. A BaseException on purpose: the readers' clients retry on `except Exception`,
    and a stop must go straight through them."""


class _Spent(_Stop):
    """The chain's request cap (or the run's deadline) is reached."""


class _Blocked(_Stop):
    """The chain said stop (401/403/429, a failed guest session)."""


ABANDON = re.compile(r"/abandon\b|cancelOrder")   # a seat-less order's own release call: may use the reserve


class Budget:
    """At most `cap` HTTP requests to one chain, each start `gap` seconds after the last, none after
    `deadline` (a clock() value). `reserve` requests are kept for releasing an order (ABANDON), so a cap hit
    mid-sample still lets the page's own abandon go out — the total stays within `cap`."""

    def __init__(self, cap=MAX_REQ, gap=GAP_S, clock=time.monotonic, sleep=time.sleep, deadline=None, reserve=0):
        self.cap, self.gap, self.used, self._last = cap, gap, 0, None
        self.clock, self.sleep, self.deadline, self.reserve = clock, sleep, deadline, reserve

    def can(self, n=1, release=False):
        return self.used + n <= self.cap - (0 if release else self.reserve)

    def late(self):
        return self.deadline is not None and self.clock() > self.deadline

    def wait(self):
        if self._last is not None:
            d = self.gap - (self.clock() - self._last)
            if d > 0: self.sleep(d)
        self._last = self.clock()

    def spend(self, n=1):
        self.used += n


_REDIRECT = (301, 302, 303, 307, 308)


class _Metered:
    """Wraps a requests / curl_cffi session. Every HTTP request — each redirect hop included, followed here
    with allow_redirects=False because curl_cffi never fills `history` — is refused past the cap or the
    deadline (_Spent), waits for the gap, and is counted. A 429 stops the chain at once (_Blocked)."""

    def __init__(self, session, budget, reserve_for=None):
        self._s, self._b, self._rel = session, budget, reserve_for

    def _one(self, method, url, **kw):
        release = bool(self._rel and self._rel.search(url))
        if self._b.late() or not self._b.can(1, release):
            raise _Spent(url)
        self._b.wait()
        self._b.spend(1)
        r = self._s.request(method, url, allow_redirects=False, **kw)
        if getattr(r, "status_code", None) == 429:
            raise _Blocked(f"429 {url}")
        return r

    def request(self, method, url, **kw):
        follow = kw.pop("allow_redirects", True)
        r = self._one(method, url, **kw)
        for _ in range(10):
            loc = (getattr(r, "headers", None) or {}).get("location") or (getattr(r, "headers", None) or {}).get("Location")
            if not follow or r.status_code not in _REDIRECT or not loc:
                return r
            url = urljoin(str(r.url or url), loc)
            if r.status_code in (301, 302, 303) and method != "HEAD":
                method = "GET"
                for k in ("data", "json", "params"):
                    kw.pop(k, None)
            else:
                kw.pop("params", None)
            r = self._one(method, url, **kw)
        return r

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def __getattr__(self, k):
        return getattr(self._s, k)


class _Direct:
    """A reader client's get() with no retry of its own, over a metered curl_cffi session (VOX, Roxy)."""

    def __init__(self, metered, impersonate="chrome"):
        self.s, self.imp = metered, impersonate

    def get(self, url, **kw):
        kw.setdefault("timeout", 30)
        return self.s.get(url, impersonate=self.imp, **kw)


def _json(r):
    try:
        return r.json() if r is not None and r.status_code == 200 else None
    except ValueError:
        return None


def _sampler(chain, budget):
    """fn(show) -> raw layout | None for one chain, on the reader's own session setup, token and helpers.
    Returns (fn, cost) where cost() is what the next sample may take in requests, or None (no seat map).
    Polite's own retries are bypassed (the metered session is called directly): a 429 is a stop."""
    if chain == "star":
        from readers import star
        from readers.common import Polite
        http = Polite(gap=0, headers={"Accept": "application/json", "Authorization": star.TOKEN})
        m = _Metered(http.s, budget)

        def fn(show):
            r = m.get(f"{star.BASE}/seat-layout/{show['_sid']}", timeout=30)
            if r.status_code in (401, 403):
                raise _Blocked(f"seat-layout {r.status_code}")
            return _json(r)
        return fn, lambda: 1
    if chain == "cineroyal":
        from readers import cineroyal
        from readers.common import Polite
        m = _Metered(Polite(gap=0).s, budget)
        warm = {"done": False}

        def fn(show):
            cref, sref, day, t, pretty = show["_sid"].split("|", 4)
            if not warm["done"]:   # the same-origin GET that sets the session cookie, as the reader does
                warm["done"] = True
                m.get(cineroyal.BASE + "/home/nowShowing", timeout=30)
            r = m.post(cineroyal.BASE + "/home/getSeatsByScreenRef", timeout=30,
                       data=json.dumps({"screenRefId": int(sref), "cinemaRefId": int(cref), "showDate": day, "showTime": t}),
                       headers={"Content-Type": "application/json;charset=UTF-8", "Origin": cineroyal.BASE,
                                "Referer": f"{cineroyal.BASE}/home/chooseScreen?prettyUrl={pretty}"})
            return _json(r)
        return fn, lambda: 1 if warm["done"] else 2
    if chain == "novo":
        from readers import novo
        from readers.common import Polite
        m = _Metered(Polite(gap=0).s, budget)

        def fn(show):
            cid, sid = show["_sid"].split("|", 1)
            return _json(m.get(f"{novo.BOOKING_API}/seat-layout/cinemas/{cid}/sessions/{sid}",
                               params={"country_id": 2, "channel": "web"}, timeout=30))
        return fn, lambda: 1
    if chain == "cinemacity":
        from readers import cinemacity
        from readers.common import Polite
        m = _Metered(Polite(gap=0).s, budget)

        def fn(show):
            uuid = cinemacity._session_uuid(show.get("book"))
            if not uuid:
                return None
            return _json(m.post(f"{cinemacity.BOOKING}/api/launch/seatpreview/{uuid}", timeout=30,
                                json={"requestData": None, "circuitId": 0, "selectedLanguageCulture": "en-US"},
                                headers={"Accept": "application/json", "Content-Type": "application/json"}))
        return fn, lambda: 1
    if chain == "reel":
        from readers import reel
        pc = reel._PriceClient()
        pc._time = type("_NoGap", (), {"monotonic": staticmethod(time.monotonic), "sleep": staticmethod(lambda s: None)})
        pc.s = _Metered(pc.s, budget, reserve_for=ABANDON)
        budget.reserve = max(budget.reserve, 1)
        state = {"login": None}

        def fn(show):
            if state["login"] is None:
                state["login"] = pc.login() or "ok"
            if state["login"] != "ok":
                raise _Blocked(state["login"])
            cinema_id, session_id, exp, screen = show["_sid"].split("|", 3)
            out = {}
            pc.on_layout = lambda body: out.setdefault("raw", body)
            try:
                pc.sample(cinema_id, session_id, exp, screen)
            except reel._SampleError:
                return None
            finally:
                pc.on_layout = None
            return out.get("raw")
        return fn, lambda: 3 if state["login"] else 4   # (guest login) + cookie + layout + cancel
    if chain == "vox":
        from readers import vox
        from curl_cffi import requests as cr
        client = _Direct(_Metered(cr.Session(), budget, reserve_for=ABANDON), vox.UA_IMPERSONATE)
        budget.reserve = max(budget.reserve, 1)

        def fn(show):
            out = {}
            try:
                vox._sample_prices(client, show["book"], on_layout=lambda html: out.setdefault("raw", html))
            except vox._Blocked as e:
                raise _Blocked(str(e))
            return out.get("raw")
        # booking + its redirect, seats/fetch + its redirect, seats (up to 3 tries), abandon (from the reserve)
        return fn, lambda: 9   # measured live: ~9 per sample with every redirect counted
    if chain == "roxy":
        from readers import roxy
        from curl_cffi import requests as cr
        client = _Direct(_Metered(cr.Session(), budget), roxy.UA_IMPERSONATE)

        def fn(show):
            r = client.get(show["_sid"])
            if r.status_code in (401, 403):
                raise _Blocked(f"seat-selection {r.status_code}")
            return r.text if r.status_code == 200 else None
        return fn, lambda: 1
    return None


def _start(show):
    return datetime.strptime(f"{show['date']} {show['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=DUBAI)


def show_key(show):
    return "|".join(str(show.get(k) or "") for k in ("cinema", "film", "date", "time", "hall_label"))


NEEDS_SID = ("star", "cineroyal", "novo", "reel", "roxy")


def pick(shows, now, recent=None):
    """The shows to sample, per chain: starting within (now, now + 3 h], with what the chain needs to read the
    seat map, not sampled in the last RESAMPLE_MIN minutes; one cinema after another (round robin), each
    cinema's soonest first — so a capped chain covers its cinemas before a second show of one."""
    recent = recent or {}
    end = now + timedelta(hours=WINDOW_H)
    by_chain = {}
    seen = set()
    for s in shows:
        chain = s.get("_chain")
        if chain not in SUPPORTED:
            continue
        if chain in NEEDS_SID and not s.get("_sid"):
            continue
        if chain in ("vox", "cinemacity") and not s.get("book"):
            continue
        try:
            st = _start(s)
        except (KeyError, ValueError):
            continue
        if not (now < st <= end):
            continue
        k = show_key(s)
        if k in seen:
            continue
        seen.add(k)
        if fresh(recent.get(k), now, RESAMPLE_MIN):
            continue
        by_chain.setdefault(chain, {}).setdefault(s["cinema"], []).append((st, s))
    out = {}
    for chain, cins in by_chain.items():
        queues = [sorted(v, key=lambda t: t[0]) for _, v in sorted(cins.items())]
        order = []
        while any(queues):
            for q in queues:
                if q: order.append(q.pop(0)[1])
        out[chain] = order
    return out


def sample(shows, now, recent=None, samplers=None, budget_for=None, deadline_s=RUN_BUDGET_S):
    """Read the seat map of each picked show, chains side by side, each within its Budget; no request starts
    after deadline_s. Returns ({show key: {"free", "total", "at", "shape", "st", "best"}},
    {chain: {"requests", "sampled", "picked", "error"}})."""
    plan = pick(shows, now, recent)
    results, report, lock = {}, {}, threading.Lock()
    stop_at = time.monotonic() + deadline_s
    budget_for = budget_for or (lambda chain: Budget(deadline=stop_at))

    def run(chain, todo):
        budget = budget_for(chain)
        rep = {"requests": 0, "sampled": 0, "picked": len(todo), "error": None}
        try:
            made = (samplers or {}).get(chain) or _sampler(chain, budget)
            if made is None:
                return
            fn, cost = made
            cost = cost if callable(cost) else (lambda c=cost: c)
            for show in todo:
                if not budget.can(cost()) or time.monotonic() > stop_at:
                    break
                try:
                    raw = fn(show)
                except _Spent:
                    break
                except _Blocked as e:
                    rep["error"] = f"stopped: {e}"[:160]
                    break
                except Exception as e:  # noqa: BLE001 - one show's failure is that show's
                    rep["error"] = f"{type(e).__name__}: {e}"[:160]
                    continue
                hall = normalise(chain, raw)
                if not hall:
                    continue
                shape, st = compact(hall)
                with lock:
                    results[show_key(show)] = {**counts(hall), "at": datetime.now(DUBAI).isoformat(timespec="seconds"),
                                               "shape": shape, "st": st, "best": best_seat(hall)}
                rep["sampled"] += 1
        except _Stop as e:
            rep["error"] = f"stopped: {e}"[:160]
        except Exception as e:  # noqa: BLE001 - a chain's sampler failing costs that chain only
            rep["error"] = f"{type(e).__name__}: {e}"[:160]
        finally:
            rep["requests"] = budget.used
            with lock:
                report[chain] = rep

    threads = [threading.Thread(target=run, args=(c, t), daemon=True) for c, t in plan.items()]
    for t in threads: t.start()
    for t in threads: t.join(max(0.0, stop_at + 45 - time.monotonic()))   # one request's timeout past the deadline
    with lock:
        return dict(results), {c: dict(r) for c, r in report.items()}


def _parse_at(at):
    """An ISO time as an aware datetime (naive = Dubai), or None."""
    try:
        t = datetime.fromisoformat(at)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=DUBAI)


def fresh(entry, now, minutes=FRESH_MIN):
    """True when an occupancy entry was sampled less than `minutes` before `now` (a sample stamped up to five
    minutes after `now` counts: the run's `now` is its start, the sample is stamped when it is read)."""
    at = _parse_at((entry or {}).get("at"))
    if at is None:
        return False
    now = now if now.tzinfo else now.replace(tzinfo=DUBAI)
    return timedelta(minutes=-5) <= now - at < timedelta(minutes=minutes)
