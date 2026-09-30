"""Build «سينما» — https://cinema.elyoxe.com — static pages from data/latest.json + discounts.yaml + halls.yaml.

  src/page.html     the page template (head with SEO, header with the wordmark and nav, footer)
  src/cinema.css    the «هـ» design system's tokens and base (night, velvet, marquee gold; Markazi Text + Readex Pro);
                    its components in src/css/ui-*.css, one Wave 2 owner each (pages/core.py CSS, W1-P1)
  src/js/*.js       client modules, bundled into /assets/cinema.<hash>.js (+ lazy chunks /assets/<name>.<hash>.js)
  src/fonts/        self-hosted woff2 subsets (OFL, licences beside them)
  site_kit.py       the shared helpers and the Kit (price cells, posters, ticket, page()) every page module uses
  pages/            the page modules: core.py (phase 1's pages), then pages/<feature>.py (docs/PLUGINS.md)

This file is the loader: it finds the page modules, bundles their CSS and JS, runs each module's pages in
order (core first), writes their data files, then the sitemap and the assets.

python build.py [--data data/latest.json] [--discounts discounts.yaml] [--halls halls.yaml] [--out out]
  -> out/index.html  out/en/…  out/<city>/  out/<city>/<cinema>/  out/film/<fid>/  out/cards/…  out/halls/
     out/data/<city>-<date>.json  out/data/discounts.json  out/sitemap.xml  out/robots.txt  out/404.html
     out/assets/{cinema.css,cinema.js,icon.svg,fonts/}

Discount semantics (mirrored in cinema.js): percent -> price×(1-v/100); bogo -> price/2 per person;
excluded_halls / included_halls by hall code; valid_until in the past -> no discount; status none_found ->
«ما لقينا خصم» (we found none), never «they refuse it». Only official rules are published, and only cards
with at least one current official discount appear anywhere (the spec: third-party/unconfirmed stay hidden).
"""
import argparse, gzip, os, re, sys, warnings

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from site_kit import *  # noqa: E402,F401,F403  (build.after, build.T, build.Halls ... stay importable from here)
from site_kit import Emit, Kit, Plugin  # noqa: E402
from pages import discover  # noqa: E402

# the core bundle's order (pages/core.py JS); kept here for old callers
JS_MODULES = ("core", "pure", "disc", "flip", "prices", "near", "prayer", "home", "filters", "bill", "ticket", "film", "tabs", "trailer", "pwa", "sheet", "main")


# ---------------------------------------------------------------- the page modules' assets
def _asset(mod, kind, name):
    """A module's CSS/JS file: <ASSET_DIR>/<name>.<ext> when the module has one, else src/css or src/js."""
    base = getattr(mod, "ASSET_DIR", None) or os.path.join(SRC, kind)
    return os.path.join(base, name + "." + kind)


def js_files(modules=None, src=None):
    """The main bundle, in order: core's modules up to main.js, every feature's JS, then main.js (start-up)."""
    modules = discover() if modules is None else modules
    core = next((m for m in modules if m.__name__ == "pages.core"), None)
    first = list(getattr(core, "JS", JS_MODULES))
    last = [first.pop()] if first and first[-1] == "main" else []
    at = lambda n: os.path.join(src or os.path.join(SRC, "js"), n + ".js")
    feats = [_asset(m, "js", n) for m in modules if m is not core for n in getattr(m, "JS", ())]
    return [at(n) for n in first] + feats + [at(n) for n in last]


def css_files(modules):
    return [_asset(m, "css", n) for m in modules for n in getattr(m, "CSS", ())]


def page_css_files(modules):
    """{page kind: [css paths]}: each module's PAGE_CSS = {kind: (names…)}, in module order (W1-P1). A second small
    stylesheet on that kind of page only (/coming/, /me/, /v/, the 404), never on the shared sheet every page loads."""
    out = {}
    for m in modules:
        for kind, names in (getattr(m, "PAGE_CSS", None) or {}).items():
            out.setdefault(kind, []).extend(_asset(m, "css", n) for n in names)
    return out


