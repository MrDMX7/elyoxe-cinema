# Probe: the monthly price table (Task 1b)

Goal: fill `prices: null` on the five chains whose readers can't reach a price without a
seat hold (vox, novo, reel, roxy, cinemacity — see each chain's own `docs/probe/<chain>.md`
"Prices — why null" section for the specific trap). cineroyal and star are **not** touched
by this table: both readers already return real, live per-show prices (`getSeatsByScreenRef`
and `seat-layout`, both confirmed hold-free in their own probe docs), so `price_table.fill()`
never even looks at their shows (it only fills a show whose `prices` is already `None`).

## What was tried, in the binding order

**1. Official price lists / FAQ / app-or-API endpoints.** Checked each chain's own
`/ticket-prices`, `/faq`, `/experiences` pages and searched for an app/API price endpoint:

- VOX (`uae.voxcinemas.com`) — no `/ticket-prices` page found; `/ways-to-watch/*` pages
  describe formats (IMAX, MAX, 4DX, THEATRE, GOLD…) but carry no AED figures.
- Novo (`uae-api.novocinemas.com`) — per the vox/novo probe docs, the booking API is a
  Vista/Veezi backend; no ticket-types-without-a-hold endpoint was found (same conclusion
  as `docs/probe/novo.md`, re-confirmed here).
- Reel, Roxy, CinemaCity — same story: real per-seat pricing sits behind a booking session
  (Reel's `apiuae.reelcinemas.com`, Roxy's login gate, CinemaCity's Vista widget via
  `booking.cinemacity.ae`). No public price-list page found on any of the three sites.

None of the five chains publish a plain price list. Result: 0 entries from this tier.

**2. Reputable third-party listings with real per-cinema price ranges.** Searched (WebSearch)
for Time Out Dubai / Khaleej Times / Gulf News / The National coverage of 2025-2026 ticket
prices, and fetched `ae.kinoafisha.info` cinema pages for one site per chain (the format the
task cites, `"42.00 DH – 57.75 DH"`). What came back:

- General blog/aggregator hits (propertyfinder.ae, cinematicketprices.com,
  dubaivisitsvisa.com, discountdeals.ae, platinumlist.net, cobone.com) gave only vague,
  unattributed ranges ("AED 35-45", "AED 75-95 for IMAX", "Platinum Suites from AED 150") —
  no named journalist/outlet article with a dated, cinema-specific figure turned up in the
  results actually fetched, so none of these were recorded (not "reputable" per the task's
  own list, and not per-cinema).
- `ae.kinoafisha.info` cinema pages (VOX Mall of the Emirates, VOX Abu Dhabi Mall, Reel Dubai
  Mall, Cinemacity AlQana, Novo Dragon Mart, Roxy Dubai Hills) do **not** carry the
  `"X.XX DH – Y.YY DH"` range the task describes — every one of the six pages fetched showed
  only a flat, identical `"from 4.00 DH"` next to every showtime on every cinema on every
  chain, clearly a placeholder/junk value on that aggregator, not a real number. Not used.

Result: 0 entries from this tier this pass.

**3. One released seat-click sample.** VOX's booking flow is guest-checkout (no login
required) and was already probed once (`docs/probe/vox.md`): the seat-map's legend only
shows seat-class names after one seat is clicked, and clicking does **not** place a hold —
this is exactly the task's allowed "seat_sample" case, already exercised for VOX Al Jimi
Mall on 2026-09-25 (the task's own known data point). This pass, re-verified the mechanism
live at a **different** cinema/hall (VOX Mall of the Emirates, "Premier"/OTHER experience,
session 2026-09-29 11:20am — 3+ days out, plenty of free seats) via the built-in browser's
own tab (`tabs_create`, origin confirmed `uae.voxcinemas.com` before every action): reached
guest checkout → "Continue as Guest" → the seat map, confirmed the same
`Unavailable / Your Seat / Regular / Preferred View` legend shape as Al Jimi. The seat grid
there is drawn on a JS-managed layer, not plain clickable DOM cells (`read_page`/`find`
returned label elements at the right coordinates, but `left_click` on them never flipped the
"No seat selected" state to a confirmed seat), so no *new* AED number was captured — no
seat was ever held or confirmed, nothing needed releasing. Rather than guess the missing
figure, it was left out.

Roxy was skipped entirely for this tier per the task's own instruction (its booking flow is
login-gated before any seat map).

Novo, Reel and CinemaCity were not seat-sampled this pass (time/seat-hold-risk budget spent
on re-verifying the VOX mechanism instead of opening three more booking flows); flagged
below as the natural next step.

## What ended up in `prices.yaml`

Only `vox / vox-al-jimi-mall`, all four halls seen there (`Standard`, `MAX`, `KIDS`,
`THEATRE`), sourced from the task's own verified 2026-09-25 seat-click sample — the only
number set in this whole search that met the confidence bar. Every other
chain×cinema×hall combination in the five null-price chains is **absent** from the table on
purpose: the page for those shows `«السعر في الشباك»` rather than a guessed number.

## Coverage (cinema × hall combinations seen in the current fixtures)

| chain | combos in fixture | priced (live reader) | priced (this table) | priced total |
|---|---|---|---|---|
| cineroyal | 16 | 16 | 0 | 16 / 16 |
| star | 30 | 30 | 0 | 30 / 30 |
| vox | 66 | 0 | 3 (MAX, KIDS, THEATRE at Al Jimi Mall — `Standard` wasn't in the 400-show trimmed fixture but is in the table too) | 3 / 66 |
| novo | 5 | 0 | 0 | 0 / 5 |
| reel | 9 | 0 | 0 | 0 / 9 |
| roxy | 14 | 0 | 0 | 0 / 14 |
| cinemacity | 15 | 0 | 0 | 0 / 15 |
| **total** | **155** | **46** | **3** | **49 / 155** |

At the show level (not combo level): `price_table.fill()` on the live `fixtures/vox.json`
fills 18 of its 400 shows (every VOX Al Jimi Mall show in MAX/KIDS/THEATRE); cineroyal and
star need no filling (100%/100% live already).

## Next step, if VOX/novo/reel/cinemacity coverage is wanted beyond Al Jimi

Repeat the released-seat-click sample (tier 3) for one cinema × hall-type per chain per big
city — VOX MAX/IMAX/4DX/GOLD at a Dubai or Abu Dhabi site, Novo and CinemaCity's own
Vista-style booking flow (same guest-checkout shape as VOX, untested this pass), Reel's
`apiuae.reelcinemas.com` guest flow. Cap: 25 seat samples per the task's own budget; this
pass used 1 (released, no number captured) of that budget.
