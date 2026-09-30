"""«سينمتي» (round3-gaps, 2026-09-30): the visitor's pinned cinemas. W3-P1 was to bind the cinema page's bookmark
(pages/_core/places.py cinema_head, `data-fav`, rendered `hidden` "until me.js binds it") and never shipped, so the
pin was invisible on the live site. No page of its own: this module only registers src/js/fav.js as a lazy chunk on
every page kind — it unhides and binds the bookmark on a cinema page, gives the board its K.rankBoost (a pinned
cinema's show first inside the same 10 minutes) and lists the pins in «قائمتي». Stored on the phone only
(localStorage «cinema.me», the key src/js/filters.js's «وين: سينمتي» already reads)."""
from site_kit import Plugin

LAZY_JS = ("fav",)


def register(site):
    return Plugin(page_js={"*": ("fav",)})
