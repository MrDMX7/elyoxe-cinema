"""pages/venue.py — Phase 2 Task 4: "inside the mall" (docs/superpowers/specs/2026-09-27-phase2-design.md,
C «Planning» + B.46 «Snacks»). Fills two of site_kit.Kit.SLOTS (docs/PLUGINS.md has both, so no fallback
/cinemas/<id>/extras data slice is needed):

  cinema.after_halls  «المول يسكّر HH:MM» + which of today's shows end after that (malls.yaml), the
                      chain's snack combos (snacks.yaml) and any OFFICIAL card F&B discount already in
                      discounts.yaml (site.rules — never a new number), and today's double-feature pairs
                      at this cinema.
  film.double         today's double-feature pairs this film is in, at any cinema (the «فيلمين ورا بعض» tab).

The calendar/leave-by/ics side of Task 4 is client-side: src/js/plan.js (in the ticket, main bundle).

No number here is invented: a mall not in malls.yaml, or a chain not in snacks.yaml, renders nothing
(docs/superpowers/specs/2026-09-26-phase1-design.md: no invented numbers, «تقريباً» on every estimate)."""
import datetime as dt
import os

import yaml

from site_kit import CITIES, L, P, Plugin, ROOT, dates, esc, human_date, money, num

CSS = ("venue",)
JS = ("plan",)

MALLS_PATH = os.path.join(ROOT, "malls.yaml")
SNACKS_PATH = os.path.join(ROOT, "snacks.yaml")
DOW = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")   # date.weekday(): Monday = 0
GAP_MIN, GAP_MAX = 15, 45   # design C.43: film B starts 15-45 min after film A's end
FOOD_WORDS = ("الأكل", "المأكولات", "الطعام", "الوجبات")   # discounts.yaml notes that mention food, not just tickets


def _load(path, key):
    if not path or not os.path.exists(path):
        return {}
    return (yaml.safe_load(open(path, encoding="utf-8")) or {}).get(key) or {}


def load_malls(path=MALLS_PATH):
    return _load(path, "malls")


def load_snacks(path=SNACKS_PATH):
    return _load(path, "chains")


def mall_for_cinema(malls, cid):
    """(mall id, entry) the cinema is inside, else (None, None) — never guessed: a cinema id must be
    listed under that mall's own `cinemas:`."""
    for mid, m in (malls or {}).items():
        if cid in (m.get("cinemas") or []):
            return mid, m
    return None, None


def close_minutes(mall, iso_date):
    """Minutes after that date's midnight the mall closes, or None when the day isn't in `hours`
    («absent, never guessed» — a mall missing a day just isn't checked yet for it)."""
    try:
        wd = DOW[dt.date.fromisoformat(str(iso_date)).weekday()]
    except ValueError:
        return None
    t = (mall.get("hours") or {}).get(wd)
    if not t:
        return None
    h, m = t.split(":")
    n = int(h) * 60 + int(m)
    return 1440 if n == 0 else n   # "00:00" close = the end of THIS date, not its start


def show_end_minutes(s):
    """Minutes from `s`'s own date's midnight to its approximate end (site_kit.Kit.end_offset's
    convention: an end clock-time before the start one is past midnight, +24h) — None with no estimate."""
    if not s.get("ends"):
        return None
    h, m = map(int, s["time"].split(":"))
    eh, em = map(int, s["ends"].split(":"))
    start = h * 60 + m
    end = eh * 60 + em
    if end < start:
        end += 1440
    return end


def shows_past_closing(shows, mall, iso_date):
    """Today's shows (at this cinema, already filtered) that end after `mall` closes on `iso_date`."""
    close = close_minutes(mall, iso_date)
    if close is None:
        return []
    out = []
    for s in shows:
        end = show_end_minutes(s)
        if end is not None and end > close:
            out.append(s)
    return out


def _abs_minutes(iso_date, hm):
    """Minutes since an arbitrary fixed point, so two shows on different calendar dates (a 23:30 show
    and the 02:00 one after it, dated the NEXT day like the data itself dates it) compare correctly."""
    h, m = int(hm[:2]), int(hm[3:5])
    return dt.date.fromisoformat(str(iso_date)).toordinal() * 1440 + h * 60 + m


def show_span_abs(s):
    """(absolute start, absolute end|None) — end wraps past midnight the same way show_end_minutes does,
    just anchored to the real calendar instead of the show's own date alone."""
    start = _abs_minutes(s["date"], s["time"])
    if not s.get("ends"):
        return start, None
    end = _abs_minutes(s["date"], s["ends"])
    if end < start:
        end += 1440
    return start, end


