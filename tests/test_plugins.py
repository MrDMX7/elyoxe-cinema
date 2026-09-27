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
    nav = re.search(r'<nav class="foot-l".*?</nav>', home, re.S).group(0)   # a feature's own key: a footer link
    assert '<a href="/hello/">أهلاً</a>' in nav
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
    js = re.search(r'<link rel="preload" href="/assets/(cinema\.[0-9a-f]{10}\.js)" as="script">', read(hello, "index.html")).group(1)
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
    assert '<a href="/coming/">نازل قريب</a>' in nav
    bad = types.SimpleNamespace(__name__="bad", register=lambda site: Plugin(slots={"nowhere": lambda s, lang: "x"}))
    with pytest.raises(ValueError, match="unknown slot"):
        build.build(DATA, DISC, str(tmp_path / "b"), noindex=False, modules=build.discover(only=("core",)) + [bad])
