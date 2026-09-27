# Probe notes: ROXY Cinemas (UAE)

Site: https://www.theroxycinemas.com (Drupal 9/10, `roxy` theme, custom module
`roxy_cinema`). No public/documented JSON API — everything below was found by
watching XHRs in the built-in browser pane (`mcp__Claude_Browser__*`) while
browsing the site normally, then replicating those calls with `fetch()` from
the page's own origin.

## Cinema list (6 live sites, all in Dubai)

`GET /en/cinemas` server-renders the list. As of 2026-09-25 Roxy operates
**six** cinemas, all in Dubai — the older locations sometimes mentioned in
older write-ups (Bollywood Parks, Galleria Al Barsha, La Mer, Arabian Center)
are **not** in the current site; cross-checked against the schedule endpoint
below, which only ever returns these six `cinema-id` values:

| site cinema-id | name (site)     | url slug      |
|----------------|------------------|----------------|
| 0000000001     | City Walk        | `citywalk`     |
| 0000000002     | The Beach, JBR   | `the-beach`    |
| 0000000003     | Boxpark          | `boxpark`      |
| 0000000006     | Al Khawaneej     | `al-khawaneej` |
| 0000000007     | Dubai Hills Mall | `dubai-hills`  |
| 0000000009     | Circle Mall      | `circle-mall`  |

Google Maps links were only present on 4 of 6 `/en/cinemas/<slug>` pages
(`al-khawaneej`, `the-beach`, `citywalk`, `boxpark`); `dubai-hills` and
`circle-mall` have no maps link in the page markup, so `maps`/`lat`/`lng`
are `None` for those two in the fixture. `city` is hardcoded/derived as
`"dubai"` for all six (confirmed from mall names + addresses); `common.city_of()`
doesn't recognise "Al Khawaneej" as a Dubai word on its own, so the reader
builds an address string that includes "Dubai" explicitly.

## Showtimes endpoint (the real find)

Each movie page (`/en/movie/<slug>`) loads its own schedule client-side via:

```
GET /en/movie-schedule/ajax?nid=<movie-node-id>&promotion=
-> {"status": "success", "html": "<div id=\"movie-schedule-block\">...(full HTML)...</div>"}
```