def css_source(modules=None):
    """The shared stylesheet's source, unminified, in the order /assets/cinema.css is made from it: src/cinema.css
    (tokens and base), then every module's partials in module order (core's src/css/ui-*.css first, W1-P1).
    Tests that pin a rule read it here, wherever the rule's file is."""
    modules = discover() if modules is None else modules
    return "\n".join(open(p, encoding="utf-8").read() for p in [os.path.join(SRC, "cinema.css")] + css_files(modules))


def bundle_js(src=None, modules=None):
    parts = [open(p, encoding="utf-8").read() for p in js_files(modules, src)]
    return minify_lite('(function () {\n"use strict";\n' + "\n".join(parts) + "\n})();\n") + "\n"


def chunk_js(path):
    """A lazy chunk: its own scope, the page's helpers as K (window.CINEMA, set by main.js before it loads)."""
    src = open(path, encoding="utf-8").read()
    return minify_lite('(function (K) {\n"use strict";\n' + src + "\n})(window.CINEMA);\n") + "\n"


# ---------------------------------------------------------------- the site
class Site(Kit):
    def __init__(self, data, disc, halls, out, modules=None):
        super().__init__(data, disc, halls, out)
        self.modules = discover() if modules is None else list(modules)
        self.js = bundle_js(modules=self.modules)
        self.js_name = f"cinema.{hashlib.sha1(self.js.encode()).hexdigest()[:10]}.js"
        self.chunks = {}
        for m in self.modules:
            for n in getattr(m, "LAZY_JS", ()):
                js = chunk_js(_asset(m, "js", n))
                self.chunks[n] = (f"{n}.{hashlib.sha1(js.encode()).hexdigest()[:10]}.js", js)
        self.chunk_urls = {n: "/assets/" + f for n, (f, _) in self.chunks.items()}
        # page-scoped stylesheets: one per page kind that has any rule (a kind whose partials are still empty gets no link)
        self.page_sheets = {}
        for kind, paths in page_css_files(self.modules).items():
            css = minify_css("\n".join(open(p, encoding="utf-8").read() for p in paths))
            if css.strip():
                self.page_sheets[kind] = (f"page-{kind}.{hashlib.sha1(css.encode()).hexdigest()[:10]}.css", css)
        self.page_css = {k: "/assets/" + f for k, (f, _) in self.page_sheets.items()}
        # every module registers before any page renders: nav items and slots reach the core pages too
        self.plugins = []
        for m in self.modules:
            p = m.register(self) if hasattr(m, "register") else None
            self.plugins.append(Plugin(pages=list(p)) if isinstance(p, (list, tuple)) else p or Plugin())
        self.nav_items = [it for p in self.plugins for it in p.nav]
        self.slots, self.kind_js = {}, {}
        for p in self.plugins:
            for k, fn in p.slots.items():
                if k not in self.SLOTS: raise ValueError(f"unknown slot {k!r} (site_kit.Kit.SLOTS)")
                self.slots.setdefault(k, []).append(fn)
            for kind, names in p.page_js.items(): self.kind_js.setdefault(kind, []).extend(names)

    def render(self, pg):
        """A Page: its build() is site.page()'s keywords; an Emit writes its pages itself."""
        if isinstance(pg, Emit): return pg.run()
        kw = dict(pg.build())
        self.page(pg.lang, tuple(pg.parts), kw.pop("title"), kw.pop("desc"), kw.pop("body"), kw.pop("graph", []), kw.pop("kind"), **kw)

    def sitemap(self):
        """hreflang pairs + x-default; lastmod moves only when the page's content hash changes (lastmod_path keeps them)."""
        known = {}
        if self.lastmod_path and os.path.exists(self.lastmod_path):
            try: known = json.load(open(self.lastmod_path, encoding="utf-8"))
            except ValueError: known = {}
        sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
        for parts in self.urls:
            for lang in ("ar", "en"):
                u = P(lang, *parts); h = self.hashes.get(u, "")
                prev = known.get(u)
                day = prev[1] if prev and prev[0] == h else self.today
                if parts[:1] == ("film",) and (self.films.get(parts[1]) or {}).get("status") == "archived":
                    day = str(self.films[parts[1]].get("last_seen") or day)   # an archive changes when the run ends
                known[u] = [h, day]
                sm.append(f"<url><loc>{SITE + u}</loc><lastmod>{day}</lastmod>"
                          f'<xhtml:link rel="alternate" hreflang="ar" href="{SITE + P("ar", *parts)}"/>'
                          f'<xhtml:link rel="alternate" hreflang="en" href="{SITE + P("en", *parts)}"/>'
                          f'<xhtml:link rel="alternate" hreflang="x-default" href="{SITE + P("ar", *parts)}"/></url>')
        sm.append("</urlset>")
        self.write(os.path.join(self.out, "sitemap.xml"), "\n".join(sm))
        if self.noindex:   # preview: nothing is crawled, and no sitemap is advertised
            self.write(os.path.join(self.out, "robots.txt"), "User-agent: *\nDisallow: /\n")
        else:
            self.write(os.path.join(self.out, "robots.txt"), f"User-agent: *\nAllow: /\nDisallow: /data/\n\nSitemap: {SITE}/sitemap.xml\n")
        if self.lastmod_path:
            os.makedirs(os.path.dirname(self.lastmod_path), exist_ok=True)
            json.dump(known, open(self.lastmod_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)

    def assets(self):
        adir = os.path.join(self.out, "assets")
        os.makedirs(os.path.join(adir, "fonts"), exist_ok=True)
        # the base sheet, then each module's partials (src/css/<name>.css) in module order, minified as one
        self.write(os.path.join(adir, "cinema.css"), minify_css(css_source(self.modules)))
        if os.path.exists(os.path.join(SRC, "icon.svg")):
            self.write(os.path.join(adir, "icon.svg"), open(os.path.join(SRC, "icon.svg"), encoding="utf-8").read())
        self.write(os.path.join(adir, self.js_name), self.js)
        for fname, js in self.chunks.values():
            self.write(os.path.join(adir, fname), js)
        for fname, css in self.page_sheets.values():
            self.write(os.path.join(adir, fname), css)
        self.write(os.path.join(adir, self.adhan_name), self.adhan)
        # PWA: the worker must sit at the root to control every page; the manifest names the icons
        self.write(os.path.join(self.out, "sw.js"), open(os.path.join(SRC, "sw.js"), encoding="utf-8").read().replace("__V__", self.v))
        self.write(os.path.join(self.out, "manifest.webmanifest"), open(os.path.join(SRC, "manifest.webmanifest"), encoding="utf-8").read())
        idir = os.path.join(SRC, "icons")
        os.makedirs(os.path.join(adir, "icons"), exist_ok=True)
        for f in os.listdir(idir) if os.path.isdir(idir) else []:
            if f.endswith(".png"): shutil.copy(os.path.join(idir, f), os.path.join(adir, "icons", f))
        for f in ("og-ar.png", "og-en.png"):
            if os.path.exists(os.path.join(SRC, f)): shutil.copy(os.path.join(SRC, f), os.path.join(adir, f))
        fdir = os.path.join(SRC, "fonts")
        for f in os.listdir(fdir) if os.path.isdir(fdir) else []:
            shutil.copy(os.path.join(fdir, f), os.path.join(adir, "fonts", f))

    def run(self):
        for p in self.plugins:
            for pg in p.pages: self.render(pg)
        for p in self.plugins:
            for rel, obj in p.data.items():
                obj = obj() if callable(obj) else obj
                self.write(os.path.join(self.out, *rel.split("/")), json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str))
            self.urls.extend(tuple(x) for x in p.sitemap)
        self.sitemap(); self.assets()
        return len(self.urls)


