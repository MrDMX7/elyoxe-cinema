# Novo Cinemas UAE — probe notes

Site: https://uae.novocinemas.com — Next.js (App Router) app. The rendered HTML/RSC
payload has no visible JSON for showtimes; `read_network_requests` only shows static
asset loads (`_next/static/...`) because the data fetch happens client-side via
`fetch`/`XHR`, which that tool doesn't log. Found the real endpoints by monkey-patching
`window.fetch` and `XMLHttpRequest.prototype.open` in the browser pane and clicking a
date tab on a movie page:

```js
window.fetch = function(...args){ window.__calls.push(args[0]); return origFetch(...args) }
```

## Endpoints (all GET, JSON, no auth/cookies required)

Base: `https://uae-api.novocinemas.com/api/home`

- **`/cinemas?country_id=2&channel=web`** — all 6 live UAE sites. Fields used:
  `id`, `name`, `name_ar`, `lat`, `long`, `address` (always `""` in practice —
  had to hardcode city per mall, see `_CITY_OVERRIDE` in `readers/novo.py`).
  `country_id=2` = UAE (confirmed empirically; no country-list endpoint found).
- **`/movies?country_id=2&channel=web`** — `data.movies[]`, one entry per film
  Novo is showing or has flagged (`movie_is_coming_soon` is `true` even for films
  currently in cinemas — don't use it to filter; just try every movie against the
  sessions endpoint and skip the ones with no sessions on the requested dates).
  Fields used: `movie_id`, `movie_title`, `movie_rating`, `movie_duration` (minutes),
  `language.lang_name` (present on maybe 2/20 films; otherwise we regex the
  `(Language)` suffix some titles carry, e.g. "I'M Game (Malayalam)").
- **`/sessions/{movie_id}/date/{YYYY-MM-DD}?cinemaId=null&languageId=&timing=&formatId=&country_id=2&channel=web&v=2`**
  — showtimes for one film on one date, grouped by
  `"{cinema name}~{cinema id}~{bool}~{cinema name (Arabic)}"` keys. A film not
  playing that day returns `{"success": false, "message": "No sessions found"}`
  (HTTP 400) — treated as "skip", not an error.
  Each session: `show_time` ("03:30 PM"), `experience` ("2D"/"3D" — this small
  chain has no IMAX/4DX/premium screens right now, everything maps to hall
  `Standard`), `cinemaId`, `session_id`, `sessionDisabled`, `capacity`.

No pagination, no API key, no rate-limit header observed; reader uses `Polite(gap=1.0)`
(~1 req/s) same as every other chain.

## Prices — live since 2026-09-26 (Task 1c), no seat hold

The seat-selection route (`/seat-selection/cinema/{cinemaId}/session/{sessionId}`) loads its data
with a plain unauthenticated GET, found in the route's chunk (fetched from the page HTML):

- **`GET /api/booking/seat-layout/cinemas/{cinemaId}/sessions/{session_id}?country_id=2&channel=web`**
  — `data.areas[]` = `{name, areaCategoryCode, priceInCents, taxInCents, ticketTypeCode,
  ticketDescription}`. The page prints each area header as ``${name} (AED ${priceInCents/100})``,
  so `priceInCents/100` is the displayed fare (e.g. Buhairah COOL = 36.75). Fired on page load,
  before any seat click; no login and no guest form (the guest form only appears when the visitor
  clicks a time on the movie page — the API itself doesn't need it).
- Also there: `GET /api/booking/ticket-price/cinemas/{cid}/sessions/{sid}` (raw Vista ticket types:
  18 rows incl. bank/loyalty/promo tickets) — not used, the seat-layout areas are the headline fares.

`cinemaId` is the numeric `cinemaId` on each session (9 = Buhairah), not the Vista code. The reader
samples one session per cinema × `experience` per run, at least an hour away; a failure leaves that
hall `None`. Prices seen 2026-09-26 (AED): BAS Mall COOL 42.50 / COOL PRIME 50 / EDGE 55; Buhairah
COOL 36.75; Manar Mall 40 / 50 / 55; Mega Mall and Sahara Centre 40 / 50 / 60. Dragon Mart had no
sessions in the window.

## Review fixes (2026-09-26)

- `/sessions` failures are counted; more than half failing (anything but the normal
  "No sessions found" 400) raises `RuntimeError`, as does zero shows.
- `experience` is the projection format ("2D"/"3D"), not the hall: plain formats map to
  `Standard`, known hall words (IMAX, 4DX, 7 Star/Sky/VIP, Suites, Kids, Theatre) map by keyword,
  anything else is `OTHER` — never silently Standard. The 7STAR/IMAX/SKY halls in halls.yaml are at
  sites not in the current 6-cinema UAE list (IMG, Festival City…), so none appear today.
- Show date = calendar date of the start (`isMidnightShow` after-midnight shows move to the next
  day); "today" is Asia/Dubai; `film_lang` from a title's `(…)` suffix only when it is a language.

## Hall mapping

Observed `experience` values so far: `2D` only (checked several animated/family
titles for `3D` — none currently scheduled). `_hall_for()` in `readers/novo.py`
keyword-matches imax/4dx/screenx/gold/vip-platinum-lux-sky/suite/kid/theatre/max
and falls back to `Standard`; `hall_label` always keeps the raw `experience` string
(`"2D"`, `"3D"`, …) so nothing is lost if the API's vocabulary changes.

## Cities

`/cinemas` has 6 sites: Sahara Centre & Mega Mall & Buhairah Centre (all Sharjah),
Manar Mall (Ras Al Khaimah), BAS Mall - Baniyas (Abu Dhabi), Dragon Mart (Dubai).
`common.city_of()` can't place "Manar Mall", "BAS Mall - Baniyas", "Buhairah Centre"
or "Dragon Mart" from name text alone (not in `_CITY_WORDS`), so `readers/novo.py`
carries a small `_CITY_OVERRIDE` dict for those four and falls back to `city_of()`
for the rest.

## `book` URL

No stable per-session deep link was confirmed (would need the booking-flow probe
above). `book` points at the movie detail page,
`https://uae.novocinemas.com/movies/{movie_id}/{TITLE-SLUG}` (slug built the same
way the site's own links are, e.g. `/movies/11493/SACRIFICE`), which is a real,
verified-live URL that lets a user pick the exact showtime themselves.
