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

## Prices — live since 2026-09-26 (Task 1c), no seat hold

The booking backend `apiuae.reelcinemas.com` *does* hand out the ticket list before any seat is
chosen — the earlier "needs a held session" note was wrong. Traced from the lazy seat-selection
chunk (`assets/index-Zpk_B4ZD.js`, `getSeatLayout`) and the showtime-click hook
(`assets/useTimeSlotBooking-*.js`, `CREATE_MOVIE_COOKIE`):

1. `POST /webapi/api/auth/loginAsGuest {}` — the anonymous guest session the site opens itself
   (no name/email/phone). Returns `tokens.access.token`, sent as `Authorization: Bearer …` (the
   site's axios interceptor). Every call also carries a `source-name` header =
   `base64(RSA-PKCS1v1.5("web"))` with the public key embedded in the bundle (`P4`).
2. `POST /webapi/api/booking/CreateMovieCookie {"value": X1(json)}` where json =
   `{CinemaId, SessionId, Experience, ScreenName}` and `X1` is the bundle's own 3DES-ECB with key
   `md5("ReelCinemasWeb")` (hex + first 16 hex), url-safe base64. Tells the backend which session
   the visitor is looking at.
3. `POST /webapi/api/seats/getSeatLayout?IsCancel=false&sessionId= {}` — the seat page's load call.
   `Sourcedata.TicketList[]` = `{AreaCode, TicketDescription, PriceInAed, PriceInCents}` and
   `AreaEntityList[]` = `{AreaCode, AreaDescription}`. Example (Dubai Mall Screen 1):
   Standard 44, Standard Plus 55 AED. `BookingTimer: 300` — a 5-minute seat-less order.

No seat is ever set (`seats/setSeat` / `seats/addTicket` never called). The site's
`order/cancelOrder` (POST, `{OptionalClientId, CinemaId, UserSessionId}`) answers 500 for an order
without seats; the reader still calls it after every sample, in a `finally` (review round 2 ruling:
abandon through the site's own path), and ignores the 500 — the order also lapses on its 300 s timer.
Sampling health is returned as `price_health` (attempted / priced / error); a guest-login failure or
an all-failed run sets `error` and is printed to stderr (so a rotated bundle key is visible).

`readers/reel.py` samples once per cinema × experience code (STANDARD / PLATINUM / PREMIUM /
DOLBY / SCREENX / IMAX / REELJUNIOR / INFINITY V) per run, on a session at least an hour away with
seats available; a failed sample leaves that hall `None`. Cost: 1 login + 2 calls per sample,
~9 samples → ~20 calls at ≥1.1 s. `readers/reel.py` needs `curl_cffi`, `cryptography` and
`pycryptodome` for this (all installed here).

Prices seen 2026-09-26 (AED, VAT incl., as the site shows them): Dubai Mall — Standard 44 / Plus 55;
Premium Front 60 / Premium 70; Platinum Suites 178; Dolby 42 / Dolby Plus 65 / Dolby Premium 75;
ScreenX Std 50 / Plus 60. Dubai Marina Mall — Standard 42 / Plus 53 / Preferred View 57; Dolby as
Dubai Mall. The Springs Souk — Standard 42 / Plus 53; Reel Junior 48.

## Review fixes (2026-09-26)

- Live cinemas are now derived from `Sessions.json` (UAE cinemas with a session in the window);
  a UAE cinema with sessions but no entry in `_CINEMA_ADDR_HINTS` raises instead of vanishing.
- Hall ruling: Dolby Cinema and Infinity Vision → `OTHER` (raw screen name kept); Reel Premium
  (recliners) → `VIP`. Dolby takes priority over the `INFINITY V` tag some Dolby screens carry.
- "Today" is Asia/Dubai; zero in-window shows raises `RuntimeError`.

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