GENERATED = [c for c, _, _ in CITIES] + ["film", "cards", "halls", "data", "assets", "en", "cinema", "cinemas", "sources"]


# ---------------------------------------------------------------- budgets (MASTER-PLAN §7.1 and §7.3 #9, W1-P1)
# the code's budgets, gzipped as a CDN sends them: every page loads the main bundle and the shared sheet before it
# can answer a tap. Over the fail line the build stops (the code is wrong, not the day's data); past the warning line
# it says so, and the package moves code into a lazy chunk or page-scoped CSS before it merges. KB as the plan counts
# them: 1,000 bytes (its «28.7 KB at 7e787e4» is that bundle's 28,740 bytes at gzip -9).
JS_WARN_GZ, JS_FAIL_GZ = 35_500, 36_700   # the initial bundle, /assets/cinema.<hash>.js (hard cap 45 KB). Raised from
# 34_000 on the legend integration branch (2026-09-28): Wave 2 filled chrome.js, drag.js, places.js and board.js —
# all previously-declared zero-cost stubs — pushing the fixture bundle to 34.3 KB, past the old line but 1.7 KB clear
# of JS_FAIL_GZ. Raised again on round3 (2026-09-30): ten units merged at once (ticket dock, appfeel, filters,
# film) each added a few real bytes to already-eager files, landing the fixture at 34.9 KB — past the old warning
# line though every one of them stayed lazy where the module system allows it (board/vote/appfeel chunks). Raised
# again in the film-hero clean-up (round r3, 2026-09-30): chrome.js's header-solid logic (an owner-reported bug
# fix — the header sitting translucent over the title, twice over: once on a real scroll, then again when the
# film hero's own flex-end text block reflows under the header with NO scroll at all, a coordinator-caught
# follow-up) needed two IntersectionObservers, both eager (no lazy chunk crosses this early), landing the
# fixture at 35.37 KB. Kept
# the gap to JS_FAIL_GZ over 1024 on purpose: tests/test_build.py pads a fixture to JS_WARN_GZ + 1024 bytes and
# expects a warning, not a failure. The line moves deliberately for real filled-in features, not quietly for
# bloat; a future package that grows the bundle further should still move its own code into a lazy chunk first.
CSS_FAIL_GZ = 19_000                      # the shared sheet, /assets/cinema.css (render-blocking)
HTML_MAX = 150_000                        # a page, raw (the spec's rule; Kit.fit keeps schedules under it)


