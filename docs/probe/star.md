# Probe: Star Cinemas UAE

Site: https://www.starcinemas.ae (React SPA) · API: https://web-api.starcinemas.ae/api/v3/external
No login, no CAPTCHA, no Cloudflare challenge encountered. All reads below are plain `GET`s a
browser makes anonymously while browsing — nothing here holds a seat or requires an account.

## Auth

Every API call the site's own JS makes carries a **static bearer token** shipped in the public
web bundle (`https://www.starcinemas.ae/assets/index-*.js`, search for `const TOKEN=`):

```
Authorization: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbiI6Ijc1ZDAzZDQwLTJiYTQtNDk5ZC04ZGU0LTY4NTQ4ODIzZDUxNSIsImlhdCI6MTY4MjU0MTUyOX0.kutbXGZb1pQsxymG2dKqopjNcthIuYoexIVfL9RYpNY
```

This is **not** a per-user login token — it's a fixed anonymous-app token, identical for every
visitor, embedded in plaintext in public JS. Without it every `/external/*` endpoint except
`cinemas` returns `403 {"isAuthorization":true,"message":"You are not authorized"}`. `readers/star.py`
hardcodes it (with this comment) rather than scraping the bundle at run time, since it hasn't
rotated and re-scraping a multi-MB JS bundle per refresh would be worse for the site, not better.
If it ever starts 403ing, re-extract from the current `index-*.js` (`grep -o 'TOKEN="[^"]*"'`).

## Endpoints used

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /cinemas` | All 17 Star cinemas in the UAE | No auth needed even without the token. `cinema_latitude`/`cinema_longitude` are a placeholder (`21.12345`/`31.123456` and close variants) for ~11 of the 17 — not real coordinates; the reader nulls these out rather than publish them. `map_view_url` is a real Google Maps short link for every cinema. |
| `GET /now-showing-movies` (no `cinema_id`) | Every film currently on across the whole chain in one call | 37 movie ids the day we probed. Passing `cinema_id` filters to one cinema — we don't, since we want the union once. |
| `GET /movie-shows/<movie_id>` (no `cinema_id`) | Every showtime for that film, at every cinema, for the next ~6 days, in one call | This is the key trick: passing a **comma-joined `cinema_id`** list (`?cinema_id=1,2,3`) silently only returns the first cinema — it does **not** union. Omitting `cinema_id` entirely returns all cinemas (243 rows for one popular title). One call per film (~37) replaces what would otherwise be 17 x 37 ≈ 629 calls. |
| `GET /seat-layout/<ss_id>` | Full seat map + **live price** for one scheduled show (`ss_id` = `movie-shows[].ss_id`) | This is what the seat-selection screen fetches before a seat is picked — it returns every physical seat's `sst_seat_type` (seat class) and `seat_price`/`seat_net_price`, but does **not** reserve/hold anything (no `is_booking_done` flip, no timer starts). Booking a seat is a separate `POST /reserve-seats`, which we never call. ~200-230 KB per call (the full seat grid), so the reader caches one sample per `(cinema_id, hall_label)` and reuses it for every show sharing that cinema+hall, instead of calling it per show. |
| `GET /seat-types/<screen_id>` | Seat categories per screen | Returns category names/colors but **no price** — not used; `seat-layout` has both the categories and the prices in one call. |
| `GET /schedule-details/<ss_id>` | Cinema/schedule metadata | No price field either — not used. |

Endpoints seen but deliberately not used: `sign-in`, `sign-up`, `verify-otp*`, `reserve-seats`,
`release-seat*` — all login/booking actions, out of scope by the task's own rule.

## Rate limiting

We hit **zero 403s** across a full live run (1 `cinemas` + 1 `now-showing-movies` + 37
`movie-shows` + ~40 `seat-layout` calls ≈ 80 requests, `Polite(gap=2.0)`, ~137 s total). The
brief mentions a previous researcher got 403-rate-limited on `seat-types`; our run never
triggered it, but `readers/star.py` still treats any `403` from `movie-shows` or `seat-layout` as
non-fatal: it records a note (printed once at the end of `fetch()`) and leaves that film's shows
or that cinema x hall's `prices` as `null` rather than raising or guessing a number. Seat-layout
calls are capped at one per `(cinema_id, hall_label)` for the whole run — well under "one price
call per cinema x hall per day" since `days<=2` shares that single cached sample.

## Prices — how they're obtained and verified

`seat-layout/<ss_id>` returns real, per-seat-class AED prices. Cross-checked against the task
brief's Bawadi Mall reference numbers on a live call:

| Screen class (`screen_type_name`) | Seat class (`sst_seat_type`) | AED (live, 2026-09-25) |
|---|---|---|
| PREMIUM | PREMIUM | 57.75 |
| PREMIUM | PREMIUM PLUS | 68.25 |
| NORMAL | STAR SELECT | 42.00 |
| NORMAL | STAR PLUS | 47.25 |
| NORMAL | STAR VIP | 52.50 |
| SUITES | STAR PLATINUM SUITES | 84.00 (Al Ghurair Centre — Bawadi's own Suites screen wasn't sampled in this run) |
| DOLBY | DOLBY SELECT / DOLBY PLUS | 57.75 / 63.00 |

All match or are consistent with the brief's Bawadi figures (Premium 57.75, Premium Plus 68.25,
Star Select 42, Star Plus 47.25, Star VIP 52.50) — confirming `seat-layout` is the right source
and that prices genuinely vary per cinema (Suites price differs by mall).

## Hall mapping

Star's `screen_type_name` is a screen-class/format label, not one of the shared enum's big-format
names (`IMAX`/`4DX`/`MAX`) — Star doesn't run those. Observed values: `NORMAL`, `SUITES`, `KIDS`,
`PREMIUM`, `DOLBY`, `ATMOS`. Mapping used in `readers/star.py::HALL_MAP`:

- `NORMAL` -> `Standard`
- `SUITES` -> `SUITES`
- `KIDS` -> `KIDS`
- everything else (`PREMIUM`, `DOLBY`, `ATMOS`, and a handful of shows where
  `screen_type_name` was blank and the format code `mf_name`, e.g. `"2D"`, was used as a
  fallback label) -> `OTHER`, with the original Star label kept verbatim in `hall_label`.

Seat *classes* (`STAR SELECT`/`STAR PLUS`/`STAR VIP`/`PREMIUM`/`PREMIUM PLUS`/`DOLBY SELECT`/
`DOLBY PLUS`/`STAR PLATINUM SUITES`/`STAR PLATINUM FAMILY`, ...) are never used as hall names —
they only ever appear in `prices[].seat`.

## Booking link

The site keeps the selected cinema in browser state (header dropdown / `localStorage`), not in
the URL. Clicking a film card in the browser produced
`https://www.starcinemas.ae/now-showing-booking/<movie_id>/1/` regardless of which cinema was
selected — the trailing `1` looks like a fixed language id (English), not a cinema id. We could
not find a confirmed per-cinema deep link in the bundle's router in the time probed, so every
show for a given film links to this one page (`readers/star.py::_book_url`); the visitor still
has to (re)pick their cinema on that page. Flagged here rather than guessing a URL shape that
might 404.

