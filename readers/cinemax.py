"""Reader for Cinemax (rakcinemax.com) — one site, Al Naeem Mall, Ras Al Khaimah, 6 screens (owner 2026-11-19).

The same MITE Solutions ASP.NET platform as Al Shaab Cinema, so readers/alshaab.py reads it with this site handed in:
home page films, film-page date tabs, /movie/showsbymalls per day, the setsession link then /Seat/Seats for prices.
The old cinemaxcinemas.com is gone (parked by 2024-12, spam since); its Makani Zakher (Al Ain) site is Star's now.
Screen P1 sells two «NORMAL» categories (36.75 and 42.00), which is why prices are keyed on the seat category.
"""
from __future__ import annotations

from readers import alshaab

CHAIN = "cinemax"
BASE = "https://www.rakcinemax.com"
SITE = {"chain": CHAIN, "base": BASE, "brand": "Cinemax",
        "known": {"al naeem mall - ras al khaimah": ("Al Naeem Mall", "Al Naeem Mall, 100 Bin Daher St, Al Nakheel, Ras Al Khaimah, United Arab Emirates")}}


def fetch(days: int = 2, cache: dict | None = None) -> dict:
    return alshaab.fetch(days, cache, site=SITE)


if __name__ == "__main__":
    import json
    import sys

    json.dump(fetch(days=2), sys.stdout, ensure_ascii=False, indent=2)
