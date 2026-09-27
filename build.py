"""Build «سينما» — https://cinema.elyoxe.com — static pages from data/latest.json + discounts.yaml + halls.yaml.

  src/page.html     the page template (head with SEO, header with the wordmark and nav, footer)
  src/cinema.css    the «هـ» design system (night, velvet, marquee gold; Markazi Text + Readex Pro)
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
import argparse, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from site_kit import *  # noqa: E402,F401,F403  (build.after, build.T, build.Halls ... stay importable from here)
from site_kit import Emit, Kit, Plugin  # noqa: E402
from pages import discover  # noqa: E402

# the core bundle's order (pages/core.py JS); kept here for old callers
JS_MODULES = ("core", "pure", "disc", "flip", "prices", "near", "prayer", "home", "filters", "ticket", "trailer", "pwa", "sheet", "main")


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
        css = "\n".join(open(p, encoding="utf-8").read() for p in [os.path.join(SRC, "cinema.css")] + css_files(self.modules))
        self.write(os.path.join(adir, "cinema.css"), minify_css(css))
        if os.path.exists(os.path.join(SRC, "icon.svg")):
            self.write(os.path.join(adir, "icon.svg"), open(os.path.join(SRC, "icon.svg"), encoding="utf-8").read())
        self.write(os.path.join(adir, self.js_name), self.js)
        for fname, js in self.chunks.values():
            self.write(os.path.join(adir, fname), js)
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
    return site.run()


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
