# Task 3 report: seat map, crowd meter, best seat

## What was built
- `seats.py`: `normalise(chain, raw)` turns each chain's seat-layout response into
  `{rows:[{name, seats:[{id,x,col,status,cls}]}], screen_side, classes:[{name,aed}]}`. Also: `counts`,
  `best_seat` (rows 55 to 75 % back from the screen, the middle third of the columns, dearest class first, closest to
  2/3 back and then to the centre), `compact`/`expand` (the site's form), `keep` (the reader hook), the capped
  sampler (`pick`, `Budget`, `_Metered`, `sample`) and `fresh` (< 90 min).
- Status mapping and screen end for each chain are documented in the `seats.py` docstring. Evidence came from live
  probes on 2026-09-27 and from each chain's own front-end code:
  - Star's cell classes in its bundle: reserve type 8 means unavailable, covid means blocked, "Wheelchair" or status 3 means wheelchair.
  - Cine Royal's `seatClicked()` refuses seatFlag 0 and internetBooked 0.
  - Reel: "Special" seats are counted in `SeatsAvailable` (36 = 35 Empty + 1 Special).
  - VOX: seats marked `.sold`, with the legend giving the class names.
  - Screen end comes from price tiers and names: Reel's first row is "Premium Front", VOX's dearer "Preferred View" rows are
    last, Star's cheapest class is in rows 1 to 5, and Cine Royal's dearest tier is row A, which puts its screen at the bottom.
  - Roxy has no seat map (login-gated).
- Reader hooks (minimal). `common.keep_layout()` never raises. Each price sampler got an `on_layout=` callback (Reel uses
  `_PriceClient.on_layout`). Star, Cine Royal, Novo and Reel shows also carry `_sid` (their session handle).
  VOX and Cinema City use the `book` URL.
- `steps/occupancy.py`:
  1. Pops every `_sid` first, so none is published.
  2. Merges kept shapes into `data/seatmaps.json`.
  3. Samples shows starting within the next 3 h into `data/occupancy.json`. Both files are written with statefile:
     atomic, with a `.bak`, and a corrupt file is renamed rather than trusted.
  4. Attaches `seats {free,total,at,m,st,best}` only when the sample is under 90 min old, and sets `data.seatmaps`
     for the halls it shows.

  Caps: 60 HTTP requests per chain per run, counting every redirect and retry, at least 1 s apart. Chains run side
  by side with a 240 s wall clock. The order is round robin over cinemas, soonest show first, and a show sampled in the last 45 min is skipped.
  A 401/403/429 or a Reel guest-login failure stops that chain. It never selects or holds a seat and never logs in.
  It reuses the readers' own clients, token and helpers by import.
- `pages/seats.py`: builds `/data/occupancy.json` (counts for time buttons) and `/data/seats/<cinema>.json` (shapes,
  the show's own statuses when fresh, and the best seat). It sets `page_js` for home, city, cinema and film.
  - `src/js/seatmap.js` (lazy chunk) puts «باقي N مقعد» under fresh times, rechecks the 90 min on the client, and
    draws the hall in the ticket as an SVG. The screen is always drawn on top, with square seats (no radius).
    The best seat is velvet. The SVG is `aria-hidden`, and a figcaption says the same thing, e.g.
    «باقي 36 مقعد من 39، أحسن مقعد متاح: الصف C وسط» plus «آخر عدّ قبل N دقيقة».
  - With no fresh sample, it draws only the hall shape: «القاعة فيها 39 مقعد، أحسن مكان: …».
  - `src/css/seatmap.css` uses only the «هـ» ticket tokens.

## Tests
- `tests/test_seats.py`: 24 tests, all passing. They cover:
  - the normalisers on 6 saved small fixtures in `tests/fixtures/seats/`, with any edits named in each `_note`
  - best seat
  - compact round trip
  - freshness
  - pick window and round robin
  - Budget spacing and the cap of 60
  - a blocked chain stopping
  - the step (strips `_sid`, attaches fresh entries only, survives a corrupt file, sampling online)
  - the reader hook
  - the site data files
  - the chunk only on ticket pages, and no `_sid` in `out/data`
  - the chunk parsing in node (`--check`) and drawing and its summary texts
- `tests/test_plugins.py`, one line: the example's home page may now load other modules' chunks. The assertion now
  checks that `hello` is not loaded there, which is what it meant.
- Full suite at the time of the run (other agents' work in progress in the tree): `24 failed, 428 passed, 12 errors`
  (exit 1).
  - The 36 failures and errors were `AttributeError: 'dict'` build errors from a module mid-edit. They disappeared on re-run.
  - After re-running, these still fail and are not from this task:
    - `test_build::test_real_latest_at_its_busiest_stays_within_budget`: film pages are over 150 KB. A core+seats
      build of the same data has 0 pages over budget.
    - `test_preview::test_default_build_stays_indexable`: `/summer/` is noindex, from the seasons module.
    - `test_refresh::test_hung_chain_is_timed_out`: `steps/coming.py` takes 59 s with network. `occupancy` takes 0.01 s.
  - Re-run of this task's files plus the readers, steps, refresh and golden tests: 123 passed, 1 failed (the hung-chain test above).

## Live check (2026-09-27 ~10:30 Dubai, real chains, real caps, state in a scratch dir)
The readers ran once with days=1; VOX, Novo and Reel ran with prices=False.

The readers returned: Reel 202 shows, Novo 118, Cine Royal 270, Cinema City 244, VOX 1430, Star 558.

The price hooks kept 62 hall layouts. The occupancy step took 76 s and attached seats to 198 shows. No `_sid` was left on any show.

| chain | shows picked | requests | shows sampled |
|---|---|---|---|
| star | 108 | 60 (cap) | 60 |
| cineroyal | 49 | 50 | 49 |
| cinemacity | 43 | 43 | 43 |
| novo | 13 | 13 | 13 |
| reel | 39 | 58 | 19 (login + 3 per sample) |
| vox | 250 | 56 | 14 (~4 per sample incl. the abandon) |

Two sampled examples: Reel Dubai Mall Screen 3 at 11:00 had 174/178 free, best seat D9. Premium 19 at 11:15 had 28/39 free, best seat B4.

## Notes and limits
- Hall shapes are keyed by cinema and hall_label. Where a label covers several screens (e.g. Star NORMAL), the
  shape drawn without a fresh sample is the sampled screen's shape. A fresh sample always uses the show's own map.
- Novo only yields a `_sid` for sessions with a `session_id`, which is why it had 13 shows picked.
- The step only runs when refresh runs (4 times a day until the cutover). «باقي» therefore shows for up to 90 min after
  each run, and the client hides it after that.

---

# Fix round 1 (review task-3-review.md)

0. **origin/main merged** into phase2 (`55c47ed`), including 01c10fa (Roxy live prices). No conflicts, and none of
   the merged files overlapped with other agents' uncommitted files.
1. **Roxy added.** Roxy's public seat-selection page (plain GET, no login, no cookie) carries the whole seat grid:
   - `seats._roxy` reads `.seats-row`, sold seats (status 7), `input.wheelchair`, the `screen-type` class and the
     `span[seat-category][price-in-aed]` legend.
   - The screen end is top: the screen image comes before the rows, and the dearer "Premium View" rows are last.
   - Roxy's `_sample_prices` got an `on_layout` hook, and every Roxy show carries `_sid` = its seat-selection URL.
   - The sampler makes 1 GET per show.
   - The seats.py docstring table is corrected, and the Reel guest-token ruling is noted there.
   - Fixture: `tests/fixtures/seats/roxy.html` (live, trimmed, not edited). It gives 57 seats: 54 free, 1 taken, 2 wheelchair.
2. **The caps now count every redirect.** `_Metered` sends every request with `allow_redirects=False` and follows
   `Location` itself. Each hop goes through the cap, the deadline, the 1 s gap and the count.
   - A test covers a curl-style response with an empty `history`.
   - A test covers the cap stopping inside a redirect chain.
   - `_Spent`/`_Blocked` are now `BaseException`, so the readers' `except Exception` retries no longer swallow them.
   - VOX and Reel keep 1 request in reserve for the order's own abandon/cancelOrder, so a cap hit mid-sample still
     releases the order and the total stays within 60. This is tested with `vox._sample_prices` itself.
   - VOX's cost per sample is 9, as measured live.
3. **No other screen's map.** Shapes are keyed by physical screen where the chain names it:
   - Star `screen_name`
   - Cine Royal `screenRefId`
   - Cinema City screen name
   - Reel `ScreenName`

   VOX, Novo and Roxy name no screen. For them there is one entry per distinct shape of a label, and a label with
   more than one shape gets no `seatmap`, so no drawing and no seat total. A show's own fresh sample is always its
   own map. The step sets `show.seatmap` only when the shape is certain, and `pages/seats.py` uses only that.
4. The report is untracked again (`git rm --cached`) and kept locally.

Minors:
- A 429 stops the chain at once (the metered session is called directly, so there is no retry).
- Late sampler threads stop at the deadline: `Budget(deadline=…)` refuses any request after it.
- `_`-prefixed show keys are dropped in two places:
  - first in the step, before any import (tested with `seats` failing to import)
  - again at build time (`pages/seats.private_off`)
- The Cine Royal warm-up is counted once (the cost is 2 for the first sample, then 1; tested).

Tests: `tests/test_seats.py` has 35 tests (11 new) and all pass. Seat and reader tests: 116 passed.

Full suite: `5 failed, 537 passed` (exit 1). None of the 5 failures is in the seats/readers code. They are the 3 already
reported before this round:
- the page budget (8 film pages over 150 KB in builds with and without seats)
- `/summer/` noindex (the seasons module)
- the hung-chain timeout (`steps/coming.py` takes 59 s)

## Live check 2 (2026-09-27 ~11:10 Dubai)
Real caps and real chains. Every HTTP request was counted independently by host, with `requests` and `curl_cffi`
wrapped, and those counts match the Budget figures exactly.

The price hooks kept 76 layouts (75 distinct shapes). 255 shows got a fresh count and 593 got a certain hall shape.
No `_` key was left on any show.

| chain | shows picked | requests (independently counted) | shows sampled |
|---|---|---|---|
| star | 113 | 60 | 60 |
| roxy | 59 | 59 | 59 |
| reel | 43 | 58 | 19 |
| vox | 275 | 54 | 6 (~9 per sample with the redirects) |
| cineroyal | 50 | 51 | 50 |
| cinemacity | 44 | 44 | 44 |
| novo | 17 | 17 | 17 |
