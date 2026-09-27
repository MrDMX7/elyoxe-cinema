"""City from the network (roadmap 237): src/js/geo.js in the main bundle. No page, no data file — the /geo
answer comes from the cinema distribution itself (infra/geo.js, wired by infra/geo.py)."""
from site_kit import Plugin

JS = ("geo",)


def register(site):
    return Plugin()
