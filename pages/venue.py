"""pages/venue.py — Phase 2 Task 4: "inside the mall" (docs/superpowers/specs/2026-09-27-phase2-design.md,
C «Planning» + B.46 «Snacks»). Fills one of site_kit.Kit.SLOTS (docs/PLUGINS.md):

  cinema.after_halls  the chain's snack combos (snacks.yaml) and any OFFICIAL card F&B discount already in
                      discounts.yaml (site.rules — never a new number), each under its card's name, and
                      today's double-feature pairs at this cinema that have not started yet.

«المول يسكّر HH:MM» and the films that end after it (malls.yaml) moved into the cinema page's head (W2-P6,
MASTER-PLAN §2.4: pages/_core/places.py reads close_minutes, mall_for_cinema and shows_past_closing from here);
mall_section() stays for any other page that wants the whole block.

The film page's all-cities double feature is deleted (W0-P2, MASTER-PLAN §4.1 #14: 107 pairs, past times,
above the schedule). On the cinema page a pair leaves the list when its first film starts: the build drops
the ones already started, and the lazy chunk src/js/when.js hides the rest as the clock passes them
(`data-until`), and the whole list once none is left (`data-when-group`). when.js is generic: any page that
marks blocks with data-until / data-from and asks for the chunk gets the same behaviour (pages/seasons.py's
/kids/ does).

The calendar/leave-by/ics side of Task 4 is client-side: src/js/plan.js (in the ticket, main bundle).

No number here is invented: a mall not in malls.yaml, or a chain not in snacks.yaml, renders nothing
(docs/superpowers/specs/2026-09-26-phase1-design.md: no invented numbers, «تقريباً» on every estimate)."""
import datetime as dt
import os

import yaml

from site_kit import L, Plugin, ROOT, dates, esc, human_date, money, num, rule_state

CSS = ("venue",)
JS = ("plan",)
# the city and cinema pages' own behaviour and sheet (W2-P6): a lazy chunk and a page-scoped stylesheet, so neither
# the main bundle nor the shared sheet every page loads carries them (MASTER-PLAN §7.2). Declared here, the places'
# plug-in, because pages/core.py (the places' pages) is not W2-P6's to edit
LAZY_JS = ("when", "places-live")
PAGE_CSS = {"city": ("places-page",), "cinema": ("places-page",)}

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
    cards = {c.get("id"): c for c in (site.disc.get("cards") or [])}
    for card, r in (site.rules.get(chain) or {}).items():
        note = r.get("note_ar") or ""
        if any(w in note for w in FOOD_WORDS) and rule_state(r, site.today) == "ok":
            c = cards.get(card) or {}
            name = (c.get("name_ar") if lang == "ar" else c.get("name_en")) or c.get("name_en") or card
            say = dates(esc(note)) if lang == "ar" else f'<span lang="ar" dir="rtl">{dates(esc(note))}</span>'
            food_rows += (f'<li><b><bdi>{esc(name)}</bdi></b>: {say} <a class="src" href="{esc(r.get("source") or "")}" '
                          f'rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a></li>')
    if food_rows:
        head2 = "خصم البطاقات على الأكل" if lang == "ar" else "Card discounts on food"
        body += f'<h3>{esc(head2)}</h3><ul class="food-disc">{food_rows}</ul>'
    if not body:
        return ""
    head0 = "الأكل في " + site.h.chain_name(chain, lang) if lang == "ar" else "Snacks at " + site.h.chain_name(chain, lang)
    return f'<section class="snacks"><h2>{esc(head0)}</h2>{body}</section>'


MAX_LINES = 20   # cinema page: the day's first 20 pairings of two films still ahead…
MAX_TIMES = 3    # …each with its first three start times (a busy multiplex has ~250 such lines: ~35 KB). The block
                 # stays under the 6 KB the arrow version took: it counts against the page budget, and a heavier
                 # one would push the busiest cinemas' schedules into the plain mode that drops per-show booking links


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


def group_times(ts, lang, day, cap=MAX_TIMES):
    """The first `cap` pairs of start times, each «21:00 ثم 23:15» ("21:00 then 23:15"): two starts, in reading
    order, with no arrow to flip in an RTL line. Each pair is its own span that leaves at its first start."""
    then = " ثم " if lang == "ar" else " then "
    more = f" <bdi>+{len(ts) - cap}</bdi>" if len(ts) > cap else ""   # isolated, or an RTL line prints «5+»
    # an RTL line keeps «21:00 ثم 23:15» in reading order on its own: no arrow, so no isolate is needed. The
    # day is on the list (data-d), each pair carries only its first start: when.js reads the two together. The
    # comma between two pairs is venue.css's, drawn only between pairs still shown, so a hidden one leaves no «، ،»
    return "".join(f'<span data-until="{esc(x)}">{esc(x)}{then}{esc(y)}</span>' for x, y in ts[:cap]) + more


def _pair_li(site, lang, day, fa, fb, ts):
    then = " ثم " if lang == "ar" else " then "
    return (f'<li data-when-group><b><bdi>{esc(site.ftitle(fa, lang))}</bdi></b>{then}<b><bdi>{esc(site.ftitle(fb, lang))}</bdi></b> '
            f'<small>{group_times(ts, lang, day)}</small></li>')


def double_feature_html(site, lang, pairs, day):
    """A cinema page: `day`'s pairings still ahead, one line per two films (earliest first, capped), collapsed —
    the slot counts against the page budget, and the schedule must never shrink for it. No count in the
    summary: the client hides pairs as they start, and a number would go stale with them."""
    if not pairs:
        return ""
    groups = group_pairs(pairs)
    more = ""
    if len(groups) > MAX_LINES:
        more = (f'<p class="hint">{"وفيه" if lang == "ar" else "and"} {num(len(groups) - MAX_LINES)} '
                f'{"غيرها بعد" if lang == "ar" else "more later in the day"}</p>')
    head = "فيلمين ورا بعض" if lang == "ar" else "Back-to-back double feature"
    items = "".join(_pair_li(site, lang, day, fa, fb, ts) for _cid, fa, fb, ts in groups[:MAX_LINES])
    return f'<details class="dfeat" data-d="{esc(day)}" data-when-group><summary>{esc(head)}</summary><ul>{items}</ul>{more}</details>'


def future_pairs(kit, cid):
    """Today's pairs at `cid` whose first film has not started at build time (Kit.is_past, the build's clock)."""
    todays = [s for s in kit._by_cin.get(cid, []) if s["date"] == kit.today and not kit.is_past(s)]
    return [p for p in double_features(todays) if p[0]["cinema"] == cid]


def register(site):
    def after_halls(kit, lang, cid):
        chain = kit.cinemas[cid]["chain"]
        return snacks_section(kit, lang, chain) + double_feature_html(kit, lang, future_pairs(kit, cid), kit.today)

    # film.double is not registered (W0-P2, MASTER-PLAN §4.1 #14 and §4.2 #27): the film page has no double feature
    return Plugin(slots={"cinema.after_halls": after_halls}, page_js={"cinema": ["when", "places-live"], "city": ["places-live"]})
