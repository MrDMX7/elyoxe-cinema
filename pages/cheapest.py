"""«وين أرخص؟» (R4 §299): on a film page, a compact table comparing this film across the visitor's city's other
cinemas — cinema, hall, the cheapest price after their card, the soonest upcoming show at that price. No data
file and no server-rendered rows: everything the table needs (cinema, hall, price, time) is already in the
schedule pages/_core/film.py renders, so src/js/cinecompare.js reads that DOM instead of shipping it twice.
This module is only the wiring: the lazy chunk, its stylesheet, and the film page's own copy of it.

No page of its own; pages/_core/film.py writes the container (<section data-cheapest>, always empty server-side,
js-only — a no-script visitor already has every hall's price in the schedule itself)."""
from site_kit import Plugin

CSS = ("cheapest",)
LAZY_JS = ("cinecompare",)
KINDS = ("film",)


def register(site):
    return Plugin(page_js={k: ("cinecompare",) for k in KINDS})