def double_features(shows, gap_min=GAP_MIN, gap_max=GAP_MAX):
    """Pairs (a, b) of shows at the SAME cinema, different films, where b starts between `gap_min` and
    `gap_max` minutes after a's approximate end (design C.43) — a's end and b's start compared on the
    real calendar, so a pair spanning midnight (a dated today, b dated tomorrow) still matches. Both must
    carry an end estimate; a film never pairs with itself or another showing of itself."""
    pairs = []
    by_cin = {}
    for s in shows:
        if s.get("ends"):
            by_cin.setdefault(s["cinema"], []).append(s)
    for _, ss in by_cin.items():
        spans = [(s, show_span_abs(s)) for s in ss]
        for a, (_, a_end) in spans:
            if a_end is None:
                continue
            for b, (b_start, _) in spans:
                if b is a or b["film"] == a["film"]:
                    continue
                gap = b_start - a_end
                if gap_min <= gap <= gap_max:
                    pairs.append((a, b, gap))
    return pairs


# ---------------------------------------------------------------- rendering
def mall_section(site, lang, cid, malls):
    """«المول يسكّر HH:MM» + which of today's shows run past it. Nothing when the cinema's mall (or its
    hours for today) is not confirmed."""
    mid, mall = mall_for_cinema(malls, cid)
    if not mall:
        return ""
    close = close_minutes(mall, site.today)
    if close is None:
        return ""
    hh, mm = divmod(close % 1440, 60)
    close_txt = f"{hh:02d}:{mm:02d}" if close % 1440 else "00:00"
    mall_name = L((mall.get("ar"), mall.get("en")), lang)
    head = (f"المول يسكّر الساعة {close_txt}" if lang == "ar" else f"The mall closes at {close_txt}")
    todays = [s for s in site._by_cin.get(cid, []) if s["date"] == site.today]
    late = shows_past_closing(todays, mall, site.today)
    note = ""
    if late:
        films = sorted({site.ftitle(s["film"], lang) for s in late})
        names = ("، " if lang == "ar" else ", ").join(films[:4])
        note = (f'<p class="mall-late">{esc(names)} — {esc("يخلص بعد تسكير المول — استعمل مدخل السينما")}</p>' if lang == "ar"
                else f'<p class="mall-late">{esc(names)} — {esc("ends after the mall closes — use the cinema’s own entrance")}</p>')
    src = f' <a class="src" href="{esc(mall["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>' if mall.get("source") else ""
    chk = f' <small class="chkd">{"تحققنا" if lang == "ar" else "checked"} {esc(human_date(mall.get("checked"), lang))}</small>' if mall.get("checked") else ""
    return (f'<section class="mall-note"><h2>{esc(head)}</h2>'
            f'<p class="hint">{esc(mall_name)}{src}{chk}</p>{note}</section>')


def snacks_section(site, lang, chain):
    """Combo names + prices for this chain (snacks.yaml), then any OFFICIAL card F&B discount already
    confirmed in discounts.yaml (site.rules — read only, never a new number here)."""
    snacks = load_snacks()
    entry = snacks.get(chain) or {}
    combos = entry.get("combos") or []
    def combo_row(c):
        name = esc(L((c.get("ar"), c.get("en")), lang))
        note = c.get("note_ar") if lang == "ar" else None   # the only language this note is written in
        note_html = f'<small class="ndesc">{dates(esc(note))}</small>' if note else ""
        return (f'<tr><td>{name}{note_html}</td>'
                f'<td>{num(money(c["aed"]))} <small>{esc(L(("درهم", "AED"), lang))}</small></td></tr>')
    rows = "".join(combo_row(c) for c in combos if c.get("aed") is not None)
    body = ""
    if rows:
        head = "الأكل والمشروبات" if lang == "ar" else "Snacks and drinks"
        body += f'<table class="prices snacks"><thead><tr><th scope="col">{esc(head)}</th><th scope="col">{esc(L(("السعر", "Price"), lang))}</th></tr></thead><tbody>{rows}</tbody></table>'
        c0 = combos[0]
        body += (f'<p class="hint"><a class="src" href="{esc(c0["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>'
                 f' <small class="chkd">{"تحققنا" if lang == "ar" else "checked"} {esc(human_date(c0.get("checked"), lang))}</small></p>')
    food_rows = ""
    for card, r in (site.rules.get(chain) or {}).items():
        note = r.get("note_ar") or ""
        if any(w in note for w in FOOD_WORDS):
            food_rows += f'<li>{dates(esc(note))} <a class="src" href="{esc(r.get("source") or "")}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a></li>'
    if food_rows:
        head2 = "خصم البطاقات على الأكل" if lang == "ar" else "Card discounts on food"
        body += f'<h3>{esc(head2)}</h3><ul class="food-disc">{food_rows}</ul>'
    if not body:
        return ""
    head0 = "الأكل في " + site.h.chain_name(chain, lang) if lang == "ar" else "Snacks at " + site.h.chain_name(chain, lang)
    return f'<section class="snacks"><h2>{esc(head0)}</h2>{body}</section>'


PER_CITY = 2     # film page: this many pairings per city (earliest first), FILM_TIMES start times each
FILM_TIMES = 2
MAX_LINES = 30   # cinema page: the day's first 30 pairings of two films…
MAX_TIMES = 3    # …each with its first three start times (a busy multiplex has ~250 such lines: ~35 KB)


