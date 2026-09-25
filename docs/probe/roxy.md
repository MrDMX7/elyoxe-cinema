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

## Prices — always `null`, and why

Clicking a session (or its "Book Now" link) leads to a login-gated flow:
the site shows *"Please log in to continue"* before any seat map or price is
shown. There is no separate "show prices without picking a seat" endpoint we
could find. Per the binding rule (never trigger a seat hold, at most one
price call per cinema×hall×day), Roxy's reader always sets `"prices": null`.
`book` links to the movie's own page with `#movie-schedule-block`
(`https://www.theroxycinemas.com/en/movie/<slug>#movie-schedule-block`),
which is the closest thing to a real "go book this" URL that doesn't require
already knowing a live session id that may have sold out.

## Auth / rate limits

No API key or auth needed for the schedule/listing endpoints (they're public
Drupal AJAX callbacks used by anonymous site visitors). No documented rate
limit; the reader uses `readers.common.Polite` at the default 1 req/s with
retry-on-429/5xx, matching normal browsing pace.

## Access from this dev network: Akamai blocks plain `requests`

**Important caveat found while probing:** this site sits behind Akamai. Every
plain `requests.get()` call made directly against `theroxycinemas.com` from
this workspace's network returned **HTTP 403 "Access Denied" (Akamai edge
block)** — even for the plain homepage, regardless of `User-Agent`/`Accept`
headers. The exact same URLs succeeded immediately (HTTP 200) when fetched
from inside the built-in browser pane (a real browser context), which is how
all the data above and the fixture were captured — via `fetch()` executed in
the browser's own JS console against `location.origin` (same-origin, so no
CORS issues), not via Python `requests`.

This means `readers/roxy.py`'s `fetch()` — written straight against
`requests`/`Polite` per the shared interface — may itself return 403s if run
from a similarly-blocked network (e.g. common cloud/datacenter IP ranges that
Akamai fingerprints as bots). It is expected to work fine from a normal
residential/mobile IP, exactly like a real site visitor. If this becomes a
recurring problem in production, the fix is routing through a browser-based
fetch (headless browser or a residential proxy) rather than raw `requests` —
noted here rather than silently worked around, since a datacenter environment
running this reader unmodified will need that fix too.

## Fixture

`fixtures/roxy.json` — 6 cinemas + 100 shows, captured live 2026-09-25 for
2 now-showing movies ("Heart of the Beast", "Avengers Endgame: Encore")
across all 6 cinemas and both dates (2026-09-25, 2026-09-26), via the browser
pane as described above. This is a live-run sample (not all ~30 now-showing
movies — the full daily catalogue is ~380 shows for 2 days, well under the
≤400 cap, but a 2-movie/100-show slice already exercises every cinema, both
dates, and every hall tier including the two irregular ones (`2L`,
`Private Screen`).