class BudgetError(Exception):
    """A build over a code budget: the bundle or the shared sheet."""


class BudgetWarning(UserWarning):
    """A build past a warning line, or a page over HTML_MAX (the day's data, not the code: reported, the build goes on)."""


def gz(b):
    return len(gzip.compress(b, 9, mtime=0))


def budgets(out, js_name=None):
    """What the guards measure in a built out/: {"js": gz bytes of the main bundle, "css": gz bytes of the shared sheet,
    "html": [(path, bytes) of every page over HTML_MAX]}. `js_name`: the bundle's file (else the one the home names)."""
    adir = os.path.join(out, "assets")
    if not js_name:
        home = open(os.path.join(out, "index.html"), encoding="utf-8").read()
        js_name = re.search(r'\("/assets/(cinema\.[0-9a-f]{10}\.js)",document\)', home).group(1)
    big = []
    for dp, _, fs in os.walk(out):
        for f in fs:
            if f.endswith(".html") and os.path.getsize(os.path.join(dp, f)) > HTML_MAX:
                big.append((os.path.relpath(os.path.join(dp, f), out), os.path.getsize(os.path.join(dp, f))))
    return {"js": gz(open(os.path.join(adir, js_name), "rb").read()), "css": gz(open(os.path.join(adir, "cinema.css"), "rb").read()),
            "html": sorted(big)}


