"""The privacy counter's client (plan §3.2 W3-P6, wired 2026-10-17): no page of its own — this module only
registers src/js/beacon.js as a lazy chunk (docs/PLUGINS.md), loaded async on every page kind through
`page_js["*"]`, so its code never lands in the shared initial bundle build.py budgets (JS_WARN_GZ). The
endpoint comes from counter.yaml (build.fill_counter); with none the chunk is inert. What it counts and what
it never stores is in beacon.js's own header and infra/counter/README.md."""
from site_kit import Plugin

LAZY_JS = ("beacon",)


def register(site):
    return Plugin(page_js={"*": ("beacon",)})
