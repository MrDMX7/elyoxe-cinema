# Probe: VOX Cinemas UAE (`uae.voxcinemas.com`)

## Can it be read without login?

Yes — cinema list, films and showtimes for every date on the site's picker are all in
server-rendered HTML, no JSON XHR to call instead. No login or account needed.

## The blocker: Akamai Bot Manager, TLS-fingerprint level

Plain `requests.get()` and plain `curl` both **hang until timeout with no response at all**
(`000`/`ReadTimeout`) on every page of this site, including the homepage — even with a real
Chrome `User-Agent` header. `robots.txt` alone loads fine, which is what made this look at first
like a normal block rather than a full-connection block.

This is Akamai's Bot Manager fingerprinting the TLS `ClientHello` (JA3/JA4), not the HTTP
headers — so no header changes fix it. What does fix it: **`curl_cffi`** (already installed,
`0.15.0`) called with `impersonate="chrome"`, which reproduces Chrome's actual TLS fingerprint.
With that, every page returns a normal `200` in ~1–2 s. The built-in browser pane (real
Chromium) also works, which is how this was diagnosed — it was the control that proved the
block was transport-level, not a content/JS check.

Practically: `readers/vox.py` does **not** use `readers.common.Polite` (which wraps plain
`requests` and would hang on this host). It has its own small rate-limited wrapper around
`curl_cffi.requests.Session()`, same politeness contract (≥1.1 s between requests, retry
429/5xx up to 3×). `CITIES`, `HALLS`, `slug()` and `city_of()` are still reused from
`readers/common.py` unchanged.

**Concern for the shared refresh job:** every other chain reader that uses `Polite`/plain
`requests` presumably works fine on requests; VOX is the one chain here needing `curl_cffi`.
Whatever runs the daily refresh (GitHub Actions or the Fold, per the design doc) must have
`curl_cffi` installed, or this reader needs a fallback to the browser pane. Not addressed by
this task — flagging for the integration step.

## Endpoints used

- `GET https://uae.voxcinemas.com/cinemas` — full cinema list: `article.cinema-summary
  [data-slug]` → name (`h3 a`), address (`p`), and whether it has a `Showtimes` link at all
  (two of the 25 listed — *Galleria Mall Dubai-Moonlight* and *Sharjah Safari* — have no
  showtimes link; they're not bookable cinemas in the normal sense — a rooftop pop-up and a
  safari park screen — so this reader excludes them from both `cinemas` and `shows`).
- `GET https://uae.voxcinemas.com/showtimes/<slug>?d=YYYYMMDD` — one cinema, one calendar day.
  `d` is `YYYYMMDD`; omitting it defaults to "today" (the site itself fills a hidden
  `<input name="d" value="20260925">` for "today" when you omit it — this reader always passes
  it explicitly for both today and tomorrow, so `days=2` means exactly those two dates).

No separate JSON API was found behind either page — view-source and the rendered DOM are the
same. The built-in browser's network log on both pages showed only analytics/tracking XHRs
(`/api/tracking/ga4/...`), asset loads And an Akamai sensor beacon
(`/Lg6gSvbDZ6D83/.../skPgAcHgc`) — nothing that carries showtime data as JSON.

## Rate limits / blocks observed

- Full run (23 cinemas × 2 days + 1 cinema-list page = 47 requests) completed in ~51 s at the
  ≥1.1 s/request pace with **zero** 429s or 5xxs.
- No CAPTCHA encountered at this request volume. The TLS-fingerprint block above is the only
  wall hit.

## Cinema → city mapping

`common.city_of()` (name + address, word-boundary match) correctly resolves 17 of 23 cinemas.
Six needed a manual override (`MANUAL_CITY` in `readers/vox.py`) because VOX's own address field
is either truncated (e.g. Burjuman's address literally ends `"...Al Waleed Rd, Duba"` on their
site) or just doesn't mention the city (`"Level 2 Mall Of Emirates"` for both Kempinski and
Mall of the Emirates, both actually in Dubai):

| slug | why it needed an override | city |
|---|---|---|
| `burjuman` | address truncated to `"...Duba"` | dubai |
| `city-centre-meaisem` | address is just `"Production City"` | dubai |
| `city-centre-shindagha` | `"Al Shindagha"` isn't in `_CITY_WORDS` | dubai |
| `kempinski-mall-of-emirates` | address has no city word | dubai |
| `megaplex-cineplex-grand-hyatt` | address truncated to `"...Duba"` | dubai |
| `mall-of-the-emirates` | address has no city word | dubai |

