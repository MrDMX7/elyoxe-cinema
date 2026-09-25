# Probe: Cine Royal Cinemas (UAE)

Site: **cineroyal.ae** — not `cineroyalcinemas.com` (that domain doesn't resolve;
`cinemacity.ae` is a different chain entirely, don't confuse the two). Found
the right domain via web search after DNS failed on the obvious guess.

Server-rendered AngularJS 1.x app ("cinemaApp" module). There is no separate
JS bundle with the booking logic — the controller (`bookingController`) is an
inline `<script>` at the bottom of every `/home/*` page's HTML. All data
endpoints are same-origin `POST /home/<endpointName>` with a JSON string body
(`Content-Type: application/json;charset=UTF-8`), called via Angular's `$http`
with **relative** URLs, so they resolve against whatever `/home/*` path the
page is on. No public API docs, no Vista/Verso branding visible, no
authentication for anonymous browsing (auth header is only added once a user
logs in, via `$rootScope.globals.currentUser`).

## Cinemas (5, all Abu Dhabi emirate)

Confirmed from `/home/cinemas` and `/home/contact`:

| Mall | `cinemaRefId` | Area |
|---|---|---|
| Khalidiyah Mall (HQ) | 2 | Al Khalidiyah, Abu Dhabi |
| Dalma Mall | 101 | Musaffah, Abu Dhabi |
| Al Dhannah Mall | 200 | Ruwais/Gharbia, Abu Dhabi |
| Deerfields Mall | 300 | Al Bahia, Abu Dhabi |
| WTC Mall Abu Dhabi | 10000001 | World Trade Center, Abu Dhabi |

No Sharjah, Al Qana or Dubai locations under the Cine Royal brand — those
malls/chains (e.g. CinemaCity at Al Qana) are unrelated operators. No lat/lng
published on the site; `maps` is a generated Google Maps search URL from the
mall name + area text, not a scraped pin.

## Endpoints used

All require one prior same-origin `GET` in the session (sets `JSESSIONID` +
AWS ALB cookies) — a single `GET /home/nowShowing` at the start of `fetch()`
is enough for the whole run.

### `GET /home/nowShowing`
Server-rendered HTML list of every film currently showing (31 films seen live,
2026-09-25). Reader regex-extracts `(prettyUrl, FILM NAME)` pairs from
`<a href="/home/chooseScreen?prettyUrl=X" class="movie__title">NAME</a>`.

### `POST /home/getShowTimesByFilmAndShowDate`
Body: `{"prettyUrl": "heart-of-the-beast", "showdate": "25-Sep-2026",
"cinemaRefId": 0, "filmName": "HEART OF THE BEAST", "screenType": null}`
(`showdate` is `DD-Mon-YYYY`, `cinemaRefId: 0` = all cinemas, `filmName` must
match the site's own uppercase title exactly or the call 405s/fails).

Returns `{"shows": [...], "film": {...}}`. `shows` is one entry per cinema
that's playing the film that day, each with `filmShowTimeList` — one entry per
showtime, with `cinemaRefId`, `screenRefId`, `screen` (auditorium name, e.g.
`"CINEMA 1"`), `screenType` (`STANDARD` / `ROYAL PLUS` / `ROYAL CLASS` /
`ROYAL KIDS` — the brand's own 4 hall categories, no IMAX/4DX/MAX/SCREENX at
this chain), `formattedShowTime` (`"11:40PM"`), `showDate` (ISO), and
`availableSeats`. `film` carries `rating`, `length` (`"105 mins"`),
`language` (usually `null` — language is only visible in the title, e.g.
`"THE PARADISE (TELUGU)"`, so the reader regex-matches known language words
in the title as a fallback).

Rate note: this endpoint 405s if called with no gap after the warm-up `GET`
(hit this once testing manually with 0 delay); ≥1 s gap (the shared
`Polite` default) was reliable every time after that.

### `POST /home/getSeatsByScreenRef` — the price source
Body: `{"screenRefId": 7, "cinemaRefId": 2, "showDate": "2026-09-25",
"showTime": "11:40PM"}`. Returns the full seat grid for that specific
showtime: `rows`, `rowSeats` (grouped by row), each seat has `seatId`,
`rowName`/`colName`, `tierName` (e.g. `"VIP"`, `"Premium"`, `"Classic"`),
`unitPrice` (AED, float), `taxRateName`/`taxValue`, and `"selected": false`
for every seat, `internetBooked` (0/1 = sold-out marker per seat, not a hold
flag).

**Why this is safe to use as the price source:** calling it does **not**
select or reserve anything — every seat in the response comes back
`"selected": false"` regardless of how many times you call it, and the
site's own controller calls it directly from `ng-click="proceedToSeatSelection"`
just to *render* the seating chart before the customer has picked a seat.
Verified live: calling it twice in a row for the same session returns
identical `unitPrice`/`internetBooked` counts both times — no seat gets
marked booked or unavailable as a side effect. It is exactly the
"ticket-types/price list for a session" case the pricing rule allows, not a
seat-hold endpoint (a hold only happens later, via `addSeatDataToSession`,
which this reader never calls). The reader collapses the per-seat rows into
one `{tierName: unitPrice}` map and emits `prices` as
`[{"seat": tierName, "aed": unitPrice}, ...]`.

**Trap found:** this endpoint 405s unless the request carries a `Referer`
header that looks like `.../home/chooseScreen?prettyUrl=<anything>` — a plain
hotlink/CSRF guard on the URL string, unrelated to session state (confirmed:
works with a `Referer` for a *different* film than the one being priced, and
works with no prior `GET /home/chooseScreen` at all as long as the header is
present). The reader always sends `Referer: .../chooseScreen?prettyUrl=<the
film's own prettyUrl>` to stay honest about what page it's "on".

**Budget respected:** the reader groups by `(cinemaRefId, screenRefId,
showDate)` — i.e. one call per cinema × hall × day — and caches the result,
reusing the same price list for every showtime that shares a hall that day
(pricing rarely varies by showtime within a day on this chain; the tradeoff is
documented here rather than hidden).

### `POST /home/getXtertainCinemas`
Returns a 5-cinema list too (subset used for a "kids zone" widget, same 5
malls) — not used; `/home/cinemas` + `/home/contact` were the source of truth
for the cinema roster instead, since that page is the human-facing "these are
our locations" list.

## Not used / not needed
`getAllCombos`, `addComboDataToSession`, `addUserDataToSession`,
`addSeatDataToSession` — all part of the actual checkout flow (combos, seat
locking, payment). Never called by this reader.

## Blocks encountered
- Wrong domain guess (`cineroyalcinemas.com` → NXDOMAIN) cost the first probe
  attempt; `www.cineroyalcinemas.com` also doesn't resolve. Correct domain
  is `cineroyal.ae`.
- `getSeatsByScreenRef` returning 405 until the `Referer` trap above was
  found — first full run (before the fix) produced 306 shows with **zero**
  priced, silently; re-ran after the fix.
- The shared browser pane (`mcp__Claude_Browser__*`) was being used
  concurrently by other chains' agents in this session and a `navigate` call
  landed on someone else's tab (a `cinemacity.ae` page), which looked like a
  redirect but wasn't — confirmed via a direct `curl -L` that `cineroyal.ae`
  serves its own content with no redirect. Switched to plain `requests`/`curl`
  probing instead of the shared browser for this chain.

## What a fixture run looks like
`fetch(days=2)` on 2026-09-25: 31 now-showing films × 2 dates queried against
all 5 cinemas → 5 cinemas, ~300 shows, most priced (a handful of showtimes
have no seat map yet — e.g. very last-minute or newly added sessions — and
those correctly carry `"prices": null`). One warm-up `GET` + ~60
`getShowTimesByFilmAndShowDate` calls + ~1 `getSeatsByScreenRef` call per
(cinema, hall, day) combo actually seen, all at the shared 1 req/s gap.
