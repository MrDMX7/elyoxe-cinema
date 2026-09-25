# Probe: Reel Cinemas (reel)

## The site is behind Cloudflare — but its data feed isn't

`www.reelcinemas.com` (React SPA, Vite build) sits behind Cloudflare Bot Management. Two out of
three direct navigations to `/uae` and `/en-ae/showtimes` in the built-in browser pane returned
Cloudflare's block page ("You have encountered a problem, please try again later.") even from a
real headed browser; a plain `requests`/`curl` hit would almost certainly always be blocked.

Reverse-engineered the app's own bundle (`https://www.reelcinemas.com/assets/index-cS_jeM1V.js`,
fetched from inside an already-loaded page tab to dodge the challenge) instead of trying to beat
the challenge. It defines two API bases:

- `https://apiuae.reelcinemas.com` — the real booking/session backend. Every path returns
  `{"statusCode":0,"statusMessage":"Unauthorized access"}` (HTTP 401) even for `/`. The axios
  instance for it is created with `withCredentials: true` and an interceptor that attaches
  `Authorization: Bearer <token>` from a Redux `userDetails.cookie` value obtained through a
  guest-login/refresh-token flow (`POST {base}/webapi/api/auth/refresh-tokens`, called
  automatically by the SPA). Not used — replicating a guest session dance for a read-only feed
  is unnecessary risk for no benefit given the next endpoint exists.
- `https://storage.googleapis.com/eeg-prod-reelcinema-sb/web` — a public, static Vista Cinema
  data export on GCS, **no auth, no Cloudflare, no cookies**. This is what the homepage/showtimes
  page actually renders from (loaded via a plain `axios.get`, `withCredentials` not set). Confirmed
  with plain `requests` from this machine: `GET .../vista/json/Cinemas.json` → 200 straight away.

## Endpoints used (all GET, unauthenticated)

```
https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Cinemas.json     (9 KB)
https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Films.json       (~250 KB)
https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Sessions.json    (~2 MB, ~10 days out)
https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Experience.json  (1.8 KB, seating-tier catalog)
```

Standard [Vista Cinema "Data-Ex"](https://www.vista.co) JSON export shape
(`{"odata.metadata": "", "value": [...]}`), the same feed format many cinema chains publish for
listing partners. No rate limiting observed; reader still uses `readers.common.Polite` (1 req/s,
retry on 429/5xx) out of politeness — 3 calls per run (Cinemas, Films, Sessions; Experience.json
isn't needed at runtime once the hall-code table below was captured by hand).

## Cinemas: only 3 of Reel's UAE cinema records are live

`Cinemas.json` lists 8 UAE-tagged (`CinemaNationalId: "UAE"`) cinema records plus 2 non-UAE
(Granada Mall = Saudi Arabia, Marassi Bahrain). Cross-checking against `Sessions.json` (grouped by
`CinemaId`) on 2026-09-25:

| ID   | Name                         | Sessions in feed |
|------|------------------------------|-------------------|
| 0001 | Dubai Mall                   | 791 |
| 0002 | Dubai Marina Mall            | 215 |
| 0003 | Jebel Ali Recreation Club    | 0 |
| 0004 | The Pointe                   | 0 |
| 0005 | Rove Downtown                | 0 |
| 0006 | The Springs Souk             | 182 |
| 0007 | Al Ghurair Centre            | 0 |
| 0008 | Reel Cinemas – Drive-In      | 0 |

The task brief's guess list ("Dubai Marina Mall, Springs Souk, Rove Downtown, The Pointe, Dubai
Mall") is exactly the 5-cinema set that shows up in the raw record, but only 3 of those have any
scheduled sessions right now — Reel's live UAE footprint (per its own public "Locations" footer
and the front page) is also only these 3: **Dubai Mall, Dubai Marina Mall, The Springs Souk**. The
reader only emits Cinema records for cinemas with at least one session in the fetch window, so it
doesn't invent an address/city for a screen that isn't operating (global "no invented data" rule).
`Cinemas.json` itself carries no address/lat/lng (all blank/null for every record, even active
ones) — addresses were filled in by hand from the mall name (`_CINEMA_ADDR_HINTS` in
`readers/reel.py`), not fabricated details beyond "which Dubai mall this is."

## Halls

Session records carry `SessionAttributesNames` (e.g. `["2D","PLATINUM","PROMO-ARAB", ...]`) and a
free-text `ScreenName` (e.g. `"Platinum Suites 4"`). `Experience.json` gives the code→display-name
catalog:

| Reel experience code | Display name         | Mapped hall |
|-----------------------|-----------------------|-------------|
| standard               | Reel Standard          | Standard |
| platinum                | Reel Platinum Suites   | SUITES |
| premium                 | Reel Premium            | GOLD |
| dolby                    | Dolby Cinema            | VIP |
| screenx                  | ScreenX                 | SCREENX |
| imax                      | IMAX                    | IMAX |
| reeljunior                | Reel Junior             | KIDS |

`hall_label` is the session's raw `ScreenName` (falls back to the matched experience's title-cased
name if `ScreenName` is blank). No 4DX/MX4D screens are currently live at any of the 3 active UAE
cinemas (Experience.json has no MX4D entry for this market), so `4DX` never appears in the fixture
— the mapping code is still there for if/when one opens.

## Prices — always `None`, and why

`Sessions.json`'s `MinimumTicketPriceInCents` field is `null` on every session record observed
(spot-checked dozens across all 3 cinemas and every hall type). Reel's real per-seat-class pricing
only appears after `GetSeatLayout`/`GetSeatPlan` is called against `apiuae.reelcinemas.com` with an
active booking session — i.e. after a seat is effectively held. The binding rule ("only from
endpoints that do NOT place a seat hold... at most one price call per cinema × hall per day") rules
that endpoint out entirely, so this reader never calls it and every show's `"prices"` is `None`.

## Booking link

Reel's own frontend builds movie-details URLs as `/{lang}/movie-details/{filmId}/{slug(title)}`
(found as `o3`/`i3` in the bundle: `o3=(e,a,o)=>\`/${o}/movie-details/${e}/${a}\`` composed with a
slugifier `i3` — lowercase, `&`→`-and-`, everything non `[a-z0-9-]` → `-`, collapse/trim dashes).
`readers/reel.py` reproduces that slug function in Python and builds
`https://www.reelcinemas.com/en-ae/movie-details/{film.ID}/{slug}` as the `book` link for every
show — a real, working page (film details + session picker for all 3 cinemas), not a
seat-specific deep link (Reel's frontend doesn't expose one without JS state), and it places no
hold.

## Result

`fetch()` on 2026-09-25: 3 cinemas, 234 shows across today + tomorrow (well under the 400 cap).
Hall distribution in the live fixture: Standard 153, SUITES 31, GOLD 22, VIP 18, SCREENX 5, KIDS 5.