Every one of the 23 bookable cinemas ends up with a valid city (`readers/vox.py` raises loudly
if one ever doesn't, rather than shipping a cinema with a bad/missing city).

## Halls: VOX's raw "experience" labels seen live

Sampled across Al Jimi Mall, Mall of the Emirates, Yas Mall, City Centre Deira, The Galleria Al
Maryah Island, Wafi Mall, City Centre Sharjah, Nation Towers, Burjuman, City Centre Mirdif, Reem
Mall and Dubai Festival City Mall:

| raw label | → `hall` | notes |
|---|---|---|
| `Standard` | Standard | |
| `MAX` | MAX | |
| `IMAX` | IMAX | |
| `4DX` | 4DX | |
| `GOLD` | GOLD | |
| `THEATRE` | THEATRE | private small-capacity room |
| `Kids` | KIDS | |
| `Premier` | OTHER | VOX's own premium-lounge product, doesn't map to any HALLS value; kept as `hall_label` |
| `Premium` | OTHER | distinct product name from `MAX`/`GOLD`, same reasoning |
| `Couch - 2 Seater` | OTHER | a seat-type label surfacing as an "experience" at one cinema |
| `THEATRE PODS in IMAX` | OTHER | hybrid product, not cleanly THEATRE or IMAX |
| `Private Cinema` (long label incl. "This session can be customized...") | OTHER | |
| `SAMSUNG ONYX` | OTHER | premium LED-screen format, no HALLS slot |

`HALL_MAP` in `readers/vox.py` matches the raw label case-insensitively and **exactly** (not by
substring), specifically so `"THEATRE PODS in IMAX"` doesn't get swallowed into `THEATRE` or
`IMAX` by accident.

## Prices: could not be read without holding a seat

Traced the full booking flow live (guest checkout, no login, no personal data entered, no
payment) for a real showtime:
`showtimes page → /booking/<id> → guest-or-login screen ("Continue as Guest") →
/booking/<order>/seats/fetch → conditions-of-access dialog → /booking/<order>/seats`.

The seat-map page itself — reached *before* clicking any seat — shows the screen layout, a seat
legend (`Unavailable / Your Seat / Regular`), and a running total that reads **`0.00 AED`** until
a seat is clicked. No per-seat-class price (Standard/MAX/GOLD/etc.) is rendered anywhere before a
seat selection, and no JSON call fires with that data either — the seat-map HTML itself has no
price fields hidden in markup, confirmed by reading the raw response body.

The task brief mentions a previous researcher having obtained Standard 46/56/61 AED, MAX
52/65/70 AED, THEATRE 195 AED "from the booking flow" — but reaching that point requires
clicking an actual seat, which places a hold on it. **The binding rule in this task explicitly
forbids that** ("If a price is only visible after selecting a seat ... do NOT do that — set
`prices: null`"), so this reader does exactly that: every VOX show ships with `"prices": null`.
No ticket-types/price-list endpoint that skips the seat-hold step was found for VOX — unlike
some chains, there does not appear to be one.

**Open question for a follow-up, if VOX prices are wanted later:** whether VOX exposes a
`GET .../seats` JSON variant (as opposed to the HTML page fetched here) that includes seat-class
prices without a hold — this reader did not find one via the rendered network log, but the
network log only shows the resources the *browser* actually requested; a raw endpoint enumeration
wasn't attempted (out of scope: that would mean probing undocumented API surface, which felt like
more risk than the task's price-safety rule wants).

## Live run results (this task's fixture)

- 23 bookable cinemas across all city buckets: `abu-dhabi` (5), `dubai` (12), `sharjah` (2),
  `al-ain` (1, Al Jimi Mall), `ajman` (1), `ras-al-khaimah` (1), `fujairah` (1). None in
  `umm-al-quwain` (VOX has no cinema there — correct, not a gap).
- 1,547 shows fetched (today + tomorrow, all 23 cinemas); trimmed to 400 for `fixtures/vox.json`
  per the task's size cap, keeping every cinema represented (17–18 shows each, non-`Standard`
  halls preferred in the trim so hall variety survives).
- Hall distribution in the full run: Standard 868, OTHER 278 (Premier/Premium/Couch/pods/Private
  Cinema/Samsung Onyx), THEATRE 104, KIDS 102, MAX 89, GOLD 75, IMAX 26, 4DX 5. `SUITES`,
  `SCREENX` and `VIP` were not observed at any UAE VOX cinema in this run (mapped in `HALL_MAP`
  in case a future refresh finds them).
- `prices` is `None` on all 1,547 shows (see above).
- `maps` / `lat` / `lng` are `None` on all cinemas — the `/cinemas` list page and the per-cinema
  detail page (`/cinemas/<slug>`) weren't checked for an embedded map/coordinates in this pass;
  flagging as a possible enhancement rather than fetching 23 more pages against the request
  budget implied by "politely, ~1/s".
