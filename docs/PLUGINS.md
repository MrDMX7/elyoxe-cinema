# Page plug-ins — adding a feature to «سينما» without touching build.py

Phase 2 builds six features in parallel (plan: `docs/superpowers/plans/2026-09-27-phase2.md`). Each lives in
its own files, so no two tasks edit the same generator code:

| file | what it is |
|---|---|
| `pages/<feature>.py` | the page module: its pages, data files, nav links, slots, CSS and JS |
| `src/css/<feature>.css` | its stylesheet partial, appended to `/assets/cinema.css` |
| `src/js/<feature>.js` | its client code, in the main bundle or as a lazy chunk |
| `tests/test_<feature>.py` | its tests |

`build.py` is only the loader. It imports `pages/core.py` first (the phase-1 pages, moved there as they
were), then every other `pages/*.py` **alphabetically** — creating the file is the whole registration. A file
whose name starts with `_` is skipped.

### The core, split by owner (W1-P1, MASTER-PLAN §5.2 and §6.2)

The three hot files ten Wave 2 packages would otherwise share are split along the file-ownership table, so two
packages never edit the same generator code, stylesheet or helper:

| was | now | Wave 2 owner |
|---|---|---|
| `pages/core.py` CorePages | `pages/_core/home.py` (home, its rows) | W2-P4 |
| | `pages/_core/bill.py` (the billboard) | W2-P1 |
| | `pages/_core/film.py` (film page, archived film) | W2-P3 (W2-P1 the hero's picture) |
| | `pages/_core/places.py` (city, cinema, `/cinemas/`) | W2-P6 |
| | `pages/_core/money.py` (cards, halls, `/sources/`) | W2-P9 |
| | `pages/_core/edge.py` (404, offline) | W2-P10 |
| | `pages/core.py` keeps `register`, the module lists, the `/data` slices, the old ids' redirects | — |
| `site_kit.py` Kit | `kit/media.py` (poster, backdrop) | W2-P1 |
| | `kit/tile.py` (tiles, a home row, the «كل الأفلام» grid) | W1-P2, then W2-P4 |
| | `kit/sched.py` (show ids, time buttons, compact times, `live_halls`) | W2-P3 |
| | `kit/ticket.py` (the ticket, the show it opens on, directions) | W2-P3 |
| | `kit/chrome.py` (header tools, tab bar, footer, sheets, the near line) | W1-P2, then W2-P5 |
| | `kit/filters.py` (the filter sheet's **content**: genre, «مع منو», «لازم يخلص قبل», language, sort, prayer) | W2-P4 (the sheet's mechanics stay W2-P5's) |
| | `site_kit.py` keeps Kit's state, names, price cells, `fit`, crumbs, JSON-LD, slots, `page()`, `write()` | — |
| `src/cinema.css` | `src/cinema.css`: tokens, fonts, element defaults, buttons, chips, the price cell, page heads, switches, the 404's old `.nf`, the `[hidden]` rule | W1-P2 |
| | `src/css/ui-{chrome,tabs,sheet}.css` | W2-P5 |
| | `src/css/ui-{bill,fhero}.css` and the stub `ui-lights.css` | W2-P1 |
| | `src/css/ui-{near,rows,tile,grid}.css` | W2-P4 |
| | `src/css/ui-{film,sched,dock,ticket}.css` | W2-P3 |
| | `src/css/ui-places.css`, `ui-money.css` | W2-P6, W2-P9 |
| | `src/css/ui-edge.css` (page-scoped: the 404 only; empty until the leader) | W2-P10 |
| | the stub `src/css/ui-paper.css` (the stub's paper) | W1-P2 |

`pages/_core/` is a package, not a page module: discovery reads top-level `pages/*.py` only. Its files are mixins
of `pages.core.CorePages`; `kit/*.py` are mixins of `site_kit.Kit` (site_kit imports them once its helpers exist:
a page module still imports `site_kit`, never `kit`). The partials are listed in `pages/core.py` `CSS` in cascade
order; `/assets/cinema.css` is still one sheet, and `build.css_source()` returns its source in that order (tests
that pin a rule read it there, wherever the rule lives).

**Empty stubs, Wave 2 only:** `src/js/chrome.js`, `src/js/places.js` (main bundle), `src/js/drag.js` (lazy),
`src/css/ui-paper.css`, `src/css/ui-lights.css`, `src/css/ui-edge.css` are declared in core's tuples already, so no Wave 2 package edits
`pages/core.py` or `build.py` to add them. A Wave 3–4 feature declares its own files in its own module.

## What a module provides

```python
CSS = ("people",)        # src/css/people.css, appended to cinema.css in module order (minified with it)
JS = ("people",)         # src/js/people.js in the main bundle, just before main.js — it calls feature(fn)
LAZY_JS = ("seatmap",)   # src/js/seatmap.js as /assets/seatmap.<hash>.js, loaded only where a page asks
PAGE_CSS = {"coming": ("coming",)}   # src/css/coming.css as /assets/page-coming.<hash>.css, linked only on that kind
DIRS = ("people",)       # top-level out/ folders this module writes (cleared before each build)

def register(site) -> Plugin | list[Page]: ...
```

`CSS`, `JS`, `LAZY_JS`, `PAGE_CSS` and `DIRS` are read without calling `register` (the bundle is made first).

**`PAGE_CSS` (W1-P1):** `{page kind: (names…)}`. The partials of a kind are minified into one small second sheet,
`/assets/page-<kind>.<hash>.css`, linked right after `cinema.css` on pages of that kind only. The default for a
page that is one kind (`/coming/`, `/me/`, `/v/`, the 404): the shared sheet has about 1 KB of margin under its
19 KB guard. A kind whose partials hold only comments gets no link at all. `register`
runs once per build, before any page renders, and returns a `Plugin` (from `site_kit`):

| field | meaning |
|---|---|
| `pages` | `Page(parts, lang, build)` — `build()` returns `site.page()`'s keywords: `title`, `desc`, `body`, `kind`, and optionally `graph` (JSON-LD), `attrs`, `nav`, `og_image`, `robots`, `path`, `js` (lazy chunks for this page). Or `Emit(fn)`: a writer that calls `site.page()` itself, many times (the core types do this) |
| `data` | `{"data/<name>.json": obj or fn() -> obj}` — written compact (the /data slice format) after every page |
| `sitemap` | extra path-part tuples, for pages written with `path=`. Pages from `site.page()` are in the sitemap already (Arabic + `/en/` pair, hreflang) |
| `nav` | `NavItem(key, href, label)` — `href` a path or `fn(lang)`, `label` `(ar, en)`. The key `films`, `cinemas`, `thursday` or `cards` re-points that built-in header link (and the phone tab bar's, for `cinemas`/`thursday`; e.g. «نازل قريب» → `/coming/`); any other key adds a link to the **footer's** row (UI redesign Task 2: the header keeps its four; `q` and `people` come first, in the spec's order, then the rest in module order). A page passing `nav=key` marks it `aria-current` |
| `slots` | `{slot: fn(site, lang, **ctx) -> html}` — the only places a feature writes into a core page (below) |
| `page_js` | `{page kind: (chunk, …)}` — load a lazy chunk on every page of a kind (`"film"`, `"city"`, `"cinema"`, `"home"` …); the kind `"*"` is every page (the search chunk) |

Order is fixed: core's pages, then each module's pages in module order; then every module's data files; then
the sitemap and the assets.

### Slots in the core pages (`site_kit.Kit.SLOTS`)

| slot | where | ctx |
|---|---|---|
| `home.after_tonight` | home, after its rows, before «كل الأفلام» (UI redesign Task 3) | — |
| `city.after_tonight` | a city page, under its «الليلة» | `city` |
| `cinema.after_halls` | a cinema page, after «القاعات والأسعار» | `cid` |
| `film.info` | a film page (showing or archived): the «عن الفيلم» tab, after the synopsis and the facts (UI redesign Task 4) | `fid` |
| `film.share` | a film page: the hero's actions, after «الإعلان» (a ghost button; pages/og.py's «شارك») | `fid` |
| `film.cast` | a film page: the «الطاقم» tab (pages/people.py) | `fid` |
| `film.similar` | a film page: the «شي يشبه» tab (pages/insights.py; an archived film gets core's tiles) | `fid` |
| `film.double` | a film page: the «فيلمين ورا بعض» tab. Nothing fills it since W0-P2 (MASTER-PLAN §4.1 #14: the all-cities pairs were past times), so the tab is not drawn; W2-P6 retires the slot | `fid` |
| `film.compare` | a film page: the «قارن» tab (pages/insights.py); the hero's «قارن» links to it | `fid` |
| `head.inline` | every page's `<head>`, right after the «js» class script: a small inline script that must run before first paint (W3-P1's `has-me`) | `kind` |
| `home.after_bill` | home, right under the billboard (and its visually hidden h1): the board (W2-P2) | — |
| `home.after_board` | home, under the board and above the rows: the Thursday band (W2-P7) | — |
| `film.first` | a showing film's page, between the hero and the day bar: «أقرب عرض لك» (W2-P2); counted in the schedule's budget | `fid` |
| `cinema.top` | a cinema page, under its head: the board's rows (W2-P2); in the budget | `cid`, `city` |
| `city.hero` | a city page with cinemas, under its head: the board's rows (W2-P2); in the budget | `city` |
| `notfound.body` | the 404, under its head: the leader's rows (W2-P2, W2-P10) | — |
| `offline.body` | the offline page, before its English line; self-contained markup (that page has no site stylesheet) | — |
| `ticket.actions` | the ticket's actions row, after «أرسلها للقروب» (W2-P3); counted with the ticket | `show` (the show's dict) |
| `sources.body` | `/sources/`, after the chains' list: «كيف نختار لك» (W2-P2) | — |

The last ten are Wave 2's (W1-P1 declared them before anyone fills them). A Wave 3–4 slot (`home.personal`,
`home.because`, `film.hero_actions`) is declared, with its one `self.slot(...)` line, by the package that fills it.

On the film page a tab is drawn only when its slot (or core's own part) has something to show; with no script
the tabs are links to the sections, stacked in the tabs' order.

A slot's markup counts against the page's budget (the schedules shrink to fit what is left). An unknown slot
name fails the build. Need another place? Add it to `Kit.SLOTS` and one `self.slot(...)` line in core —
review that change on its own, since it touches the shared file.

## The kit: never copy a helper

Feature modules import from `site_kit` only (never `build`):

- **text**: `esc`, `L(pair, lang)`, `P(lang, *parts)` (site paths, Arabic at the root, English under `/en/`),
  `dates(escaped)` (isolates ISO dates and percentages so an RTL run cannot flip them), `num`, `money`,
  `human_date`, `span_dates`, `ar_count`, `ago`, `lang_words`, `genre_words`, `genre_label`, `film_flags`
- **tables**: `CITIES`, `CITY`, `T`, `UI`, `VERDICT`, `LANGS`, `CHAIN_SITE`, `SITE`
- **budgets**: `PAGE_TARGET` (125 KB aim under the 150 KB rule), `CHROME`, `SCHED_BUDGET`, and `site.fit(render, modes, budget)`
- **the site** (`register(site)` receives it): `site.films`, `site.cinemas`, `site.shows`, `site.showing`,
  `site.cards`, `site.rules`, `site.today`, `site.now`; markup `site.page()`, `site.crumbs()`,
  `site.breadcrumb_ld()`, `site.poster()`, `site.film_tile()`, `site.posters_row()`, `site.pcell()` (a price cell
  the client reprices after the visitor's card), `site.min_cell()`, `site.times()`, `site.tbtn()`,
  `site.ticket()`, `site.card_row()`, `site.movie_ld()`, `site.theater_ld()`, `site.screening_ld()`,
  `site.write()` (every file: Western digits enforced)
- `Pages(site)`: a base class whose `self.x` reads through to the site — write methods the way core does.
- **the show key** (W1-P1): `Kit.show_key(cinema, date, time, hall)` and `site.show_key_of(show)`: the key of the
  show link `/film/<fid>/#s-<key>` (MASTER-PLAN §2.2), FNV-1a 32-bit over the UTF-8 of «cinema|date|time|hall key»
  (the hall key Kit.hkey gives, «Standard» when none), base36, left-padded to 6. `showKey()` in `src/js/core.js`
  is its twin; `tests/test_showkey.py` holds them equal over every show. The key is 32 bits, so two shows of one film
  can share it by chance (about 1 day's data in 3,800 at 5,000 shows); the page that prints `id="s-<key>"` (W2-P3)
  must find such a twin at build time and keep both reachable, never ship two equal ids. The test only warns on real
  data: the hourly deploy never stops on the day's data.
- **`Kit.week_phase(now)`** (W1-P1): `"wed-eve"` from Wednesday 18:00 UAE, `"thu-sat"` Thursday to Saturday 23:59,
  `"rest"` otherwise; the Thursday band and the rows read it (build with `site.now`).

## The client side

- **Main bundle** (`JS`): the file is concatenated into the bundle's single function scope, so it sees
  every helper (`q`, `qa`, `C`, `city`, `card`, `renderPrices` …). Register start-up work with
  `feature(function () { … })`; it runs after the core has bound the page, and a feature that throws does
  not stop the others. The whole bundle must stay under **45 KB gzipped** (`tests/test_build.py`) — anything
  large or used on few pages is a lazy chunk.
- **Lazy chunk** (`LAZY_JS`): wrapped as `(function (K) { … })(window.CINEMA)` and loaded after start-up on
  the pages that list it (`js=` on a page, or `page_js` by kind). `K` holds `C, lang, AR, page, q, qa, esc,
  fmt, sub, uae, getJSON, get, set, now(), city(), card()`.
- The same minifier as the bundle: no `/*` or line-leading `//` inside strings or regexes.
- **The hook bus** (W1-P1, `src/js/core.js`): `on(ev, fn)` listens, `emit(ev, x)` tells; every handler runs in
  order inside its own try/catch, so one that throws never stops the others. main.js emits:

  | event | when | `x` |
  |---|---|---|
  | `ready` | the last thing start-up does (after every `feature(fn)` ran) | — |
  | `slice` | the city's shows arrived (home, city page), for the city still chosen | `S` |
  | `card` | the visitor picked a card («بدون بطاقة» too) | the card id, `""` for none |
  | `city` | the visitor picked a city | the city |
  | `day` | a day button was chosen | the date |
  | `minute` | at each UAE minute's :00, from one timeout aligned to it and set again even when a minute's work throws (never a free `setInterval`) | `NOW` |

  Wave 2 emits its own the same way (`board`, `stub`, `plan`). A lazy chunk reaches the bus as `K.on` / `K.emit`.
- **UAE time in every timer:** read `NOW`, `nowMin()`, `TODAY` from core.js, never `new Date().getHours()` (a phone
  set to another zone still sees Dubai's clock; `tests/test_js.py` runs core.js under `TZ=America/New_York`).
- **`showKey(cin, date, time, hallKey)`** is in core.js (moved from ticket.js by W1-P1), also as `K.showKey`.
- **`[hidden]` means hidden** (W1-P1): `:where([hidden]:not([data-hold])),:where(:root:not(.js) [hidden])`
  `{display:none!important}` in the base sheet, whatever display a component sets; no one-off `X[hidden]` patch. A
  slot the script fills later and must hold its place (CLS) carries `data-hold` and its own `.js …[hidden]` rule
  (today `.now[data-now]` and `.rail[data-near-row]`); without a script it is hidden like the rest.

## Example: `/hello/` (tests/fixtures/plugins/hello.py)

A module using every hook. As `pages/hello.py` it would drop `ASSET_DIR` and keep `hello.css` / `hello.js`
under `src/css/` and `src/js/`.

```python
"""Example page module (docs/PLUGINS.md): /hello/ in both languages, a data file, a header link, a line under
«الليلة» on home, a stylesheet partial and a lazy script. A real one is pages/<name>.py, files in src/."""
import os

from site_kit import L, NavItem, P, Page, Plugin, ar_count, esc, num

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))   # a real module drops this: src/css and src/js
CSS = ("hello",)          # hello.css, appended to /assets/cinema.css
LAZY_JS = ("hello",)      # hello.js -> /assets/hello.<hash>.js, only on the pages that ask for it
DIRS = ("hello",)         # out/hello/ belongs to this module (cleared before each build)
TITLE = ("أهلاً", "Hello")


def register(site):
    n = len(site.showing)

    def build(lang):
        count = ar_count(n, ("فيلم واحد", "فيلمين", "أفلام", "فيلم")) if lang == "ar" else f"{n} films"
        body = (f'<section class="head wrap">{site.crumbs(lang, (L(TITLE, lang), None))}'
                f'<h1 class="pt">{esc(L(TITLE, lang))}</h1><p class="lead hello">{esc(count)}</p></section>')
        return {"title": L(TITLE, lang), "desc": L(TITLE, lang), "body": body, "kind": "hello", "nav": "hello",
                "graph": [site.breadcrumb_ld(lang, (L(TITLE, lang), P(lang, "hello")))], "js": ("hello",)}

    return Plugin(
        pages=[Page(("hello",), lang, lambda lang=lang: build(lang)) for lang in ("ar", "en")],
        data={"data/hello.json": {"films": n}},
        nav=[NavItem("hello", href=lambda lang: P(lang, "hello"), label=TITLE)],
        slots={"home.after_tonight": lambda site, lang: f'<p class="wrap hello">{num(n)}</p>'})
```

```js
/* src/js/hello.js — a lazy chunk: K is window.CINEMA */
K.qa(".hello").forEach(function (el) { el.setAttribute("data-lang", K.lang); });
```

### Its test (from tests/test_plugins.py)

Build the synthetic fixtures with the module added, then read the output — never the module's internals:

```python
@pytest.fixture(scope="module")
def hello(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("hello"))
    build.build(DATA, DISC, out, noindex=False, modules=build.discover(extra=[HELLO]))
    return out


def test_example_pages_data_sitemap(hello):
    for parts in (("hello",), ("en", "hello")):
        h = read(hello, *parts, "index.html")
        assert '<h1 class="pt">' in h and 'data-page="hello"' in h and '<link rel="canonical"' in h
    n = len([f for f, v in json.load(open(DATA, encoding="utf-8"))["films"].items() if v.get("status") != "archived"])
    assert json.loads(read(hello, "data", "hello.json")) == {"films": n}
    assert "<loc>https://cinema.elyoxe.com/hello/</loc>" in read(hello, "sitemap.xml")


def test_example_nav_and_slot_reach_core_pages(hello):
    home = read(hello, "index.html")
    assert '<a href="/hello/">أهلاً</a>' in re.search(r'<p class="foot-l">.*?</p>', home, re.S).group(0)
    assert home.index('id="tonight"') < home.index('<p class="wrap hello">')


def test_example_css_partial_and_lazy_chunk(hello):
    assert read(hello, "assets", "cinema.css").endswith(".hello{color: var(--gold);}\n")
    url = ct(read(hello, "hello", "index.html"))["chunks"]["hello"]
    assert read(hello, *url.strip("/").split("/")).startswith("(function (K) {")
    assert "chunks" not in ct(read(hello, "index.html"))       # only the pages that ask for it
```

A module in `pages/` is picked up by every build (`build.build(...)` with no `modules=`), so its tests can
build normally; `modules=build.discover(extra=[path])` is for modules kept outside the package.

## The golden test

`tests/test_golden.py` extracts the phase-1 generator from git (`c7ff237`, override with
`CINEMA_GOLDEN_REF`) and builds the fixtures and `data/latest.json` (when present) with both it and the
current code, core module only: same files, same bytes after normalising asset hashes (the client bundle
alone may differ). The full build must only add files. A feature therefore can never change a core page by
accident; filling a slot or re-pointing a nav link changes the full build only. It runs with
`PYTHONHASHSEED=0` because `data/discounts.json` lists chains from a set (its order varies per run).
Skipped where git or the commit is missing (a shallow CI checkout).

## Rules that still bind (phase-1 spec)

Arabic at `/` and English under `/en/` for every page; Western digits (enforced in `site.write`); no invented
numbers, «تقريباً» on every estimate, only confirmed discounts; a page ≤ 150 KB; the main bundle ≤ 45 KB gz.

**The guards (W1-P1, MASTER-PLAN §7.3 #9):** `build.build()` ends with `build.check_budgets(out)`. It **fails the
build** (`BudgetError`) when the initial bundle is over **36 KB gz** or the shared stylesheet over **19 KB gz**, and
warns (`BudgetWarning`) past **34 KB gz** of JS and for any page over 150,000 bytes (a heavy day's data: the hourly
build goes on, and `tests/test_build.py` holds the fixtures and the busiest real day to it with
`check_budgets(out, strict_html=True)`). KB here is 1,000 bytes at gzip -9, as MASTER-PLAN §7 counts it (legend's bundle
was 32.6 KB gz at R0, 32.8 after W1-P1; the shared sheet 13.9). Past the warning line, move code into a lazy chunk or CSS into `PAGE_CSS`
before merging. No top-level name may be declared twice in the bundle (`tests/test_film.py`), and no page may carry
a duplicate `id` (`tests/test_showkey.py`).

**Measuring (§5.0 #6):** every local check serves the build with `tools/serve.py` (an exclusive port, the
package's own, and `X-Served-By: <package>-<sha>` asserted on the document and an asset), and the perf tools
(`tools/lh_gate.sh`, `perf_fx.cjs`, `ttb_bench.cjs`, `idle_check.cjs`) take the laptop's one perf lock
(`tools/perf_lock.cjs`).

## The chrome (UI redesign Task 2)

Every page from `site.page()` gets the same chrome from `src/page.html` and `Kit.chrome()`: the header (mark,
four links, the search button, the city pill `#pill-city`, the card pill `#pill-card`, the other language),
the phone's tab bar (four links: home, cinemas, coming, search), the footer's links, and two sheets.

- `site.sheet(id, (ar, en) title, body_html, lang)` — a sheet: `<div class="sheet" id=… role="dialog"
  aria-modal="true" aria-labelledby=… hidden>`. Any element with `data-sheet-open="ID"` opens it
  (`src/js/sheet.js`: focus kept inside, Esc / × / the scrim / the back button close it, focus returns);
  `data-sheet-close` inside it closes it. One sheet at a time; ids must be unique on the page.
- `site.sheet_city(lang, city)` / `site.sheet_card(lang)` — the pills' sheets (on every page already; a module
  never renders them again). Choosing reuses main.js's `pickCity` / `pickCard` (reprice + persist, pill labels).
- `[data-search]` anywhere opens the search overlay (`src/js/search.js`).
- A page whose kind is in `site_kit.HERO_KINDS` (home, film) gets `data-hero` on `<body>`: the header starts as
  a gradient over its backdrop and turns solid after 40 px.

