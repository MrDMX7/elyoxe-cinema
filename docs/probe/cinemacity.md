# Probe notes — Cinema City UAE (cinemacity.ae)

Date probed: 2026-09-25. Site: https://www.cinemacity.ae (confirmed via built-in browser —
title "Luxury Cinemas | Experiences, Locations & Movies — Cinemacity", FB/IG
`cinemacityuae`). This is a **different brand** from the old "Cinema City" mall list
implied by generic naming (Marina Mall, Bawabat Al Sharq, Dragon Mart etc. belong to
other chains) — the real, current Cinema City UAE network is six sites:

| code    | name                     | mall                 | city      |
|---------|--------------------------|-----------------------|-----------|
| G01IH   | Cinemacity AlQana        | AlQana                | abu-dhabi |
| G0FO1   | Cinemacity Starlight     | Marina Mall           | abu-dhabi |
| G00YW   | Cinemacity Fountain Views| The Dubai Mall        | dubai     |
| X0FR7   | Cinemacity Arabian Centre| Arabian Centre Mall   | dubai     |
| G01PB   | Cinemacity Rahmania      | Rahmania Mall         | sharjah   |
| X110K   | Cinemacity Zero 6 Mall   | Zero 6 Mall           | sharjah   |

Discovered by browsing `/our-locations/` (lists all 6 under Abu Dhabi / Dubai / Sharjah
headings) and confirmed via `/page-data/our-locations/<slug>/page-data.json`, whose
`page.parent.childPages[].relatedEntity.id` lists all 6 Vista theater codes in one place.
Addresses were scraped from each location page's "How to find us" block and hardcoded
in `readers/cinemacity.py::CINEMAS_RAW` (venue data is stable; re-scraping HTML on every
`fetch()` call would be fragile and slow). No lat/lng or Google Maps link was found in
any JSON payload or as a plain `<a href>` (the "Get directions" control is JS-driven) —
left as `None`, allowed by the schema.

## The API

The Gatsby front-end calls a JSON API at:

```
https://www.cinemacity.ae/api/gatsby-source-boxofficeapi/...
```

`gatsby-source-boxofficeapi` is a Gatsby build-time data-source plugin name, not a
third-party vendor — this is Cinema City's own public API, served from their own domain.
**No auth, no cookies, no referrer needed** — confirmed with a plain `curl` (no browser
session) getting a 200 with full data. Standard `User-Agent` sent regardless out of
politeness.

### Theaters / cinema list
No dedicated `/theaters` endpoint (404s). The 6 codes come from `/our-locations/`
page-data as above, or from `participatingTheaters?movieIds=<id>` for any one movie
(e.g. `?movieIds=1000036867` → `["X0FR7","X110K","G00YW","G01IH","G01PB","G0FO1"]`).

### Schedule (shows)
```
GET /api/gatsby-source-boxofficeapi/schedule
    ?from=2026-09-25T03:00:00
    &to=2026-09-27T03:00:00
    &includeAllMovies=true
    &theaters={"id":"G01IH","timeZone":"Asia/Dubai"}
```
One call per cinema covers the **whole date window** (days=2 → one 48h call per cinema,
not one call per day) — `from`/`to` use a 03:00 day boundary so late shows past midnight
land under the correct calendar date, matching what the site itself sends. Response:
```json
{"G01IH": {"schedule": {"<movieId>": {"2026-09-25": [ {show...}, ... ], "2026-09-26": [...] }},
           "moviesTags": {...}, "showtimesDates": [...]}}
```
Each show object: `id`, `startsAt` (ISO local time, no offset), `tags` (array — hall,
language, service tags, see below), `isExpired`, `occupancy.rate`, `screen.name`,
`data.ticketing` (array of `{urls, type, provider}` — `provider:"default"` points at
`booking.cinemacity.ae`, `provider:"relay"` at `relay.mvtx.us`; the reader prefers
`default`).

