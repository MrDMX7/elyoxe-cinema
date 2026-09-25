# elyoxe.com/cinema — design

Owner's decisions, 2026-09-25 (see memory `project_elyoxe_cinema`):
all UAE from day one · data from each chain's own booking system · a mixed home (your city + your card,
week's films with verdicts, a light "on now" strip) · live and indexable · name «سينما» at `/cinema`
(+ `/en/cinema`) · verdicts in light Emirati Arabic.

## Why it beats cinemauae.com
cinemauae.com: 79 cinemas, 7 chains, showtimes, English only. It has no seat-class prices, no card
discounts, no price after discount, no explanation of premium halls, no verdict. Those five are this
product.

## Shape of the data (one source of truth)
`data/latest.json`, rebuilt by `refresh.py`:

```
{ "generated": ISO, "chains": {chain: {"ok": bool, "at": ISO, "error": str|null}},
  "cinemas": {cid: {chain, name, name_ar, city, mall, address, maps, halls:[...]}},
  "films":   {fid: {title, title_ar, lang, rating(PG13…), runtime, genres, poster, tmdb, imdb, rt, verdict}},
  "shows":   [{cinema: cid, film: fid, date: "YYYY-MM-DD", time: "HH:MM", hall: "Standard|MAX|IMAX|4DX|GOLD|THEATRE|SUITES|…",
               hall_label: str, prices: [{seat: str, aed: float}] | null, book: url}] }
```

Each chain reader (`readers/<chain>.py`) exposes `fetch(days=2) -> {"cinemas": [...], "shows": [...]}`
in that shape, with raw film titles; `normalize.py` merges films across chains (title slug + year +
language), `enrich.py` adds TMDB (Arabic title, poster, genres) and OMDb (IMDb, RT). A reader that
fails leaves the chain's previous shows in place, marked stale with its time.

Prices: read from the chain's booking API where it exposes them without a login or a held seat.
Where a chain only shows a price after seat selection, the reader stores one sampled price per
cinema × hall × seat class per day (`prices` on every show of that class), never more requests than
a person clicking through would make.

Discounts: `discounts.yaml`, maintained by hand — per card (fazaa, esaad, homat, and banks) per chain:
percent or BOGO, halls excluded, conditions (box office only, max tickets, days), source URL, checked
date. The page computes price-after-discount itself.

Verdicts: `verdicts/<fid>.json` — `{"verdict": "yes|mixed|skip", "ar": "two lines, light Emirati", "en": …,
"basis": "RT 91% · CinemaScore A-"}`; written once per new film (by Claude), hand-editable, never
overwritten by the job.

## Pages (static, `build.py` → `out/cinema/…`, `out/en/cinema/…`)
- `/cinema/` — home: city + card picker (localStorage), "on now" strip (next 2 h, from the day's
  JSON, client side), grid of the week's films with verdict, rating and "cheapest for you tonight".
- `/cinema/<city>/` — every cinema and film in the city (8 cities).
- `/cinema/<city>/<cinema>/` — halls explained (what VIP is called there and what's in it), prices
  per hall/seat, cards accepted, today's schedule, map.
- `/cinema/film/<fid>/` — synopsis, ratings, verdict, then per city: cinemas, halls, prices
  before/after your card, showtimes, book link.
- `/cinema/cards/<card>/` — which cinemas take it, how much, conditions, price examples.
- `/cinema/halls/` — the premium halls of every chain explained (GOLD, THEATRE, IMAX, 4DX, SUITES…).
- sitemap with hreflang pairs; JSON-LD `Movie`, `MovieTheater`, `ScreeningEvent`, `FAQPage`.

Identity: the /tools look (`/tools/assets/base.css`, paper/ink/saffron, Plex, no radius/shadow) plus
`cinema.css`. Every verified number in Plex Mono. Arabic in the root, English mirror.

Client script `cinema.js`: reads city + card, loads `/cinema/data/<city>.json` (small per-city slice),
rewrites price cells to after-discount, fills "on now" and "cheapest for you".

## Serving and refresh
- Own repo `saas/cinema`; published to the tools bucket under `cinema/` and `en/cinema/` only
  (its own `s3 sync --delete` limited to those prefixes; tools' sync is limited to its own).
- CloudFront: add `/cinema*` and `/en/cinema*` behaviors to the tools origin (idempotent script).
- Refresh 3×/day. Runner chosen by the probe: GitHub Actions if the chains answer datacenter IPs;
  otherwise the Fold (residential IP, always on) via cron. HTML cached 5 min, data 10 min.
- Failure: `ok:false` per chain + notify the owner; the page shows "updated X h ago" per chain.

## Phase 0 — probe (first, before the build depends on it)
For each of the 7 chains: can showtimes and prices be read without login? From which endpoint? Rate
limit? A reader + a fixture from a real response. A chain that cannot be read ships with showtimes
from its public pages and "price at the box office" until solved — never an invented number.

## Out of scope for v1
Accounts, booking inside our site, social sentiment scraping, push alerts, paid anything.
