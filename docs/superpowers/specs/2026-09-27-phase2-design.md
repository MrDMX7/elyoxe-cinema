# «سينما» Phase 2 — content and intelligence

Owner: «كمل» after reading the phase-2 list (2026-09-27). Scope = docs/ROADMAP.md Phase 2. Identity, budgets and
rules of phase 1 stay binding (docs/superpowers/specs/2026-09-26-phase1-design.md): «هـ» design, Markazi/Readex,
Western digits, no invented numbers, «تقريباً» on estimates, only confirmed discounts, ar + /en/, ≤150 KB pages.

## A. People and pages
- **Cast & directors** of films showing (and archived films' pages link to them): `/people/<slug>/` —
  photo (Wikimedia Commons via Wikidata P18, only freely licensed, attribution line), Arabic/English name,
  a 2-line bio from Wikipedia (ar first, en fallback; cited), «يعرض له الحين» first, then notable films
  (Wikidata, capped). No person page without at least a name + one showing film.
- **«نازل الخميس»** `/coming/`: films announced by the chains (their "coming soon" feeds) with release date,
  poster, trailer, «نبّهني» placeholder for phase 3. Countdown only for dated releases.
- **«آخر فرصة»**: films whose schedule shrinks to its last 2 days in a city (shows exist today/tomorrow, none
  beyond, and seen for ≥ 14 days) — a strip on home + city pages.
- **Gulf & Arabic films** hub `/arabic/`: films in Arabic or produced in the Gulf.
- **Special events** `/events/`: chain-labelled events (festivals like K-Fest, ladies' nights, immersive dining,
  classics), from reader labels, never invented.
- **Question pages** `/q/<slug>/` (40): generated answers to real searches from our data, e.g. «كم سعر تذكرة
  IMAX في دبي؟», «هل فزعة تشتغل في فوكس؟», «أرخص سينما في العين» — each with the numbers and their dates;
  only generated when the data answers it.

## B. Inside the hall
- **Real seat map (45) + crowd (4) + best seat (16)**: from the seat-layout responses the readers already fetch
  for prices, and a light occupancy sample for shows starting within the next 3 hours (≤ 1 req/s, ≤ 60 per
  chain per run, never holding a seat). Ticket shows the hall drawing with free/taken seats and «باقي 23 مقعد»,
  best seat = centre-ish rows 2/3 back, free, by class. Occupancy older than 90 min is not shown.
- **«يستاهل IMAX/MAX؟» (18)**: a line per film only when the film plays in a premium format near you and there is
  a basis (critics mention format / genre spectacle / runtime), written with the verdict (Claude) and cited;
  otherwise nothing.
- **Post-credits (19)**: only from a sourced dataset (Wikipedia/Wikidata or a named site); otherwise nothing.
- **Snacks (46)**: `snacks.yaml` per chain — combo names and prices with source + checked date; card F&B
  discounts from discounts.yaml when official. Shown on cinema pages and in the ticket.

## C. Planning
- **Add to calendar (41)**: .ics download + Google Calendar link from the ticket (title, cinema, address, start,
  «يخلص تقريباً», reminder 60 min).
- **«اطلع من البيت الساعة…» (42)**: with the user's location, drive time ≈ road distance estimate
  (haversine × 1.35 at 60 km/h city / 90 km/h between cities, labelled «تقريباً») + 10 min parking.
- **Double feature (43)**: pairs at the same cinema with a 15–45 min gap.
- **Mall closing (44)**: `malls.yaml` hours per mall with source; shows ending after closing get a note.

## D. Data
- **UAE box office (35)**: films ranked by this week's show count and cinema count (not ticket sales — say so).
- **Price index (36) + price history (56)**: daily snapshots of median price per chain × hall class in
  `data/price_history.jsonl` (kept in the bucket, not git); a page `/prices/` with the index and a chart that
  grows over time; «زاد/نقص» only when ≥ 30 days of data exist.
- **Cheapest time of the week (6)**: from history once ≥ 14 days exist; before that the section is hidden.
- **Compare two films (22)** and **«شي يشبه» (23)**: client compare view; similarity from genres + cast +
  director + language.

## E. Seasons
- **Ramadan & Eid mode (54)**: by Hijri date (the tools' Hijri calc): shows after Taraweeh marked, iftar time per
  city, an Eid releases page when Eid is within 10 days.
- **Kids morning & summer (55)**: a kids preset (G/PG + animation/family, starting before 14:00) and a summer
  page in July–August.

## Politeness and cost
All new chain requests share the daily cache; occupancy sampling is capped as above. Claude calls only for new
films or new formats (IMAX line). No new paid services.