**Update 2026-09-28 (legend W0-P4, §4.1 #33): a per-show link is confirmed.**
`https://www.starcinemas.ae/now-showing-single-show-booking/<ss_id>/<screen_id>/<movie_details_id>/<movie_id>`
opens that show's «2. Pick Seats» step (checked live in headed Chrome on four shows: Bawadi Mall SCREEN 02
29 Sep 11:45, Junction Mall DIP SCREEN 01 and 02, Mall of Al Ain SCREEN 1). The four ids are fields of each
show record the reader already fetches. `readers/star.py::_book_url` builds it when all four are positive
integers and falls back to the film-level link above otherwise.

## Coverage

All 17 UAE Star Cinemas sites returned by `/cinemas`: Abu Dhabi (National Cinema, Central Mall
KC, Grand Safeer, Al Wahda Mall, Al Raha) · Al Ain x5 (Mall of Al Ain, Bawadi Mall, Al Foah,
Barari Outlet Mall, Makani Zakher Mall — the last currently has no scheduled films) · Ajman
(Grand Mall) · Fujairah x2 (Century Mall, Dana Plaza) · Ras Al Khaimah · Umm Al Quwain · Dubai x2
(Al Ghurair Centre, Junction Mall DIP). No Sharjah site — Star simply doesn't operate one; not a
probe gap.

## Live run result (this probe)

17 cinemas, 687 raw shows over today+tomorrow (all 17 with at least one show except Makani
Zakher Mall, which has none scheduled), 100% of shows priced (0 `null`), 0 rate-limit hits.
`fixtures/star.json` is trimmed to 347 shows (cap ~24/cinema, keeping every `(hall, date)`
combination at least once) to stay well under the ~400-show fixture guidance while keeping all
17 cinemas represented.
