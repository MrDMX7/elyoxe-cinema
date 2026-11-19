"""«عروض مجانية» (/free/ and /en/free/, owner 2026-11-19): the page itself is the app's (app/build_app.py App.free, from
data["free"] that steps/free_screenings.py writes), written after this build like the home, film and cinema pages.
This module only puts it in the sitemap, with both languages, when there is something on it."""
from site_kit import Plugin


def register(site):
    data, today = getattr(site, "d", None) or {}, getattr(site, "today", "") or ""
    live = [i for i in (data.get("free") or []) if (i.get("end_date") or i.get("date") or "") >= today]
    return Plugin(sitemap=[("free",)] if live else [])
