"""Feel (roadmap 203, 204, 138): instant pages, view transitions, icon shortcuts.

The speculation rules and the «back» view-transition type live in src/page.html's head (they must be there
before the first paint); the manifest shortcuts in src/manifest.webmanifest with their icons from
src/icons/make_shortcuts.py. This module brings the rest: src/css/transitions.css (the transitions, off under
reduced motion) and src/js/feel.js (features wait for a prerendered page to be shown; the tapped poster is
named for the morph). No page, no data file.

A prerendered page runs no script until it is shown: src/page.html loads the bundle through its «boot» loader,
which waits for prerenderingchange (lazy chunks come from the bundle, so they wait too). `data-nospec` on a link
keeps it out of both speculation rules — an escape hatch no page uses today."""
from site_kit import Plugin

CSS = ("transitions",)
JS = ("feel",)


def register(site):
    return Plugin()