- `nid` is the Drupal node id of the movie, found in the movie page's raw
  HTML as `data-history-node-id="177366"` (NOT visible via a plain `fetch()`
  of the page — that attribute is server-rendered, so a real GET on
  `/en/movie/<slug>` is enough; you do *not* need to run the page's JS).
- **One call returns ALL cinemas and ALL upcoming dates** (today through
  +5 days) for that movie, not just the currently-selected day/cinema. This
  is the opposite of pagination — it means `fetch()` needs exactly one
  request per now-showing movie (≈30–35 requests total for the whole UAE
  catalogue), not one per cinema×day.
- The HTML fragment embeds one `<input type="radio">` per session with every
  field we need as plain HTML attributes, e.g.:
  ```html
  <input ... cinema-name="Al Khawaneej" cinema-id="0000000006" screen="Gold"
         nid="177366" date="Sep 25 Fri" time="23:30" session="96276">
  ```
  Parsed with a single regex — no HTML parser needed, no JS execution needed.
- `date` is `"<Mon> <D> <Weekday>"` (no year) — the reader assumes the current
  year and maps month names itself (`_map_date`).
- Screen/tier names seen in the wild: `Gold` / `GOLD` (Circle Mall uses caps),
  `BRONZE`, `Silver`, `Platinum`, `Xtreme`, `2L` (a "comfortable glide seating
  / curved screen / love-seat" format at City Walk only), and `Private Screen`
  (The Beach JBR — a whole room hired privately). Mapped to the shared `HALLS`
  enum as: `Xtreme→MAX`, `Platinum→VIP`, `Gold/GOLD→GOLD`, `Silver→Standard`,
  `Bronze→OTHER`, `2L→OTHER`, `Private Screen→SUITES`. Raw label is always kept
  in `hall_label`.

## Movie list / metadata

- Now-showing + coming-soon movie slugs are read off `/en` (`href="/en/movie/<slug>"`).
- Title, runtime, language and rating are scraped from the movie page itself
  (cut off before the "other movies you might like" carousel, which repeats
  unrelated movies' data and will poison a naive regex — learned the hard way
  when a `Language:` match came back "Korean" for an English film).
  - Title: `<h1>...</h1>`
  - Runtime: `"N Hour[s] M Minute[s]"` text → minutes
  - Language: `"Language: <X>"` text
  - Rating: `<span id="movie-rating">PG 13</span>` → normalized to `"PG13"` (space stripped)

## Prices — live, from the seat-selection page, no login (corrected 2026-09-27)

**Earlier note in this file was wrong.** Clicking a session's "Book Now" link
does land on a page with a *"Please log in to continue"* modal — but that
modal is for the *watchlist* feature ("You need to be logged in to add
movies to your watchlist"), triggered by JS on click; it is not a gate on
the page's own content, and a plain server-side `GET` on the seat-selection
URL never triggers it. There is a real, ungated seat-class price source:

```
GET /en/seat-selection/<cinemaCode>/<sessionId>/<movieNid>/<cinema name>/<"Mon D Ddd">/<HH:MM>/<hall label>
```

e.g. `/en/seat-selection/0000000006/96027/177366/Al%20Khawaneej/Sep%2027%20Sun/22:30/Gold`.
Every field in the URL is already on the schedule-ajax session tag (`cinema-id`,
`session`, `nid`, `cinema-name`, `date`, `time`, `screen`) — no extra lookup
needed, `readers/roxy.py`'s `_seat_selection_url()` builds it directly.

The response is the full server-rendered seat map, whose legend carries one
`<span>` per seat class:

```html
<span price="7000" tax="1001" price-in-aed="70" seat-category="Premium View">Premium View</span>
```

Confirmed live, repeatedly: a plain `GET` on this URL returns the seat map
with **no redirect, no `Set-Cookie`, no booking/order id created** — nothing
is held or selected. `readers/roxy.py`'s `_seat_legend_prices()` parses
`price-in-aed`/`seat-category` with a single regex (`SEAT_LEGEND_RE`).

**VAT/fees are already included in the published number.** `price` and `tax`
are in fils (100ths of a dirham); `price-in-aed` is exactly `price / 100`.
Sampled across several cinema×hall combinations, `tax / price` always landed
on the same ratio (~1/7) regardless of the total (e.g. 615/4300, 1001/7000,
1157/8100, 2543/17800) — that only holds if `tax` is a fixed fraction already
folded into `price`, not an amount added on top. So `price-in-aed` is the
inclusive, pay-this-at-checkout number, and that is what `readers.roxy`
publishes as `prices[].aed` — no separate VAT line is added or subtracted.

Sampled once per cinema×hall×show-date (not per session — twin sessions in
the same hall/date share a sample), reusing `data/price_cache.json` across
hourly runs like the other chains (`fetch(days=..., cache=...)`, wired
through `refresh.py`'s `PRICE_CACHE_CHAINS`, which now includes `roxy`). A
sampling failure (non-200, blocked, exception) never fails the chain — it's
recorded honestly in `price_health` and that show's `prices` stays `null`.
A live one-cinema-day run on 2026-09-27 (274 shows) priced 270/274 (98.5%);
the 4 unpriced were all "Private Screen" (The Beach, JBR) — a whole-room
rental format whose seat-selection page carries no seat-class legend at all
(a real, expected null, not an error).

`book` still links to the movie's own page with `#movie-schedule-block`
(`https://www.theroxycinemas.com/en/movie/<slug>#movie-schedule-block`),
which is the closest thing to a real "go book this" URL that doesn't require
already knowing a live session id that may have sold out.

## Auth / rate limits

No API key or auth needed for the schedule/listing endpoints (they're public
Drupal AJAX callbacks used by anonymous site visitors). No documented rate
limit; the reader uses `readers.common.Polite` at the default 1 req/s with
retry-on-429/5xx, matching normal browsing pace.

## Access from this dev network: Akamai blocks plain `requests` — fixed with `curl_cffi`

**Important caveat found while probing, since fixed:** this site sits behind
Akamai. Every plain `requests.get()` call made directly against
`theroxycinemas.com` from this workspace's network returned **HTTP 403
"Access Denied" (Akamai edge block)** — even for the plain homepage,
regardless of `User-Agent`/`Accept` headers. This is a TLS-fingerprint-level
block (same as VOX, see `docs/probe/vox.md`), not a header check, so no
amount of header-spoofing on plain `requests` fixes it.

Fix: `readers/roxy.py` uses `curl_cffi.requests` with `impersonate="chrome"`
instead of `readers.common.Polite` (which wraps plain `requests`).
`curl_cffi` matches Chrome's real TLS fingerprint (JA3/ALPN/cipher order),
which Akamai accepts as a normal browser. Confirmed working with a real
unattended shell run — see the fix report appended to
`.superpowers/sdd/2026-09-25-cinema/task-1-roxy-report.md` for the exact
command and output (6 cinemas, 660 shows for today+tomorrow across the full
now-showing catalogue, 0 priced as expected).

`CITIES`, `HALLS`, `slug()` and `city_of()` are still reused from
`readers.common` — only the HTTP transport changed.

## Fixture

`fixtures/roxy.json` — 6 cinemas + 380 shows, resampled (seeded random,
`random.seed(42)`) down from a real unattended `readers.roxy.fetch()` shell
run on 2026-09-26 that returned 660 shows (full now-showing catalogue,
today+tomorrow, all 6 cinemas). 380 was chosen to sit under the ≤400 cap
while still exercising every cinema and every hall bucket. All shows have
`"prices": null`, confirmed live (see fix report in
`.superpowers/sdd/2026-09-25-cinema/task-1-roxy-report.md`).
