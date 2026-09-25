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

## Prices — deliberately not fetched (`"prices": null` on every show)

Could not find a ticket-types/price-list endpoint that doesn't require entering the
seat-selection step of the booking flow. Things tried:

- Guessed a dozen GET paths off the same `uae-api.novocinemas.com/api/home` and
  `/api/booking` bases (`/tickettypes/{session_id}`, `/session/{id}`,
  `/price/{id}`, `/ticket-types/{id}`, …) — all 404.
- Wanted to click through an actual "Book Now" → seat map in the browser pane to
  watch the real request, but the browser pane is shared across the 7 parallel
  chain agents in this task and hit its tab cap while another chain's session was
  mid-checkout on `uae.voxcinemas.com` — didn't want to risk touching another
  agent's in-flight booking, so stopped there rather than force a new tab.
- Novo's cinema records carry a `vista_id` per site and movies carry a
  `vista_Film_id`/`vista_hOFilmCode_id` — strongly suggests a Vista Cinema
  (Veezi/Vista Insight) backend, where ticket-type pricing is normally returned
  by a "GetTicketTypes"-style call keyed to a *held* session, not a free GET.

Given the binding rule (no price call that places a seat hold), every show ships
with `"prices": null`. Re-probe candidate: watch the booking flow at
`uae.novocinemas.com/movies/{id}/{TITLE}` → pick a showtime → seat page, once a
browser tab is free, and look specifically for a request fired *before* any seat
is clicked.

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
