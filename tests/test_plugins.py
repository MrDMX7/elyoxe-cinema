"""Page plug-ins (docs/PLUGINS.md): discovery order, and the example module tests/fixtures/plugins/hello.py
exercising every hook — a page per language, a data file, a nav item, a slot on home, a CSS partial, a lazy
chunk — plus a main-bundle feature and a built-in nav link re-pointed."""
import gzip, json, os, re, shutil, subprocess, sys, types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import pages  # noqa: E402
from site_kit import NavItem, Plugin  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
HELLO = os.path.join(ROOT, "tests", "fixtures", "plugins", "hello.py")
NODE = shutil.which("node")


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def ct(html):
    return json.loads(re.search(r"<script>window\.CT = (.*?);</script>", html).group(1))


@pytest.fixture(scope="module")
def hello(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("hello"))
    build.build(DATA, DISC, out, noindex=False, modules=build.discover(extra=[HELLO]))
    return out


def test_core_first_then_alphabetical():
    names = pages.names()
    assert names[0] == "core" and names[1:] == sorted(names[1:])
    assert [m.__name__ for m in build.discover(only=("core",))] == ["pages.core"]
    assert build.discover(extra=[HELLO])[-1].__name__ == "pages_extra_hello"


def test_example_pages_data_sitemap(hello):
    for parts in (("hello",), ("en", "hello")):
        h = read(hello, *parts, "index.html")
        assert '<h1 class="pt">' in h and 'data-page="hello"' in h and '<link rel="canonical"' in h
    n = len([f for f, v in json.load(open(DATA, encoding="utf-8"))["films"].items() if v.get("status") != "archived"])
    assert f'<p class="lead hello">{build.ar_count(n, ("فيلم واحد", "فيلمين", "أفلام", "فيلم"))}</p>' in read(hello, "hello", "index.html")
    assert f'<p class="lead hello">{n} films</p>' in read(hello, "en", "hello", "index.html")
    assert json.loads(read(hello, "data", "hello.json")) == {"films": n}
    sm = read(hello, "sitemap.xml")
    assert "<loc>https://cinema.elyoxe.com/hello/</loc>" in sm and 'hreflang="en" href="https://cinema.elyoxe.com/en/hello/"' in sm
    assert os.path.exists(os.path.join(hello, "film"))         # core still built, first


def test_example_nav_and_slot_reach_core_pages(hello):
    home = read(hello, "index.html")
    nav = re.search(r'<nav class="nav".*?</nav>', home, re.S).group(0)
    foot = re.search(r'<nav class="foot-l".*?</nav>', home, re.S).group(0)   # a feature's own key: a footer link
    assert '<a href="/hello/">أهلاً</a>' in foot and "/hello/" not in nav
    assert '<a href="/en/hello/">Hello</a>' in read(hello, "en", "index.html")
    assert '<a href="/hello/" aria-current="page">أهلاً</a>' in read(hello, "hello", "index.html")
    assert '<p class="wrap hello"><span class="num">' in home
    # home (UI redesign Task 3): the slot comes after the rows, before «كل الأفلام»
    assert home.index('<p class="wrap hello">') < home.index('id="all"')


