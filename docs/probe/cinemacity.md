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

## Prices — live since 2026-09-26 (Task 1c), no seat hold

The ticketing widget (`booking.cinemacity.ae`, Webedia/Boxoffice React app,
`assets/index-*.js`) has a **seat-preview** mode that opens the seat map without an order step.
Both calls are POSTs to the widget's own origin, no login, no guest form:

1. `POST /api/launch/seatpreview/{boxofficeSessionId}` body
   `{"requestData": null, "circuitId": 0, "selectedLanguageCulture": "en-US"}` →
   `dataToken`, `selectSeatsModel.seatsLayoutModel.{areas[] (number, name), rows[].seats[]
   (areaId, areaCategoryCode)}`. The `boxofficeSessionId` is the UUID in each show's `book` link
   (`/launch/ticketing/<uuid>`).
2. `POST /api/Tickets/GetTickets {"dataToken": …}` → `selectTicketsModel.groupedTicketTypes[]
   .ticketTypeModels[]` = `{displayName, areaCategoryCode, price (fils, VAT incl.), tax, isMemberTicket,
   isPackageTicket…}`. E.g. AlQana: AQ Deluxe 5000 (tax 476 → 50.00 AED incl. 5 % VAT), AQ-CLUB 6500.

Member/redemption/third-party/card-promo/loyalty tickets are skipped; the first remaining ticket per
seat area is the headline fare, named by the area (`Deluxe`, `CLUB`, `VIP`…). One sample per cinema ×
hall label per run (retried once on the next show if it fails); failures leave `None`.

The widget has Cloudflare Turnstile configured (`turnstileConfig.enabled: true`) but neither call
asked for a token. Prices seen 2026-09-26 (AED): AlQana Deluxe 50 / CLUB 65 (PLF: Deluxe 65, CLUB 75,
VIP 165; Arthouse 70); Starlight Deluxe 60 / Club 80 / VIP 200; Fountain Views Club 85, VIP recliner
150; Arabian Centre 2D 42, VIP 100; Rahmania 65; Zero 6 Deluxe 45 / Club 48, IMAX from 65 to 120.

## Review fixes (2026-09-26)

- Show date = `startsAt[:10]` (calendar date), not the API's 03:00 business-day bucket; the window
  now starts at 00:00 so today's after-midnight shows are kept.
- Hall ruling: PLF and InfinityVision → `OTHER` (label kept), LuxurySeats → `VIP`.
- `book` falls back to the locations page if a show has no ticketing link; city is validated;
  zero shows raises `RuntimeError`.

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