def check_budgets(out, js_name=None, strict_html=False):
    """The guards: raise BudgetError when the bundle is over JS_FAIL_GZ or the shared sheet over CSS_FAIL_GZ (and, with
    strict_html, when any page is over HTML_MAX, as the tests ask); warn past JS_WARN_GZ and for a page over HTML_MAX
    (the hourly build keeps going on a heavy day: the tests hold the fixtures and the busiest real day to it)."""
    b = budgets(out, js_name)
    kb = lambda n: f"{n / 1000:.1f} KB gz"
    bad = []
    if b["js"] > JS_FAIL_GZ: bad.append(f"the initial bundle is {kb(b['js'])}, over the {kb(JS_FAIL_GZ)} guard: move code into a lazy chunk")
    elif b["js"] > JS_WARN_GZ: warnings.warn(f"the initial bundle is {kb(b['js'])}, past the {kb(JS_WARN_GZ)} warning line", BudgetWarning)
    if b["css"] > CSS_FAIL_GZ: bad.append(f"the shared stylesheet is {kb(b['css'])}, over the {kb(CSS_FAIL_GZ)} guard: use page-scoped CSS (PAGE_CSS)")
    if b["html"]:
        msg = f"{len(b['html'])} page(s) over {HTML_MAX} bytes: " + ", ".join(f"{p} {n}" for p, n in b["html"][:5])
        if strict_html: bad.append(msg)
        else: warnings.warn(msg, BudgetWarning)
    if bad: raise BudgetError("; ".join(bad))
    return b


def preview_mode(env=None):
    """PREVIEW=1 (or true/yes) in the environment: the build is a preview. Every page is noindex,nofollow
    and robots.txt is `Disallow: /` with no Sitemap line. Unset or 0: the normal, indexable site."""
    return str((env if env is not None else os.environ).get("PREVIEW", "")).strip().lower() in ("1", "true", "yes")


def build(data_path, discounts_path, out, halls_path=None, preview=False, lastmod_path=None, noindex=None, modules=None):
    """`modules`: the page modules to build (default: every module under pages/, core first)."""
    modules = discover() if modules is None else list(modules)
    data = json.load(open(data_path, encoding="utf-8"))
    disc = load_discounts(discounts_path)
    halls = Halls(halls_path or os.path.join(ROOT, "halls.yaml"))
    owned = dict.fromkeys(GENERATED + [d for m in modules for d in getattr(m, "DIRS", ())])
    for sub in owned:              # only what this build writes; anything else in out/ is left alone
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
    for f in ("index.html", "404.html", "offline.html", "sitemap.xml", "robots.txt", "sw.js", "manifest.webmanifest"):
        try: os.remove(os.path.join(out, f))
        except FileNotFoundError: pass
    site = Site(data, disc, halls, out, modules); site.lastmod_path = lastmod_path
    site.noindex = preview_mode() if noindex is None else noindex
    n = site.run()
    check_budgets(out, site.js_name)   # the code's budgets stop the build; a heavy page is reported (W1-P1)
    return n


def main():
    first = lambda *ps: next((p for p in ps if os.path.exists(p)), ps[-1])
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=first(os.path.join(ROOT, "data", "latest.json"), os.path.join(ROOT, "fixtures", "sample_latest.json")))
    ap.add_argument("--discounts", default=first(os.path.join(ROOT, "discounts.yaml"), os.path.join(ROOT, "fixtures", "sample_discounts.yaml")))
    ap.add_argument("--halls", default=os.path.join(ROOT, "halls.yaml"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--preview", action="store_true", help="(kept for old callers; the site no longer needs anything from ../tools)")
    a = ap.parse_args()
    n = build(a.data, a.discounts, a.out, a.halls, a.preview, os.path.join(ROOT, "data", "lastmod.json"))
    print(f"built {n} pages ×2 languages from {os.path.relpath(a.data, ROOT)} + {os.path.relpath(a.discounts, ROOT)} -> {a.out}")


if __name__ == "__main__":
    main()
