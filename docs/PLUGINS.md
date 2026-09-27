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

## What a module provides

```python
CSS = ("people",)        # src/css/people.css, appended to cinema.css in module order (minified with it)
JS = ("people",)         # src/js/people.js in the main bundle, just before main.js — it calls feature(fn)
LAZY_JS = ("seatmap",)   # src/js/seatmap.js as /assets/seatmap.<hash>.js, loaded only where a page asks
DIRS = ("people",)       # top-level out/ folders this module writes (cleared before each build)

def register(site) -> Plugin | list[Page]: ...
```

`CSS`, `JS`, `LAZY_JS` and `DIRS` are read without calling `register` (the bundle is made first). `register`
runs once per build, before any page renders, and returns a `Plugin` (from `site_kit`):

| field | meaning |
|---|---|
| `pages` | `Page(parts, lang, build)` — `build()` returns `site.page()`'s keywords: `title`, `desc`, `body`, `kind`, and optionally `graph` (JSON-LD), `attrs`, `nav`, `og_image`, `robots`, `path`, `js` (lazy chunks for this page). Or `Emit(fn)`: a writer that calls `site.page()` itself, many times (the core types do this) |
| `data` | `{"data/<name>.json": obj or fn() -> obj}` — written compact (the /data slice format) after every page |
| `sitemap` | extra path-part tuples, for pages written with `path=`. Pages from `site.page()` are in the sitemap already (Arabic + `/en/` pair, hreflang) |
| `nav` | `NavItem(key, href, label)` — `href` a path or `fn(lang)`, `label` `(ar, en)`. The key `films`, `cinemas`, `thursday` or `cards` re-points that built-in link (Task 2: «نازل الخميس» → `/coming/`); any other key adds a link after «البطاقات». A page passing `nav=key` marks it `aria-current` |
| `slots` | `{slot: fn(site, lang, **ctx) -> html}` — the only places a feature writes into a core page (below) |
| `page_js` | `{page kind: (chunk, …)}` — load a lazy chunk on every page of a kind (`"film"`, `"city"`, `"cinema"`, `"home"` …) |

Order is fixed: core's pages, then each module's pages in module order; then every module's data files; then
the sitemap and the assets.

### Slots in the core pages (`site_kit.Kit.SLOTS`)

| slot | where | ctx |
|---|---|---|
| `home.after_tonight` | home, under «الليلة» | — |
| `city.after_tonight` | a city page, under its «الليلة» | `city` |
| `cinema.after_halls` | a cinema page, after «القاعات والأسعار» | `cid` |
| `film.info` | a film page (showing or archived), after the facts and the trailer | `fid` |

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
    assert '<a href="/hello/">أهلاً</a>' in re.search(r'<nav class="nav".*?</nav>', home, re.S).group(0)
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
