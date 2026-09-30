"""«كم بتكلفني الطلعة؟» (R4 #298): the ticket's ticket-count stepper and its total after the card. No page of its
own, and no data file: kit/ticket.py always writes the slot (<div data-tk-qty hidden>, empty server-side — the
stepper needs a tap, so a no-script visitor keeps just the seats table above it); this module only registers the
lazy chunk (src/js/tkqty.js) on every page kind that can hold a ticket, so the always-loaded bundle carries none
of its weight (build.py's JS_WARN_GZ guard, the same reasoning pages/seats.py's seatmap.js chunk already follows)."""
from site_kit import Plugin

LAZY_JS = ("tkqty",)
KINDS = ("home", "city", "cinema", "film")


def register(site):
    return Plugin(page_js={k: ("tkqty",) for k in KINDS})
