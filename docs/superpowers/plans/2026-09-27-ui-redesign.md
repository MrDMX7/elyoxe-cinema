# «سينما» UI redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the site's look into the approved Netflix-like layout (billboard, poster rows, one filter sheet, schedule-first film page) without losing any feature.

**Architecture:** Same static generator (build.py + pages/*.py plug-ins + site_kit.Kit helpers + src/js modules bundled by build.py + src/cinema.css and src/css/*.css). New: a backdrop data step, a shared sheet component (JS + CSS) for city/card/filter, rewritten home and film markup, new chrome (header pills, 4-tab bar, footer).

**Tech Stack:** Python 3.13, vanilla JS, CSS, yt-dlp + ffmpeg + Pillow (backdrops), pytest, Playwright (screenshots/QA only, from `C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright`).

**Spec:** `docs/superpowers/specs/2026-09-27-ui-redesign-design.md` — visual reference `docs/superpowers/specs/ui-mock/` (open `*.png`; `mock.css` holds the approved measurements: header, `.bill`, `.row`, `.tile`, `.near`, `.sheet`, `.bar`, `.tb`, `.ticket`, `.dock`, `.tabsx`).

## Global Constraints
- Identity unchanged: tokens in `src/cinema.css :root` (night #0F0B0C, velvet #7A1626, gold #E2B659 only for prices/verdict word/selected, screen #F1EAE0, seat #A89C8E, live #5FC9A0 only for «starting now»/on switches); Markazi Text 700 display, Readex Pro body/numbers; no border-radius, no drop shadows (except the hero poster velvet glow), no middle-dot fact strings, no all-caps, no numbering of non-sequences; logical properties only; Western digits; Emirati copy («عندي» not «معي»).
- **No feature is removed.** Every control and section that exists today must still be reachable (list in Task 5's checklist). Existing localStorage keys, URL params (shareParams), events, `data-aed/data-chain/data-hall` price cells and `data-show` time buttons keep working; JS/Python discount parity tests stay green.
- Arabic at `/`, English at `/en/` — every change in both languages; RTL derived, not mirrored.
- Budgets: HTML ≤ 150 KB/page, JS ≤ 45 KB gz total initial, Lighthouse mobile ≥ 90 on home + a film page; 375 px and 390 px with `scrollWidth == innerWidth` measured by Playwright with `isMobile: true` (headless Chrome's CLI screenshot has a 500 px minimum — never use it for phone checks).
- `prefers-reduced-motion`: no auto-rotation, no lift animations.
- Tests: `python -m pytest -q` must pass; check `$?` directly — never pipe the test command through `tail`/`tee`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; commit on branch `ui-redesign` in worktree `C:/Users/requi/cinema-ui`; never push, never deploy, never touch S3/CloudFront (the controller releases).
- Windows paths inside strings use forward slashes.

---

### Task 1: Trailer backdrops data step
**Files:** create `steps/backdrops.py`, `tests/test_backdrops.py`; modify `refresh.py` or the steps registry (follow how `steps/og.py` is registered), `site_kit.py` `Kit.backdrop()` to prefer the new files, `run.sh` only if posters upload needs the new prefix, `.gitignore` for the work dir.
**Produces:** `data/backdrops.json` `{fid: {"trailer": id, "w1280": "/posters/bd-<fid>-<h>-1280.webp", "w640": "...-640.webp", "t": seconds, "at": iso}}` plus failure entries `{fid: {"trailer": id, "fail": iso}}`; `Kit.backdrop(fid, hero)` returns markup using these (with `srcset` 640/1280, `sizes=100vw`, `fetchpriority=high` + eager when `hero`), falling back to today's poster-based backdrop.
- [ ] Frame scorer as a pure function `score_frame(img: PIL.Image) -> float | None` (None = reject): reject mean luma < 35 or > 200; reject when edge density (Pillow `FIND_EDGES`, threshold) in the bottom 22% band is > 2.2× the frame's median band density (burned subtitles) or a centred horizontal band has text-like density with a flat surround (title cards); otherwise score = colourfulness (Hasler–Süsstrunk) × mid-tone weight. Tests with synthetic images: black frame rejected, white frame rejected, a gradient with white text drawn in the bottom band rejected, the same gradient without text accepted, the more colourful of two accepted frames wins.
- [ ] `crop_letterbox(img)` removes black bars (rows whose mean luma < 12 from top/bottom); test with a padded synthetic image.
- [ ] Pipeline: yt-dlp `-f "bv*[height<=720][ext=mp4]/bv*[height<=720]"` to a temp dir under the work dir, ffprobe duration, ffmpeg seek 16 frames between 12% and 80%, score, pick best, save WebP q80 at 1280 and 640 width; hash = first 10 hex of sha1 of the chosen JPEG bytes. Cache per fid+trailer; failure cached 7 days; at most 8 new films per run (`CINEMA_BACKDROPS_MAX` env override); delete the downloaded video after each film; a film's failure never fails the step. Only films currently showing or coming.
- [ ] Test the pipeline orchestration with yt-dlp/ffmpeg mocked (subprocess patched): cache hit skips, failure cached, cap respected, video deleted.
- [ ] Wire the step so the backdrop WebPs land wherever posters are uploaded from (read `run.sh`/`steps` and follow the posters path — they must reach S3 `posters/` on deploy). Run it for real on the laptop against `data/latest.json` for the top 10 films; open 3 results and confirm they are clean frames (report which).

### Task 2: Chrome — header pills, sheets, tab bar, footer
**Files:** `site_kit.py` (`Kit.page`, `nav_links`, `me`, `card_chips`, new `Kit.sheet_city`, `Kit.sheet_card`), `src/page.html`, `src/cinema.css` (header/nav/foot/sheet sections), new `src/js/sheet.js` (generic open/close/focus-trap/escape/back-button for any `[data-sheet]`), `src/js/main.js`/`core.js` (city/card state hooks — reuse the existing state functions, do not duplicate), `pages/core.py` `sources()` → a standalone sources/freshness page if it is not one already, tests.
**Produces:** `Kit.sheet(id, title_ar_en, body_html, lang)` markup contract `<div class="sheet" id=… role="dialog" aria-modal="true" aria-labelledby=… hidden>`; any `<button data-sheet-open="ID">` opens it. City pill `#pill-city`, card pill `#pill-card` whose labels JS keeps in sync with state.
- [ ] Header per spec/mock: mark, desktop links, search button (opens existing search overlay), city pill, card pill, English/Arabic link; `.top` transparent-gradient over pages with a hero (`data-hero` on body), solid otherwise and after 40 px scroll (IntersectionObserver sentinel, not a scroll listener).
- [ ] City sheet: 7 cities + «قريب مني» (existing geolocation/near code). Card sheet: «بدون بطاقة» + confirmed cards grouped (حكومية / بنوك) as a list of radio-like buttons — replaces the bank `<select>`. Selecting updates state via the existing functions (reprice + persist), updates pill labels, closes the sheet.
- [ ] Phone tab bar: 4 items with inline SVG icons (home, pin, calendar, search) — الرئيسية، السينمات، نازل قريب، بحث; `aria-current` on the active one. Desktop hides it.
- [ ] Footer: mark + links (السينمات، البطاقات والخصومات، من وين الأسعار، أسئلة، الناس، English/العربية); chain freshness list moves to the sources page.
- [ ] No-JS: pills are links to `/cinemas/` and the cards page; sheets hidden.
- [ ] Tests: golden/markup tests updated; a test that every page has exactly one header, one tab bar with 4 links, the two pills, and no duplicate ids.

### Task 3: Home
**Files:** `pages/core.py` `home()`, `site_kit.py` (`film_tile` → new tile markup, `posters_row` → row markup with «الكل» link and desktop arrow buttons), `src/js/home.js`, `src/js/filters.js`, `src/js/near.js`, `src/cinema.css` (bill/row/tile/near/grid/filter sheet), tests.
**Consumes:** Task 1 `Kit.backdrop`, Task 2 `Kit.sheet` + pills.
- [ ] Billboard with the city's top 5 (server renders film 1 for the default city plus a JSON island of the top 5 per city: fid, titles, verdict word + text, facts, min after-card inputs, backdrop urls, trailer id); JS swaps content on city change and rotates every 6 s (pause on hover/focus/hidden tab/reduced motion), indicator buttons are real buttons with labels. CTA price follows the card state through the existing reprice path.
- [ ] «يبدأ قريب منك» row from the existing now/near logic (live green «بعد N د»); hidden when there is nothing in the next 3 hours.
- [ ] Rows in order: الأكثر عرضاً الليلة، يستاهل، أرخص لك الليلة، للعائلة، نازل الخميس، آخر فرصة، عربي (+ any existing season/hub rows after them); skip rows under 4 films; each «الكل» goes to an existing page or `#all` with the matching filter preselected via URL param.
- [ ] Tile markup per mock (poster, one-line title, from-price or «السعر في الشباك», optional corner tag); desktop hover panel with verdict word + next time without layout shift; all existing `data-*` filter attributes stay on the tile.
- [ ] «كل الأفلام» grid (3/7 cols) + «تصفية» chip with active-count badge + sort chip; the filter sheet contains every current home control (genres, companions, ends-before, language, sort, prayer switch) and «اعرض N فيلم» (live count) / «مسح». Filtering behaviour is the existing filters.js logic moved, not rewritten.
- [ ] Home no longer renders the cities grid, cards list or freshness list.
- [ ] Tests updated; home HTML ≤ 150 KB in both languages (assert in test).

### Task 4: Film page
**Files:** `pages/core.py` `film_pages()`, `film_schedule()`, `similar()`, `archive_note()`, `site_kit.py` (`tbtn`, `times`, `ticket`), `src/js/ticket.js`, `src/js/main.js`, new small `src/js/tabs.js`, `src/cinema.css` (fhero/bar/schedule/dock/tabs), and whichever pages plug-ins inject film-page sections (compare, back-to-back «فيلمين ورا بعض», people/cast, seatmap) — keep their content, move their placement into tabs, tests.
- [ ] Hero per mock (backdrop, desktop poster with velvet glow, AR + EN title + year, verdict with «المزيد», facts, actions الإعلان/شارك/قارن + existing alert button).
- [ ] Sticky day bar under the header (top offset = header height) with the existing day switching; prayer switch moves into a «⋯» sheet at the bar's end.
- [ ] Schedule directly after the bar: chosen city's cinemas sorted nearest-first (existing near logic), time buttons with time/hall/after-card price, past faded, next one «يبدأ بعد N د»; other cities under one disclosure per city.
- [ ] Ticket: desktop = the existing ticket rendered as a sticky side column (empty state «اختر وقت»); phone = bottom dock (price, time/cinema/hall, «التفاصيل والحجز») that opens the existing ticket sheet. Seat table, terms, share, Maps/Waze, seat map unchanged.
- [ ] Tabs (عن الفيلم، الطاقم، شي يشبه، فيلمين ورا بعض، قارن) as an accessible tablist (arrow keys, `aria-selected`, panels `hidden`); no-JS = anchor links with all panels visible; `#hash` deep links open the right tab.
- [ ] The repeated «أنا في … وعندي» block is gone from the film page.
- [ ] Archived films (ended) keep their archive layout («عُرض من … إلى …» + «المعروض الحين») inside the new hero/chrome.
- [ ] Tests updated; film HTML ≤ 150 KB.

### Task 5: Every other page, cleanup, QA
**Files:** all `pages/*.py` using the old `.me`/controls/tiles, `src/cinema.css` + `src/css/*.css` dead rules, `tests/`, new `tools/shots.cjs` (Playwright: pages × {390×844 mobile, 1440×900} × {ar, en}, prints `innerWidth scrollWidth`, full screenshots to `out/_shots/`).
- [ ] City, cinema, cards, halls, coming, seasons, hubs, people, people index, insights, questions, venue, search, 404, offline: new chrome, new tiles/rows where they list films, page-top control rows removed in favour of the pills.
- [ ] Delete CSS/JS that nothing references any more (grep each selector/function before deleting).
- [ ] Feature checklist — each must be reachable, write where in the report: city choice, card choice (all confirmed cards), nearest/«الحين», genre filter, companions, ends-before, language, sort, prayer switch, trailer, share (film + ticket + og), compare, back-to-back, similar, cast/people pages, seat map, ticket with per-seat prices and terms, Maps/Waze, archive pages, search overlay, PWA install/offline, new-film alert, coming page, seasons/hubs/insights/questions pages, English mirror.
- [ ] Build both languages; run `tools/shots.cjs` against a local static server of `out/`; every page reports `scrollWidth == innerWidth` at 390; Lighthouse mobile (npx lighthouse or the CI critique job's command) ≥ 90 on home + one film; budgets hold. Attach the screenshot paths in the report.
