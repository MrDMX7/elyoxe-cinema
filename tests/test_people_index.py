"""/people/ + /en/people/ (phase 3, batch A, task A5): showing-now first, then alphabetical, photos where
pages/people.py mirrored one, and the symmetric "no people data, no page" rule pages/people.py already
follows for the per-person pages."""
import json, os, re, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
MODULES = build.discover(only=("core", "people", "people_index"))


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def site_data(tmp_path):
    d = json.load(open(DATA, encoding="utf-8"))
    fs = d["films"]
    for f in fs.values():
        f["cast"], f["directors"] = [], []
    fs["heart-of-the-beast"]["cast"] = ["Q1"]           # showing now
    fs["heart-of-the-beast"]["directors"] = ["Q9"]      # showing now
    fs["weapons"]["cast"] = ["Q2"]                      # archived only -> not "showing now"
    d["people"] = {
        "Q1": {"qid": "Q1", "slug": "zaid", "name_en": "Zaid Actor", "name_ar": "زايد الممثل", "gender": "m",
               "photo": {"src": "/posters/people/q1-abc-160.webp", "src2x": "/posters/people/q1-abc-320.webp",
                         "licence": "CC BY", "licence_url": "https://x", "author": "A", "page": "https://x"},
               "bio": {"ar": None, "en": None}, "notable": []},
        "Q9": {"qid": "Q9", "slug": "ahmad", "name_en": "Ahmad Director", "name_ar": "أحمد المخرج", "gender": "m",
               "photo": None, "bio": {"ar": None, "en": None}, "notable": []},
        "Q2": {"qid": "Q2", "slug": "basil", "name_en": "Basil Archived", "name_ar": None, "gender": "m",
               "photo": None, "bio": {"ar": None, "en": None}, "notable": []},
        "Q3": {"qid": "Q3", "slug": "no-name", "name_en": None, "name_ar": None, "gender": None,
               "photo": None, "bio": {"ar": None, "en": None}, "notable": []},          # no name: no page, no row
    }
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return str(p)


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pidx")
    o = str(tmp / "out")
    build.build(site_data(tmp), DISC, o, modules=MODULES)
    return o


def test_showing_now_group_before_the_alphabetical_rest(out):
    h = read(out, "people", "index.html")
    now_h2 = h.index("يعرض لهم الحين")
    all_h2 = h.index("الكل")
    zaid, ahmad, basil = h.index("/people/zaid/"), h.index("/people/ahmad/"), h.index("/people/basil/")
    assert now_h2 < ahmad < zaid < all_h2 < basil     # showing-now group (alpha within it) before the rest
    assert "/people/no-name/" not in h                 # no name: never listed


def test_photo_shown_where_available(out):
    h = read(out, "people", "index.html")
    assert 'src="/posters/people/q1-abc-160.webp"' in h
    start = h.index('href="/people/ahmad/"')
    ahmad_row = h[start:start + h[start:].index("</li>")]
    assert "<img" not in ahmad_row and 'class="pi-i"' in ahmad_row


def test_english_page_and_names(out):
    h = read(out, "en", "people", "index.html")
    assert "Showing now" in h and ">Zaid Actor<" in h and ">Ahmad Director<" in h and "Everyone" in h


def test_arabic_name_preferred_english_fallback_marked(out):
    h = read(out, "people", "index.html")
    assert ">زايد الممثل<" in h
    start = h.index('href="/people/basil/"')
    basil_row = h[start:start + h[start:].index("</li>")]
    assert 'lang="en" dir="ltr">Basil Archived<' in basil_row


def test_breadcrumb_and_nav(out):
    h = read(out, "people", "index.html")
    assert '<h1 class="pt">الناس</h1>' in h
    nav = re.search(r'<nav class="nav".*?</nav>', h, re.S).group(0)
    assert 'href="/films/"' not in nav                # nav="films" re-uses the existing link, adds nothing new


def test_sitemap_includes_both_languages(out):
    sm = read(out, "sitemap.xml")
    assert "<loc>https://cinema.elyoxe.com/people/</loc>" in sm
    assert 'hreflang="en" href="https://cinema.elyoxe.com/en/people/"' in sm


def test_css_partial_bundled(out):
    assert ".pi-l" in read(out, "assets", "cinema.css")


def test_no_people_data_no_index_page(tmp_path):
    """Symmetric with pages/people.py's own per-person rule: no data["people"], no page at all."""
    o = str(tmp_path / "out")
    build.build(DATA, DISC, o, modules=MODULES)   # fixtures/sample_latest.json has no data["people"]
    assert not os.path.exists(os.path.join(o, "people"))


def test_page_budget_holds_with_300_people(tmp_path):
    """Fix round 1 (task-A5-review.md): a real refresh can carry well over 100 distinct cast/director qids
    across a season of films -- steps/people.py caps a single film's own credits, never the site-wide
    total. A flat photo grid for 300 rows would blow the ~125 KB page target long before that; site.fit()
    (site_kit.py) must fall back to the photo-less "compact" mode, and every person must still be listed --
    this is a budget fix, not a pagination cut that drops people from the page."""
    d = json.load(open(DATA, encoding="utf-8"))
    fs = d["films"]
    for f in fs.values():
        f["cast"], f["directors"] = [], []
    people = {}
    now_ids, rest_ids = [], []
    for i in range(150):
        q = f"Q{1000 + i}"
        fs["heart-of-the-beast"]["cast"].append(q)          # showing now
        now_ids.append(q)
        people[q] = {"qid": q, "slug": f"now-person-{i}", "name_en": f"Now Person {i}", "name_ar": None,
                     "gender": None,
                     "photo": ({"src": f"/posters/people/{q.lower()}-160.webp",
                                "src2x": f"/posters/people/{q.lower()}-320.webp", "licence": "CC BY",
                                "licence_url": "https://x", "author": "A", "page": "https://x"} if i % 2 else None),
                     "bio": {"ar": None, "en": None}, "notable": []}
    for i in range(150):
        q = f"Q{2000 + i}"
        fs["weapons"]["cast"].append(q)                     # archived only -> the "Everyone" group
        rest_ids.append(q)
        people[q] = {"qid": q, "slug": f"rest-person-{i}", "name_en": f"Rest Person {i}", "name_ar": None,
                     "gender": None, "photo": None, "bio": {"ar": None, "en": None}, "notable": []}
    d["people"] = people
    p = tmp_path / "big.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = str(tmp_path / "out")
    build.build(str(p), DISC, o, modules=MODULES)
    for parts in (("people", "index.html"), ("en", "people", "index.html")):
        size = os.path.getsize(os.path.join(o, *parts))
        assert size <= 125_000, f"{parts}: {size} bytes"
    h = read(o, "people", "index.html")
    for q in now_ids + rest_ids:                             # the fix is a byte budget, not a row cut
        assert f'/people/{people[q]["slug"]}/' in h
    assert h.count("<img") < len(now_ids)                    # the fit() fallback dropped photo markup, not rows


def test_no_qualifying_people_no_index_page(tmp_path):
    """data["people"] present but nobody has both a name and a film we list -> same as none."""
    d = json.load(open(DATA, encoding="utf-8"))
    d["people"] = {"Q1": {"qid": "Q1", "slug": "ghost", "name_en": "Ghost", "name_ar": None, "gender": None,
                          "photo": None, "bio": {"ar": None, "en": None}, "notable": []}}   # in no film
    p = tmp_path / "l.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    o = str(tmp_path / "out")
    build.build(str(p), DISC, o, modules=MODULES)
    assert not os.path.exists(os.path.join(o, "people"))