### Movie metadata
```
GET /api/gatsby-source-boxofficeapi/movies?basic=false&castingLimit=3&ids=<id>&ids=<id>...
```
Batched (25 ids per call in the reader, well under any practical URL-length limit).
Gives `title`, `certificate` (rating, e.g. `"PG-13"` — reader strips the hyphen to match
the `PG13`-style shape in the brief), `runtime` (**seconds**, not minutes — divide by 60),
`genres`, cast/crew. No explicit language field on the movie itself; language comes from
the per-show `tags` instead (see below).

## Hall / tag vocabulary

Tags observed on real showtimes across all 6 cinemas (union):
```
Auditorium.Comfort.LuxurySeats        Auditorium.Comfort.ReservedSeating
Auditorium.Experience.DolbyAtmos      Auditorium.Experience.InfinityVision
Auditorium.Experience.PLF             Format.Projection.Digital
Format.Projection.Imax                Internal.Data.AlmostSoldOut
Localization.Language.Arabic|English|Hindi|Telugu
Showtime.Experience.CinemaCityArthouse
Showtime.Restriction.15Plus|18Plus|21Plus|Adults
Showtime.Service.VIP
```
Only `X110K` (Zero 6 Mall, Sharjah) had `Format.Projection.Imax` — matches the site's
own claim "Sharjah's ONLY IMAX Cinema". Mapped to `common.HALLS` by priority (first
match wins), raw tag kept in `hall_label`:

| tag                                              | hall     | hall_label     |
|---------------------------------------------------|----------|----------------|
| `Format.Projection.Imax`                          | IMAX     | IMAX           |
| *(none seen)* `*4DX*`, `*ScreenX*`, `*Kids*`, `*Suite*` | 4DX/SCREENX/KIDS/SUITES | (matched text) |
| `Showtime.Service.VIP`                            | VIP      | VIP            |
| `Auditorium.Experience.PLF`                        | MAX      | PLF            |
| `Auditorium.Experience.InfinityVision`             | MAX      | InfinityVision |
| `Auditorium.Comfort.LuxurySeats`                   | GOLD     | Luxury Seats   |
| `Showtime.Experience.CinemaCityArthouse`           | OTHER    | Arthouse       |
| *(no matching tag)*                                | Standard | Standard       |

`film_lang` is read from whichever `Localization.Language.*` tag is present on the show
(first match).

## Prices — why `null`

Every show's `data.ticketing[].urls` points at `https://booking.cinemacity.ae/launch/ticketing/<uuid>`,
which redirects to a Vista e-commerce widget (`booking.cinemacity.ae`). Followed one link
in the browser pane to check: it lands on a **Login / Continue as Guest** screen
(`https://booking.cinemacity.ae/login/...`) — no ticket-type or price is shown yet at
that point. Continuing (as guest) moves into session/seat selection, where Vista widgets
place a seat/session hold as soon as a seat or ticket-type quantity is confirmed, before
any payment step. Per the binding rule ("only from endpoints that do NOT place a seat
hold"), the reader does **not** proceed into that flow and does not log in or enter any
personal details. `prices` is therefore always `None` for this chain. No separate
public price-list endpoint was found on `cinemacity.ae` itself (some malls' cinema pages
have a "Pricing" link but it resolves to a static content page, not fetched here since it
isn't per-showtime pricing).

## Rate limiting / politeness

`readers/common.Polite` is used with the default 1 req/s gap and its built-in retry on
429/5xx. Total calls for `fetch(days=2)`: 6 (one `schedule` call per cinema, each
covering both days) + ~2-3 batched `movies` calls (≈25 ids/call) = **under 10 requests**
per run, well under "1 price call per cinema x hall x day" (there are zero price calls).

## Gotchas

- The shared built-in browser pane is used by other chains' readers in parallel — always
  pass an explicit `tabId` when probing, don't assume the active tab.
- `movies?ids=...` runtime is in **seconds**; the fixture/reader divides by 60 and rounds.
- `certificate` values seen: `G`, `PG-13`/`PG-15` (hyphenated), `15+`, `18+` — reader
  strips hyphens/spaces only, doesn't otherwise normalize.
- Booking links use two providers per show (`default` → booking.cinemacity.ae, `relay` →
  relay.mvtx.us); the reader always prefers `default` when present.