def group_pairs(pairs):
    """[(cinema, film A, film B, [(A's time, B's time), …])] — every pairing of the same two films at the same
    cinema on one line, times in order; lines ordered by their first pair's start."""
    g = {}
    for a, b, _gap in pairs:
        g.setdefault((a["cinema"], a["film"], b["film"]), []).append((a["time"], b["time"], a["date"]))
    out = []
    for (cid, fa, fb), ts in g.items():
        ts.sort(key=lambda t: (t[2], t[0]))
        out.append(((ts[0][2], ts[0][0]), (cid, fa, fb, [(x, y) for x, y, _ in ts])))
    return [v for _, v in sorted(out, key=lambda kv: (kv[0], kv[1][:3]))]


def _times(ts, lang, cap=MAX_TIMES):
    """The start times, isolated left-to-right (so an RTL line cannot reorder them): 11:45 → 14:00, …"""
    more = f" +{len(ts) - cap}" if len(ts) > cap else ""
    return f'<bdi dir="ltr" class="num">{", ".join(f"{esc(x)} → {esc(y)}" for x, y in ts[:cap])}{more}</bdi>'


def _pair_li(site, lang, cid, fa, fb, ts, cinema=True, cap=MAX_TIMES):
    cin = ""
    if cinema:
        c = site.cinemas.get(cid) or {}
        name = f"<bdi>{esc(site.cname(cid, lang))}</bdi>"
        cin = f' — <a href="{P(lang, c.get("city"), cid)}">{name}</a>' if c.get("city") else f" — {name}"
    arrow = " ← " if lang == "ar" else " → "
    return (f'<li><b><bdi>{esc(site.ftitle(fa, lang))}</bdi></b>{arrow}<b><bdi>{esc(site.ftitle(fb, lang))}</bdi></b> '
            f'<small>{_times(ts, lang, cap)}</small>{cin}</li>')


def _details(lang, n, items, more="", open_=False):
    head = "فيلمين ورا بعض" if lang == "ar" else "Back-to-back double feature"
    return (f'<details class="dfeat"{" open" if open_ else ""}><summary>{esc(head)} <small>({num(n)})</small></summary>'
            f'<ul>{"".join(items)}</ul>{more}</details>')


def double_feature_html(site, lang, pairs, show_cinema=True):
    """A cinema page: the day's pairings, one line per two films (earliest first, capped), collapsed — the slot
    counts against the page budget, and the schedule must never shrink for it."""
    if not pairs:
        return ""
    groups = group_pairs(pairs)
    more = ""
    if len(groups) > MAX_LINES:
        more = (f'<p class="hint">{"وفيه" if lang == "ar" else "and"} {num(len(groups) - MAX_LINES)} '
                f'{"غيرها بعد" if lang == "ar" else "more later in the day"}</p>')
    return _details(lang, len(groups), [_pair_li(site, lang, *g, cinema=show_cinema) for g in groups[:MAX_LINES]], more)


def film_double_feature_html(site, lang, pairs):
    """A film page: pairings anywhere in the country — a few per city (earliest first), each naming its
    cinema, whose own page lists that cinema's day. Open: it is the page's «فيلمين ورا بعض» tab."""
    if not pairs:
        return ""
    groups = group_pairs(pairs)
    by_city, order = {}, [c[0] for c in CITIES]
    for g in groups:
        by_city.setdefault((site.cinemas.get(g[0]) or {}).get("city"), []).append(g)
    keep = [g for city in sorted(by_city, key=lambda c: order.index(c) if c in order else len(order))
            for g in by_city[city][:PER_CITY]]
    more = ""
    if len(keep) < len(groups):
        more = (f'<p class="hint">{"والباقي في صفحة كل سينما" if lang == "ar" else "More on each cinema’s page"}</p>')
    # open: on the film page it is its own tab now (UI redesign Task 4), no longer a fold under the schedule
    return _details(lang, len(groups), [_pair_li(site, lang, *g, cap=FILM_TIMES) for g in keep], more, open_=True)


def register(site):
    malls = load_malls()

    def after_halls(kit, lang, cid):
        chain = kit.cinemas[cid]["chain"]
        todays = [s for s in kit._by_cin.get(cid, []) if s["date"] == kit.today]
        pairs = [p for p in double_features(todays) if p[0]["cinema"] == cid]
        return (mall_section(kit, lang, cid, malls) + snacks_section(kit, lang, chain)
                + double_feature_html(kit, lang, pairs, show_cinema=False))

    def film_info(kit, lang, fid):
        todays = [s for s in kit.shows if s["date"] == kit.today]
        pairs = [p for p in double_features([s for s in todays if s["film"] == fid] + [s for s in todays if s["film"] != fid])
                 if p[0]["film"] == fid or p[1]["film"] == fid]
        return film_double_feature_html(kit, lang, pairs)

    return Plugin(slots={"cinema.after_halls": after_halls, "film.double": film_info})
