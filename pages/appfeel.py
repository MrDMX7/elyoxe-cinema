"""r3-app («iPhone-app feel»): no page of its own — this module only registers src/js/appfeel.js as a lazy
chunk (docs/PLUGINS.md), loaded async on every page kind through `page_js["*"]`, so its code never lands in
the shared initial bundle build.py budgets (JS_WARN_GZ). See appfeel.js for what it does."""
from site_kit import Plugin

LAZY_JS = ("appfeel",)


def register(site):
    return Plugin(page_js={"*": ("appfeel",)})
