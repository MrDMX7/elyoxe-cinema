"""Site build from the synthetic fixtures: every page in both languages, no Arabic-Indic digits,
price cells carry what cinema.js needs, the sitemap pairs languages, discounts read honestly."""
import json, os, re, sys
from html.parser import HTMLParser

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
CITIES = ["abu-dhabi", "dubai", "sharjah", "al-ain", "ajman", "ras-al-khaimah", "fujairah", "umm-al-quwain"]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    build.build(DATA, DISC, str(out))
    data = json.load(open(DATA, encoding="utf-8"))
    return str(out), data


def read(out, *parts):
    return open(os.path.join(out, *parts, "index.html"), encoding="utf-8").read()


def all_files(out):
    for dp, _, fs in os.walk(out):
        for f in fs:
            yield os.path.join(dp, f)


def test_every_page_in_both_languages(site):
    out, data = site
    cards = [c["id"] for c in build.load_discounts(DISC)["cards"]]
    pages = [("cinema",), ("cinema", "halls"), ("cinema", "cards")]
    pages += [("cinema", c) for c in CITIES]
    pages += [("cinema", c["city"], cid) for cid, c in data["cinemas"].items()]
    pages += [("cinema", "film", fid) for fid in data["films"]]
    pages += [("cinema", "cards", c) for c in cards]
    for p in pages:
        assert os.path.exists(os.path.join(out, *p, "index.html")), p
        assert os.path.exists(os.path.join(out, "en", *p, "index.html")), ("en",) + p


def test_no_arabic_indic_digits_anywhere(site):
    out, _ = site
    bad = re.compile("[٠-٩۰-۹]")
    for f in all_files(out):
        if f.endswith((".html", ".json", ".js", ".css", ".xml")):
            assert not bad.search(open(f, encoding="utf-8").read()), f


class Cells(HTMLParser):
    def __init__(self):
        super().__init__(); self.cells, self.ld = [], []; self._ld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "p" in (a.get("class") or "").split(): self.cells.append(a)
        if tag == "script" and a.get("type") == "application/ld+json": self._ld = True

    def handle_data(self, d):
        if self._ld: self.ld.append(d); self._ld = False


def test_price_cells_carry_data_and_jsonld_parses(site):
    out, _ = site
    total = 0
    for f in all_files(out):
        if not f.endswith(".html"): continue
        p = Cells(); p.feed(open(f, encoding="utf-8").read())
        for c in p.cells:
            for k in ("data-aed", "data-chain", "data-hall"):
                assert c.get(k), (f, c)
            float(c["data-aed"])
        for block in p.ld: json.loads(block)
        total += len(p.cells)
    assert total > 100


def test_sitemap_pairs_languages(site):
    out, _ = site
    sm = open(os.path.join(out, "cinema", "sitemap.xml"), encoding="utf-8").read()
    urls = re.findall(r"<url>(.*?)</url>", sm, re.S)
    assert len(urls) > 40
    for u in urls:
        assert 'hreflang="ar"' in u and 'hreflang="en"' in u
    assert "https://elyoxe.com/cinema/al-ain/" in sm and "https://elyoxe.com/en/cinema/al-ain/" in sm


def test_head_has_canonical_and_hreflang(site):
    out, _ = site
    h = read(out, "cinema", "al-ain")
    assert '<link rel="canonical" href="https://elyoxe.com/cinema/al-ain/">' in h
    assert 'hreflang="en" href="https://elyoxe.com/en/cinema/al-ain/"' in h
    assert "سينما العين" in h.split("</title>")[0]


def test_none_found_says_we_found_none(site):
    out, _ = site
    h = read(out, "cinema", "cards", "fazaa")
    assert "ما لقينا خصم" in h
    assert "ما يقبلون" not in h


def test_discount_math_and_example(site):
    rules = build.load_discounts(DISC)["rules"]
    assert build.after(42, "star", "Standard", "fazaa", rules, "2026-09-25")[0] == 33.6
    assert build.after(52.5, "star", "Standard", "fazaa", rules, "2026-09-25")[0] == 42.0
    assert build.after(46, "vox", "Standard", "adcb", rules, "2026-09-25")[0] == 23.0
    assert build.after(195, "vox", "THEATRE", "adcb", rules, "2026-09-25")[0] is None      # excluded hall
    assert build.after(50, "reel", "Standard", "fazaa", rules, "2026-09-25")[0] is None     # included_halls only SUITES
    assert build.after(200, "reel", "SUITES", "fazaa", rules, "2026-09-25")[0] == 150.0
    assert build.after(35, "cinemacity", "Standard", "fazaa", rules, "2026-09-25")[0] is None  # expired
    out, _ = site
    assert "33.60" in read(out, "cinema", "cards", "fazaa")


def test_box_office_price_and_stale_chain(site):
    out, _ = site
    assert "السعر في الشباك" in read(out, "cinema", "ras-al-khaimah", "novo-manar-mall")
    h = read(out, "cinema", "al-ain", "star-bawadi-mall")
    assert "آخر تحديث قبل 3 ساعات" in h
    assert "updated 3 hours ago" in read(out, "en", "cinema", "al-ain", "star-bawadi-mall").lower()


def test_unconfirmed_rule_is_marked(site):
    out, _ = site
    assert "غير مؤكد" in read(out, "cinema", "cards", "esaad")


def test_city_slices_for_the_client(site):
    out, data = site
    for city in {c["city"] for c in data["cinemas"].values()}:
        j = json.load(open(os.path.join(out, "cinema", "data", city + ".json"), encoding="utf-8"))
        assert j["shows"] and all(s["c"] in j["cinemas"] for s in j["shows"])
    d = json.load(open(os.path.join(out, "cinema", "data", "discounts.json"), encoding="utf-8"))
    assert d["rules"]["star"]["fazaa"]["value"] == 20
    js = os.path.getsize(os.path.join(out, "cinema", "assets", "cinema.js"))
    assert js < 25 * 1024


def test_poster_used_when_present(tmp_path):
    data = json.load(open(DATA, encoding="utf-8"))
    data["films"]["crawlers"]["poster"] = "https://image.example/crawlers.jpg"
    p = tmp_path / "d.json"; p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    build.build(str(p), DISC, str(tmp_path / "o"))
    assert 'src="https://image.example/crawlers.jpg"' in read(str(tmp_path / "o"), "cinema")
