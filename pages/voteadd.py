"""pages/voteadd.py — round-3 follow-up (2026-09-30): entry points into /v/ «أي واحد؟» (pages/vote.py),
which was live but reachable from nowhere on the site. This module fills the ticket's own extension
point (site_kit.Kit.SLOTS["ticket.actions"]: "the ticket's actions row, after «أرسلها للقروب»") with one
button that doubles as both requested entry points:

  - the first tap on ANY ticket reads «اسأل القروب: أي واحد؟» (spec #1) and starts the pending vote
    (this show becomes its first stub);
  - once the vote already has a show queued, every OTHER ticket's same button reads «+ للتصويت»
    (spec #2) — no second button, no long-press: opening a different time's ticket already gives
    "each time's ticket" its own add action, so the toggle covers both entry points with one control.

The button is server-rendered per show (title, cinema name, time, cheapest price, the /v/ fragment's
own city.date.key.fid tuple — site.show_key_of, the same helper vote.js's Python twin already exposes)
so a no-JS visitor still gets a share-quality "أرسلها للقروب" beside it; src/js/voteadd.js is a lazy
chunk (page_js["*"], the appfeel.py/search.py pattern: async on every page kind, never in the shared
initial bundle build.py budgets -- a ticket can appear on nearly any page kind, but JS_WARN_GZ counts
only the eager bundle). It owns the click behaviour, the queue (localStorage, 2-4 shows, never a fake
tally -- WhatsApp is the ballot, same as vote.js's own comment), and the floating «التصويت (n) — أرسل»
bar. src/js/ticket.js's fillTicket() keeps this button's data-v-* attributes in step with whichever
show the ticket currently shows (a tapped time never leaves the button naming the previous one)."""
from site_kit import Plugin, esc

CSS = ("voteadd",)
LAZY_JS = ("voteadd",)

T_ASK = ("اسأل القروب: أي واحد؟", "Ask the group: which one?")


def _ticket_slot(site, lang, show):
    s = show
    cid = s["cinema"]
    city = (site.cinemas.get(cid) or {}).get("city") or ""
    key = site.show_key_of(s)
    title = site.ftitle(s["film"], lang)
    cn = site.cname(cid, lang)
    price = min((p["aed"] for p in (s.get("prices") or []) if (p.get("aed") or 0) > 0), default=None)
    label = T_ASK[0] if lang == "ar" else T_ASK[1]
    price_attr = f' data-v-price="{price}"' if price is not None else ""
    return (f'<button type="button" class="v-add" data-v-add'
            f' data-v-fid="{esc(s["film"])}" data-v-city="{esc(city)}" data-v-date="{esc(s["date"])}" data-v-key="{esc(key)}"'
            f' data-v-title="{esc(title)}" data-v-cin="{esc(cn)}" data-v-time="{esc(s["time"])}"{price_attr}>{esc(label)}</button>')


def register(site):
    return Plugin(slots={"ticket.actions": _ticket_slot}, page_js={"*": ("voteadd",)})