def test_example_css_partial_and_lazy_chunk(hello):
    css = read(hello, "assets", "cinema.css")
    assert css.endswith(".hello{color: var(--gold);}\n") and css.count("\n") == 1
    page = ct(read(hello, "hello", "index.html"))
    url = page["chunks"]["hello"]
    assert re.fullmatch(r"/assets/hello\.[0-9a-f]{10}\.js", url)
    chunk = read(hello, *url.strip("/").split("/"))
    assert chunk.startswith("(function (K) {") and "window.CINEMA" in chunk and "example lazy chunk" not in chunk
    assert "hello" not in ct(read(hello, "index.html")).get("chunks", {})   # only the pages that ask for it
    if NODE:
        r = subprocess.run([NODE, "--check", os.path.join(hello, *url.strip("/").split("/"))], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    js = re.search(r'\("/assets/(cinema\.[0-9a-f]{10}\.js)",document\)', read(hello, "index.html")).group(1)
    assert len(gzip.compress(open(os.path.join(hello, "assets", js), "rb").read())) < 45 * 1024


def test_main_bundle_feature_goes_before_start_up(tmp_path):
    (tmp_path / "feat.js").write_text('feature(function () { document.body.setAttribute("data-feat", "1"); });\n', encoding="utf-8")
    feat = types.SimpleNamespace(__name__="feat", JS=("feat",), ASSET_DIR=str(tmp_path))
    js = build.bundle_js(modules=build.discover(only=("core",)) + [feat])
    assert js.index('data-feat') < js.index("(function init()") and js.index("function startFeatures") < js.index('data-feat')
    assert build.bundle_js() == build.bundle_js(modules=build.discover())


def test_builtin_nav_repointed_and_unknown_slot_refused(tmp_path):
    coming = types.SimpleNamespace(__name__="coming", register=lambda site: Plugin(nav=[NavItem("thursday", href=lambda lang: build.P(lang, "coming"))]))
    out = str(tmp_path / "o")
    build.build(DATA, DISC, out, noindex=False, modules=build.discover(only=("core",)) + [coming])
    nav = re.search(r'<nav class="nav".*?</nav>', read(out, "index.html"), re.S).group(0)
    assert '<a href="/coming/">قريباً في السينما</a>' in nav
    bad = types.SimpleNamespace(__name__="bad", register=lambda site: Plugin(slots={"nowhere": lambda s, lang: "x"}))
    with pytest.raises(ValueError, match="unknown slot"):
        build.build(DATA, DISC, str(tmp_path / "b"), noindex=False, modules=build.discover(only=("core",)) + [bad])


# ---------------------------------------------------------------- W1-P1: the seams (docs/PLUGINS.md)
def test_the_core_mixin_package_is_never_discovered():
    """pages/_core/ holds CorePages' families (W1-P1): a package, not page modules. Discovery still loads exactly the
    top-level pages/*.py (core first), and nothing from pages/_core registers pages of its own."""
    top = sorted(f[:-3] for f in os.listdir(os.path.join(ROOT, "pages")) if f.endswith(".py") and not f.startswith("_"))
    assert sorted(pages.names()) == top and "_core" not in pages.names()
    mods = build.discover()
    assert [m.__name__ for m in mods] == ["pages." + n for n in pages.names()]
    assert not any(m.__name__.startswith("pages._core") for m in mods)
    from pages.core import CorePages
    from pages._core import bill, edge, film, home, money, places
    for mix in (home.HomePages, bill.BillPages, film.FilmPages, places.PlacesPages, money.MoneyPages, edge.EdgePages):
        assert issubclass(CorePages, mix) and not hasattr(mix, "register")


def test_page_scoped_css_reaches_only_its_kind(tmp_path):
    """PAGE_CSS = {kind: (names…)}: a second small stylesheet, linked only from pages of that kind; never in the shared
    sheet. An all-comment partial (a stub) links nothing."""
    (tmp_path / "scoped.css").write_text(".scoped-only{color:var(--gold)}\n", encoding="utf-8")
    (tmp_path / "stub.css").write_text("/* nothing yet */\n", encoding="utf-8")
    mod = types.SimpleNamespace(__name__="scoped", ASSET_DIR=str(tmp_path), PAGE_CSS={"film": ("scoped",), "home": ("stub",)})
    out = str(tmp_path / "o")
    build.build(DATA, DISC, out, noindex=False, modules=build.discover(only=("core",)) + [mod])
    film = read(out, "film", "heart-of-the-beast", "index.html")
    link = re.search(r'<link rel="stylesheet" href="/assets/cinema\.css\?v=[0-9a-f]{10}"><link rel="stylesheet" href="(/assets/page-film\.[0-9a-f]{10}\.css)">', film)
    assert link and read(out, *link.group(1).strip("/").split("/")) == ".scoped-only{color:var(--gold)}\n"
    assert "page-film." not in read(out, "index.html") and "page-home." not in read(out, "index.html")
    assert ".scoped-only" not in read(out, "assets", "cinema.css")
    assert not [f for f in os.listdir(os.path.join(out, "assets")) if f.startswith("page-home.")]
    # core's own: the 404's leader sheet (W2-P10's ui-edge.css) is page-scoped, and empty until W2-P10: no link yet
    assert "page-404." not in read(out, "404.html") and not [f for f in os.listdir(os.path.join(out, "assets")) if f.startswith("page-404.")]


def test_wave2_slots_are_declared_and_each_lands_in_its_place(tmp_path):
    """The ten places Wave 2 fills (W1-P1): declared in Kit.SLOTS, each drawn where docs/PLUGINS.md says, with its ctx."""
    wave2 = ("head.inline", "home.after_bill", "home.after_board", "film.first", "cinema.top", "city.hero", "notfound.body",
             "offline.body", "ticket.actions", "sources.body")
    assert set(wave2) <= set(build.Kit.SLOTS)
    for later in ("home.personal", "home.because", "film.hero_actions"):     # Wave 3–4 declare their own
        assert later not in build.Kit.SLOTS
    seen = {}

    def mark(name):
        def fn(site, lang, **ctx):
            seen.setdefault(name, []).append(ctx)
            return f'<i data-slot="{name}"></i>' if name != "head.inline" else '<script data-slot="head.inline">0</script>'
        return fn
    mod = types.SimpleNamespace(__name__="marks", register=lambda site: Plugin(slots={n: mark(n) for n in wave2}))
    out = str(tmp_path / "o")
    build.build(DATA, DISC, out, noindex=False, modules=build.discover(only=("core",)) + [mod])
    home = read(out, "index.html")
    assert home.index('<script>document.documentElement.classList.add("js")</script><script data-slot="head.inline">') < home.index("</head>")
    # W2-P4: the near row (id="now") is deleted; the board in home.after_bill carries the id, and with a module filling
    # the slot, home draws no anchor of its own (one target)
    assert home.index("</section>", home.index('<section class="bill"')) < home.index('data-slot="home.after_bill"') \
        < home.index('data-slot="home.after_board"') < home.index('class="rail"') < home.index('id="all"')
    assert 'id="now"' not in home
    film = read(out, "film", "heart-of-the-beast", "index.html")
    assert film.index('<section class="fhero') < film.index('data-slot="film.first"') < film.index('<section class="fsched"')
    tk = film[film.index('<div class="tk-act">'):film.index("</aside>", film.index('<div class="tk-act">'))]
    assert tk.index('data-tk-share') < tk.index('data-slot="ticket.actions"')
    city = read(out, "dubai", "index.html")
    assert city.index('<h1 class="pt">') < city.index('data-slot="city.hero"') < city.index('data-me')
    cin = read(out, "dubai", "reel-dubai-mall", "index.html")
    assert cin.index('<p class="meta">') < cin.index('data-slot="cinema.top"') < cin.index('data-me')
    assert read(out, "404.html").index('class="head wrap nf"') < read(out, "404.html").index('data-slot="notfound.body"')
    off = read(out, "offline.html")
    assert off.index("<h1>") < off.index('data-slot="offline.body"') < off.index('<p lang="en">')
    src = read(out, "sources", "index.html")
    assert src.index('<ul class="chains">') < src.index('data-slot="sources.body"')
    # the context each place passes
    assert {"kind"} == set(seen["head.inline"][0]) and {x["kind"] for x in seen["head.inline"]} >= {"home", "film", "city", "404"}
    assert all(set(c) == {"fid"} for c in seen["film.first"]) and all(set(c) == {"city"} for c in seen["city.hero"])
    assert all(set(c) == {"cid", "city"} for c in seen["cinema.top"]) and all(set(c) == {"show"} and c["show"]["film"] for c in seen["ticket.actions"])
