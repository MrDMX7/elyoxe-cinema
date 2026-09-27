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
