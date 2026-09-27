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
    cards = [c["id"] for c in build.confirmed_cards(build.load_discounts(DISC), "2026-09-25")]
    pages = [(), ("halls",), ("cards",)]
    pages += [(c,) for c in CITIES]
    pages += [(c["city"], cid) for cid, c in data["cinemas"].items()]
    pages += [("film", fid) for fid in data["films"]]
    pages += [("cards", c) for c in cards]
    for p in pages:
        assert os.path.exists(os.path.join(out, *p, "index.html")), p
        assert os.path.exists(os.path.join(out, "en", *p, "index.html")), ("en",) + p
    assert not os.path.exists(os.path.join(out, "cinema")), "pages live at the site root now"
    for f in ("404.html", "robots.txt", "sitemap.xml", os.path.join("assets", "cinema.css"), os.path.join("assets", "fonts", "readex-arabic.woff2")):
        assert os.path.exists(os.path.join(out, f)), f


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
    sm = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    urls = re.findall(r"<url>(.*?)</url>", sm, re.S)
    assert len(urls) > 40
    for u in urls:
        assert 'hreflang="ar"' in u and 'hreflang="en"' in u
    assert "https://cinema.elyoxe.com/al-ain/" in sm and "https://cinema.elyoxe.com/en/al-ain/" in sm


def test_head_has_canonical_and_hreflang(site):
    out, _ = site
    h = read(out, "al-ain")
    assert '<link rel="canonical" href="https://cinema.elyoxe.com/al-ain/">' in h
    assert 'hreflang="en" href="https://cinema.elyoxe.com/en/al-ain/"' in h
    assert "سينما العين" in h.split("</title>")[0]


def test_none_found_says_we_found_none(site):
    out, _ = site
    h = read(out, "cards", "fazaa")
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
    assert "33.60" in read(out, "cards", "fazaa")


def test_box_office_price_and_stale_chain(site):
    out, _ = site
    assert "السعر في الشباك" in read(out, "ras-al-khaimah", "novo-manar-mall")
    h = read(out, "al-ain", "star-bawadi-mall")
    assert "آخر تحديث قبل 3 ساعات" in h
    assert "updated 3 hours ago" in read(out, "en", "al-ain", "star-bawadi-mall").lower()


def test_only_confirmed_cards_and_official_rules_are_published(site):
    """Spec: third-party and unconfirmed rules stay hidden; a card with no current official discount
    (homat: only «none found») appears nowhere — no chip, no row in discounts.json, not in the sitemap;
    its old URL is only a noindex «no confirmed discount» note (test_hourly_safe.py), not a card page."""
    out, _ = site
    esaad = re.sub(r"<script.*?</script>", "", read(out, "cards", "esaad"), flags=re.S)   # official at Novo, third-party at Star
    assert "غير مؤكد" not in esaad and "نوفو" in esaad
    assert "ستار" not in esaad.split('<section class="wrap cardsx">')[0].split("</h1>")[1]
    stub = read(out, "cards", "homat")
    assert '<meta name="robots" content="noindex">' in stub and "cardrows" not in stub
    home = read(out)
    assert 'data-card="fazaa"' in home and 'data-card="homat"' not in home and 'value="homat"' not in home
    d = json.load(open(os.path.join(out, "data", "discounts.json"), encoding="utf-8"))
    assert {c["id"] for c in d["cards"]} == {"fazaa", "esaad", "adcb"}
    assert all(r.get("confidence") == "official" for cs in d["rules"].values() for r in cs.values())
    assert "esaad" not in d["rules"]["star"]


def test_city_day_slices_for_the_client(site):
    out, data = site
    for city in {c["city"] for c in data["cinemas"].values()}:
        for day in ("2026-09-25", "2026-09-26"):
            j = json.load(open(os.path.join(out, "data", f"{city}-{day}.json"), encoding="utf-8"))
            assert j["S"]
            for ci, fi, t, hi, pi, bi, tail in j["S"]:
                assert j["C"][ci][0] in data["cinemas"] and j["F"][fi][0] in data["films"] and re.match(r"^\d\d:\d\d$", t)
                assert j["H"][hi][0] and "|" in j["H"][hi][1]
                assert pi == -1 or j["P"][pi][0][1] > 0
                assert bi == -1 or (j["B"][bi] + tail).startswith("https://")
    d = json.load(open(os.path.join(out, "data", "discounts.json"), encoding="utf-8"))
    assert d["rules"]["star"]["fazaa"]["value"] == 20
    # the client is one bundle, named by its hash; the budget is 45 KB gzipped (spec: Budgets)
    import gzip
    home = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    name = re.search(r'<link rel="preload" href="/assets/(cinema\.[0-9a-f]{10}\.js)" as="script">', home).group(1)
    js = open(os.path.join(out, "assets", name), "rb").read()
    assert len(gzip.compress(js)) < 45 * 1024
    assert json.load(open(os.path.join(out, "data", "cinemas.json"), encoding="utf-8"))


def test_percentages_are_isolated_in_arabic(site):
    """«خصم 20%» in one bidi run prints «خصم %20»: every percentage in visible text sits in its own .num span."""
    out, _ = site
    for f in all_files(out):
        if not f.endswith(".html"): continue
        h = open(f, encoding="utf-8").read()
        body = re.sub(r"<script.*?</script>", "", h.split("<body", 1)[1], flags=re.S)
        body = re.sub(r'href="[^"]*"', 'href=""', body)   # a URL's %-escapes are not visible text
        for m in re.finditer(r"\d+(?:\.\d+)?\s?%", body):
            # dir="ltr" too: span.num is unicode-bidi:plaintext, which alone still prints «%88» in an RTL page
            assert re.search(r'class="num" dir="ltr">\s*$', body[:m.start()][-40:]), (f, body[m.start() - 60:m.end() + 10])
    assert '<span class="num" dir="ltr">20%</span>' in read(out, "cards", "fazaa")
    assert '<b class="num" dir="ltr">20%</b>' in read(out, "cards")


def test_hall_labels_are_cleaned():
    h = build.Halls(os.path.join(ROOT, "halls.yaml"))
    assert build.clean_label("Private CinemaiThis session can be customized after you book (content, F&B)") == "Private Cinema"
    assert h.name("vox", "OTHER", "Private CinemaiThis session can be customized after you book (content, F&B)", "en") == "Private Cinema"
    assert h.key("vox", "OTHER", "Premium") == h.key("vox", "OTHER", "Premier") == "PREMIER"
    assert h.key("star", "OTHER", "2D") == "Standard" and h.name("star", "OTHER", "2D", "ar") == "عادية"
    assert h.key("roxy", "OTHER", "2L") == "Standard"
    assert h.key("reel", "Standard", "Screen 11") == "Standard"
    assert h.key("reel", "VIP", "Dolby Screen 7") == "DOLBY"
    key, name, e, clean = h.resolve("vox", "OTHER", "Some Brand New Thing 12")
    assert name == "Some Brand New Thing" and not clean


def merged_real():
    import normalize
    res = {c: json.load(open(os.path.join(ROOT, "fixtures", c + ".json"), encoding="utf-8"))
           for c in ("vox", "star", "novo", "reel", "roxy", "cineroyal", "cinemacity")
           if os.path.exists(os.path.join(ROOT, "fixtures", c + ".json"))}
    return normalize.merge(res, None, "2026-09-25T00:00:00")


def sizes_ok(out, page_max=150_000, slice_max=150_000):
    big = []
    for f in all_files(out):
        n = os.path.getsize(f)
        if f.endswith(".html") and n > page_max: big.append((f, n))
        if os.sep + "data" + os.sep in f and f.endswith(".json") and n > slice_max: big.append((f, n))
    return big


def test_real_fixtures_build_within_budget(tmp_path):
    data = merged_real()
    p = tmp_path / "real.json"; p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = str(tmp_path / "o")
    build.build(str(p), os.path.join(ROOT, "discounts.yaml"), out)
    assert sizes_ok(out) == []
    junk = re.compile(r"This session|customized after")
    for f in all_files(out):
        if f.endswith((".html", ".json")): assert not junk.search(open(f, encoding="utf-8").read()), f


def test_scaled_volume_stays_within_budget(tmp_path):
    """The fixtures cap each chain at ~400 shows; real volume is ~3,500 per 2 days. Triple every show."""
    data = merged_real()
    extra = []
    for s in data["shows"]:
        for shift in (7, 14):
            h, m = map(int, s["time"].split(":")); m += shift
            extra.append(dict(s, time=f"{(h + m // 60) % 24:02d}:{m % 60:02d}", book=(s.get("book") or "") + f"?x={shift}"))
    data["shows"] += extra
    assert len(data["shows"]) > 6000
    p = tmp_path / "big.json"; p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = str(tmp_path / "o")
    build.build(str(p), os.path.join(ROOT, "discounts.yaml"), out)
    assert sizes_ok(out) == []


def test_real_latest_at_its_busiest_stays_within_budget(tmp_path):
    """The live data at its fullest: data/latest.json rebuilt as if at 08:00 on its busiest day, so nothing
    has started yet (a morning build carries ~1,500 Dubai shows). Every page stays within 150,000 bytes and
    the busiest city page within the 130 KB target. Skipped where there is no live data (CI, a fresh clone)."""
    src = os.path.join(ROOT, "data", "latest.json")
    if not os.path.exists(src): pytest.skip("no data/latest.json")
    data = json.load(open(src, encoding="utf-8"))
    days = {}
    for s in data["shows"]: days[s["date"]] = days.get(s["date"], 0) + 1
    busiest = max(days, key=days.get)
    data["generated"] = busiest + "T08:00:00+04:00"
    p = tmp_path / "live.json"; p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = str(tmp_path / "o")
    build.build(str(p), os.path.join(ROOT, "discounts.yaml"), out)
    assert sizes_ok(out) == []
    assert os.path.getsize(os.path.join(out, "dubai", "index.html")) <= 130_000


def test_poster_used_when_present(tmp_path):
    data = json.load(open(DATA, encoding="utf-8"))
    data["films"]["crawlers"]["poster"] = "https://image.example/crawlers.jpg"
    p = tmp_path / "d.json"; p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    build.build(str(p), DISC, str(tmp_path / "o"))
    assert 'src="https://image.example/crawlers.jpg"' in read(str(tmp_path / "o"))


# ---------------------------------------------------------------- fix wave: B (re-release), C (template line), G (names), H (genres, %)

def _built(tmp_path, mutate):
    data = json.load(open(DATA, encoding="utf-8"))
    mutate(data)
    p = tmp_path / "d.json"; p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = str(tmp_path / "o")
    build.build(str(p), DISC, out)
    return out


def test_enriched_genres_render_as_words_and_empty_hides_the_cell(tmp_path):
    def m(d):
        d["films"]["crawlers"]["genres"] = {"ar": ["رعب", "إثارة"], "en": ["horror film", "thriller film"]}
        d["films"]["resident-evil"]["genres"] = {"ar": [], "en": []}
    out = _built(tmp_path, m)
    ar, en = read(out, "film", "crawlers"), read(out, "en", "film", "crawlers")
    assert "<dt>النوع</dt><dd>رعب، إثارة</dd>" in ar and "ar، en" not in ar
    assert "<dt>Genre</dt><dd>horror film, thriller film</dd>" in en
    assert "<dt>النوع</dt>" not in read(out, "film", "resident-evil")
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', en, re.S).group(1)
    assert json.loads(ld)["@graph"][0]["genre"] == ["horror film", "thriller film"]


def test_a_percentage_inside_a_verdict_is_isolated(tmp_path):
    def m(d):
        d["films"]["crawlers"]["verdict"] = {"verdict": "yes", "ar": "قلب الوحش ياب بتقييم نقاد 88%.", "en": "88% of critics.",
                                             "basis": "RT 88% (124 نقد)"}
    out = _built(tmp_path, m)
    ar = read(out, "film", "crawlers")
    assert 'بتقييم نقاد <span class="num" dir="ltr">88%</span>' in ar
    # the ratings under the verdict: two plain items in reading order, never the mixed-language «basis»
    assert '<p class="basis rates"><span>النقاد <span class="num" dir="ltr">22%</span></span><span>الجمهور <span class="num" dir="ltr">35%</span></span></p>' in ar
    assert "RT 88%" not in ar


def test_rerelease_is_labelled_in_both_languages(tmp_path):
    def m(d):
        d["films"]["crawlers"].update(rerelease=True, year=2008)
    out = _built(tmp_path, m)
    assert "إعادة عرض" in read(out, "film", "crawlers") and "إعادة عرض" in read(out)
    assert "Re-release" in read(out, "en", "film", "crawlers") and "Re-release" in read(out, "en")
    assert "إعادة عرض" not in read(out, "film", "resident-evil")


def test_template_verdict_line_is_shown_for_an_unknown_film(tmp_path):
    def m(d):
        d["films"]["crawlers"]["verdict"] = {"verdict": "unknown", "ar": "ما لقينا تقييمات كافية لهالفيلم للحين.",
                                             "en": "Not enough ratings yet.", "basis": "", "by": "template"}
    out = _built(tmp_path, m)
    assert "ما لقينا تقييمات كافية لهالفيلم للحين." in read(out, "film", "crawlers")
    assert "Not enough ratings yet." in read(out, "en", "film", "crawlers")


def test_every_real_cinema_has_a_display_name_in_both_languages():
    names = build.load_cinema_names(os.path.join(ROOT, "cinemas.yaml"))
    ids = set(merged_real()["cinemas"]) | set(json.load(open(DATA, encoding="utf-8"))["cinemas"])
    missing = sorted(i for i in ids if not (names.get(i) or {}).get("ar") or not (names.get(i) or {}).get("en"))
    assert missing == []
    for i, n in names.items():
        assert build.ARABIC.search(n["ar"]) and " — " in n["ar"] and " — " in n["en"], i


def test_arabic_pages_use_the_arabic_cinema_name(tmp_path):
    data = merged_real()
    p = tmp_path / "real.json"; p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = str(tmp_path / "o")
    build.build(str(p), os.path.join(ROOT, "discounts.yaml"), out)
    city = read(out, "al-ain")
    assert "ستار — الفوعة مول" in city and "فوكس — الجيمي مول" in city
    for raw in ("Al Foah -Al Ain", "Mall of Al Ain - Al Ain", "Barari Outlet Mall -Al Ain", "VOX Cinemas Al Jimi Mall"):
        assert raw not in city, raw
    assert "Star — Al Foah Mall" in read(out, "en", "al-ain")
    assert build.clean_reader_name("Al Foah -Al Ain") == "Al Foah - Al Ain"


def test_table_prices_carry_their_own_date_not_live_freshness(tmp_path):
    """Final review, Important 4: a price filled from prices.yaml shows «السعر بتاريخ <entry date>» on
    its cell (and in the slices cinema.js reads), never under a live «updated X min ago»."""
    data = json.load(open(DATA, encoding="utf-8"))
    for s in data["shows"]:
        if s["cinema"] == "vox-al-jimi-mall":
            s["price_source"], s["price_checked"] = "table", "2026-09-25"
    p = tmp_path / "d.json"; p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = str(tmp_path / "o")
    build.build(str(p), DISC, out)
    cin = read(out, "al-ain", "vox-al-jimi-mall")
    cells = re.findall(r'<span class="p"[^>]*>.*?</span></span>', cin)
    assert cells and all('data-asof="2026-09-25"' in c and "السعر بتاريخ" in c for c in cells)
    assert "Price as of" in read(out, "en", "al-ain", "vox-al-jimi-mall")
    city = read(out, "al-ain")
    assert re.search(r'data-cin="vox-al-jimi-mall" data-asof="2026-09-25"', city)
    # a live-priced cinema carries no date note
    star = read(out, "al-ain", "star-bawadi-mall")
    assert 'data-asof="' not in star and '<small class="asof">' not in star
    # slices: the table date rides on the show row for the home tiles and «starting now»
    sl = json.load(open(os.path.join(out, "data", "al-ain-2026-09-25.json"), encoding="utf-8"))
    ci = [c[0] for c in sl["C"]].index("vox-al-jimi-mall")
    rows = [r for r in sl["S"] if r[0] == ci and r[4] >= 0]
    assert rows and all(len(r) == 8 and r[7] == "2026-09-25" for r in rows)
    assert all(len(r) == 7 for r in sl["S"] if r[0] != ci)
    ct = re.search(r"window\.CT = (\{.*?\});</script>", read(out))
    assert ct and json.loads(ct.group(1))["asof"] == "السعر بتاريخ {date}"


def test_bogo_price_says_per_person_with_two_tickets(tmp_path):
    """Final review, Important 6: wherever a BOGO price appears it reads «للشخص — بشرط تذكرتين»."""
    assert build.T["per_person"] == ("للشخص — بشرط تذكرتين", "per person, with 2 tickets")
    out = str(tmp_path / "o")
    build.build(DATA, os.path.join(ROOT, "discounts.yaml"), out)
    assert "للشخص — بشرط تذكرتين" in read(out, "cards", "enbd")       # the worked example
    assert "per person, with 2 tickets" in read(out, "en", "cards", "enbd")
    home = open(os.path.join(ROOT, "src", "js", "home.js"), encoding="utf-8").read()
    prices = open(os.path.join(ROOT, "src", "js", "prices.js"), encoding="utf-8").read()
    # the «starting now» slot, the home's «يبدأ قريب منك» row, every tile and the billboard's «from» all append the
    # per-person note (UI redesign Task 3: the row and renderFrom are their own functions now)
    fn = lambda name: home[home.index("function " + name + "("):].split("\nfunction ", 1)[0]
    assert all(fn(n).count("ppNote(b.r)") == 1 for n in ("renderNow", "renderNear", "renderFrom", "renderHome"))
    assert "ppNote(x.r)" in prices[prices.index("function priceHTML"):prices.index("function renderPrices")]
    assert "r: x.a != null ? x.r : null" in prices                               # best() keeps the rule


def test_film_schedule_prices_each_day_when_days_differ(tmp_path):
    """Prices are sampled per show date: when tomorrow's price differs (or is a dated table price), the
    film page prices each day on its own row instead of letting today's price stand for tomorrow."""
    data = json.load(open(DATA, encoding="utf-8"))
    tomorrow = "2026-09-26"
    base = [s for s in data["shows"] if s["cinema"] == "vox-al-jimi-mall" and s.get("prices")][0]
    t2 = dict(base, date=tomorrow, time="21:00", prices=[{"seat": "Regular", "aed": 77.5}], price_source="table", price_checked="2026-09-25")
    data["shows"].append(t2)
    p = tmp_path / "d.json"; p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = str(tmp_path / "o")
    build.build(str(p), DISC, out)
    film = read(out, "film", base["film"])
    assert 'data-aed="77.50"' in film and 'data-asof="2026-09-25"' in film and "السعر بتاريخ" in film
    assert f'data-aed="{build.money(base["prices"][0]["aed"])}"' in film            # today's live price kept
    # the cinema page prices halls from ONE day, live and today first
    cin = read(out, "al-ain", "vox-al-jimi-mall")
    assert 'data-aed="77.50"' not in cin


# ---------------------------------------------------------------- phase 1: «هـ» markup, root paths, archive

def test_root_files_and_robots(site):
    out, _ = site
    robots = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    assert "Sitemap: https://cinema.elyoxe.com/sitemap.xml" in robots
    nf = open(os.path.join(out, "404.html"), encoding="utf-8").read()
    assert 'lang="ar"' in nf and 'href="/en/"' in nf and "noindex" in nf
    home = read(out)
    assert '<link rel="canonical" href="https://cinema.elyoxe.com/">' in home
    assert 'href="/assets/cinema.css?v=' in home and 'rel="preload" href="/assets/fonts/' in home
    assert 'href="/en/" hreflang="en"' in home


def test_times_are_booking_links_with_show_ids_and_the_ticket_is_server_rendered(site):
    """Review round 1: every time books with no script (an <a href> to the chain's booking page, or the
    chain's site), carries data-show for the ticket, and a show already started is plain text."""
    out, data = site
    film = read(out, "film", "heart-of-the-beast")
    btns = re.findall(r'<a class="tm[^"]*" (href="[^"]*"[^>]*)>', film)
    assert btns and all(re.search(r'href="https?://[^"]+".*data-show="[0-9a-f]{10}" data-start="\d\d:\d\d"', b) for b in btns)
    assert "<button" not in "".join(re.findall(r'<div class="times".*?</div>', film))
    assert re.search(r'<span class="tm past" data-start="(0\d|1[0-7]):\d\d">', film)       # built at 18:00: earlier shows are text
    ids = [re.search(r'data-show="(\w+)"', b).group(1) for b in btns]
    assert len(ids) == len(set(ids))
    assert any("data-ends=" in b and 'data-lang="English"' in b for b in btns)
    tk = film[film.index('<aside class="ticket"'):]
    tk = tk[:tk.index("</aside>")]
    assert 'data-aed="' in tk and "wa.me/?text=" in tk and "أرسلها للقروب" in tk
    assert re.search(r"يخلص تقريباً \d\d:\d\d", tk)
    pl = json.loads(re.search(r'<script type="application/json" id="cinema-p">(.*?)</script>', film).group(1))
    assert all(int(re.search(r'data-p="(\d+)"', b).group(1)) < len(pl) for b in btns if "data-p=" in b)
    cin = read(out, "al-ain", "star-bawadi-mall")
    assert '<aside class="ticket"' in cin and 'class="tm' in cin
    assert 'role="dialog" aria-labelledby="tk-cin"' in tk and 'data-tk-book data-book=' in tk and "data-share=" in tk


def test_every_page_with_times_has_a_filled_ticket_for_its_city(site):
    out, data = site
    city = read(out, "al-ain")
    assert city.count('class="tm') > 5 and "data-tk-rows" in city
    tk = city[city.index('<aside class="ticket"'):]
    cin = re.search(r'data-cin="([^"]+)"', tk).group(1)
    assert data["cinemas"][cin]["city"] == "al-ain"
    for m in re.finditer(r'<div class="scin" data-cin="([^"]+)" data-chain="([^"]+)">', city):
        assert data["cinemas"][m.group(1)]["chain"] == m.group(2)
    home = read(out)
    tk = home[home.index('<aside class="ticket"'):]
    assert "data-tk-rows" in tk and data["cinemas"][re.search(r'data-cin="([^"]+)"', tk).group(1)]["city"] == "dubai"
    film = read(out, "film", "heart-of-the-beast")            # the default ticket is in the city shown first (Dubai)
    tk = film[film.index('<aside class="ticket"'):]
    assert data["cinemas"][re.search(r'data-cin="([^"]+)"', tk).group(1)]["city"] == "dubai"


def test_og_images_exist(site):
    out, _ = site
    for f in all_files(out):
        if f.endswith("offline.html"): continue   # the service worker's fallback, never shared
        if not f.endswith(".html"): continue
        m = re.search(r'<meta property="og:image" content="([^"]+)">', open(f, encoding="utf-8").read())
        assert m, f
        if m.group(1).startswith(build.SITE + "/assets/"):
            assert os.path.exists(os.path.join(out, *m.group(1)[len(build.SITE) + 1:].split("/"))), (f, m.group(1))


def test_dates_are_human_and_english_runs_marked(site):
    out, _ = site
    cin = read(out, "al-ain", "star-bawadi-mall")
    assert "<small>25 سبتمبر 2026</small>" in cin and "25 September 2026" in read(out, "en", "al-ain", "star-bawadi-mall")
    assert 'lang="en">Google Maps</a>' in cin and 'lang="en">Waze</a>' in cin
    assert '<p class="basis rates">' in read(out, "film", "crawlers") and '<bdi dir="ltr" lang="en">' not in read(out, "film", "crawlers")
    assert "E0816F" not in open(os.path.join(ROOT, "src", "cinema.css"), encoding="utf-8").read()
    # font preloads: the Arabic display + body faces (en: the latin body face); the digits' latin subset comes via the stylesheet
    assert 'href="/assets/fonts/readex-arabic.woff2"' in read(out) and 'href="/assets/fonts/markazi-700-arabic.woff2"' in read(out)
    assert read(out).count('as="font"') == 2 and read(out, "en").count('as="font"') == 1
    assert 'href="/assets/fonts/readex-latin.woff2"' in read(out, "en")
    assert "fonts/readex-latin.woff2" in open(os.path.join(ROOT, "src", "cinema.css"), encoding="utf-8").read()


def test_no_poster_hero_is_not_a_colour_field(site):
    """The home billboard (UI redesign Task 3) with no trailer frame: the poster itself (full-bleed on a phone, sharp
    over its blur on a desktop), preloaded; with no poster either, Kit.backdrop's typographic fallback."""
    out, _ = site
    home = read(out)                                   # the fixture's Dubai top tonight (The Paradise) has no poster
    bill = home[home.index('<section class="bill"'):home.index("</section>", home.index('<section class="bill"'))]
    assert '<div class="bd noimg"' in bill and '<span class="pst bd-t">' in bill

    def m(d):
        d["films"]["the-paradise"].update(poster="https://cinema.elyoxe.com/posters/the-paradise-342.webp",
                                          poster_2x="https://cinema.elyoxe.com/posters/the-paradise-684.webp")
    import tempfile
    h = read(_built(__import__("pathlib").Path(tempfile.mkdtemp()), m))
    assert re.search(r'<div class="bd pf" style="--pc:#[0-9A-Fa-f]{6}" aria-hidden="true"><img src="/posters/the-paradise-342\.webp"[^>]* class="pb"[^>]*fetchpriority="high">'
                     r'<img [^>]*class="ps"', h)
    pre = re.search(r'<link rel="preload" as="image" href="([^"]+)" imagesrcset="([^"]+)" imagesizes="([^"]+)"', h)
    first = re.search(r'<img src="([^"]+)" srcset="([^"]+)" sizes="([^"]+)"[^>]*fetchpriority="high"', h)
    assert pre and first and pre.groups() == first.groups()
    assert h.count('fetchpriority="high"') == 2      # the preload link and the billboard's poster: no tile claims it


def test_ends_only_when_known(site):
    out, _ = site
    film = read(out, "film", "crawlers")          # the fixture gives Crawlers no end times
    assert "data-ends=" not in film and "يخلص تقريباً" not in film.split("<script>window.CT")[0]


def test_posters_and_tiles(site):
    out, _ = site
    home = read(out)
    # a grid tile's poster: img with width descriptors and the size the grid draws it at (3 columns / 7);
    # our own posters are root-relative in markup (absolute in og:image and JSON-LD). The billboard is the
    # page's image priority (tests above): no tile has fetchpriority, and all but the first are lazy
    assert re.search(r'<img src="/posters/coyote-vs-acme-342\.webp" srcset="[^"]+-342\.webp 342w, [^"]+-684\.webp 684w" sizes="\(min-width:1024px\) 13vw, 32vw"', home)
    assert 'fetchpriority="high"' not in home
    assert home.count('loading="lazy"') >= 1
    # no poster: a typographic tile in the film's colour (or a hue from its id), never a broken image
    assert re.search(r'<span class="pst" style="--pc:#1D2A4A"><span class="pst-t">سبايدر مان', home)
    assert re.search(r'<span class="pst" style="--pc:#[0-9A-F]{6}"><span class="pst-t"[^>]*>The Paradise', home)
    assert 'data-genres="animation comedy family" data-family="1" data-kids="1"' in home
    # the controls live in the filter sheet now (UI redesign Task 3)
    assert 'data-filter="family"' in home and 'data-sort="price"' in home and 'data-before="21:00"' in home


def test_hostile_media_fields_are_dropped(tmp_path):
    def m(d):
        d["films"]["crawlers"].update(poster="javascript:alert(1)", poster_color="red;background:url(x)", trailer="<script>")
    out = _built(tmp_path, m)
    film = read(out, "film", "crawlers")
    assert "javascript:" not in film and "url(x)" not in film and "&lt;script&gt;" not in film


def test_archived_film_keeps_its_page(site):
    out, data = site
    ar, en = read(out, "film", "weapons"), read(out, "en", "film", "weapons")
    assert "عُرض في سينمات الإمارات من 7 أغسطس إلى 17 سبتمبر 2026" in ar
    assert "Shown in UAE cinemas from 7 August to 17 September 2026" in en
    assert "المعروض الحين" in ar and 'class="btn light" href="/"' in ar
    assert '<aside class="ticket"' not in ar and 'class="tm' not in ar
    similar = ar[ar.index('class="tonight wrap similar"'):]
    tiles = re.findall(r'<a class="film[^"]*" href="/film/([^/]+)/"', similar)
    assert 0 < len(tiles) <= 6 and "weapons" not in tiles and "the-long-walk" not in tiles
    # a shared genre first (horror / thriller), then the verdict: Resident Evil (mixed) before Crawlers (skip)
    assert set(tiles[:3]) == {"resident-evil", "crawlers", "sacrifice"}
    assert tiles.index("resident-evil") < tiles.index("crawlers")
    nodate = read(out, "film", "the-long-walk")
    assert '<p class="arch-s">انتهى عرضه في السينما</p>' in nodate
    for page in (read(out), read(out, "al-ain"), read(out, "al-ain", "star-bawadi-mall")):
        assert "/film/weapons/" not in page and "/film/the-long-walk/" not in page
    for f in os.listdir(os.path.join(out, "data")):
        if f == "search.json":
            # pages/search.py (task A5, ruling round 2, task-A5-review.md): search is a lookup surface, not
            # a listing -- an archived film keeps a real page (this very test asserts that above), so it
            # stays findable there too, marked `x` and ranked after every showing match by the client,
            # never silently indistinguishable from a film still on. Every other data file keeps this
            # test's original contract untouched.
            entries = json.loads(open(os.path.join(out, "data", f), encoding="utf-8").read())
            weapons = [e for e in entries if e.get("p") == "film/weapons"]
            assert weapons and weapons[0].get("x") == 1
            continue
        assert "weapons" not in open(os.path.join(out, "data", f), encoding="utf-8").read()
    sm = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    assert "<loc>https://cinema.elyoxe.com/film/weapons/</loc><lastmod>2026-09-17</lastmod>" in sm


def test_no_middle_dot_fact_strings(site):
    out, _ = site
    for f in all_files(out):
        if f.endswith(".html"):
            body = re.sub(r"<script.*?</script>", "", open(f, encoding="utf-8").read().split("<body", 1)[1], flags=re.S)
            assert " · " not in body, f


def test_real_poster_tile_puts_the_title_under_the_poster(site):
    """A tile (UI redesign Task 3): the poster, then the title on its own line under it, then the price. A real
    poster carries its own title, so nothing is drawn over it; a tile with no poster keeps its typographic title
    inside too (the line under it names the film either way)."""
    out, _ = site
    home = read(out)
    tile = re.search(r'<a class="film[^"]*" href="/film/coyote-vs-acme/".*?</a>', home, re.S).group(0)
    assert '<span class="pst img"' in tile and 'class="pst-t"' not in tile
    assert re.search(r'</span></span><span class="t"[^>]*>كايوتي ضد أكمي</span><span class="m" data-cheap>', tile)
    # a failed image gives way to the tile's colour: cinema.js posterFallback() (no inline handler per tile)
    assert "onerror" not in tile
    assert "classList.remove(\"img\")" in open(os.path.join(ROOT, "src", "js", "main.js"), encoding="utf-8").read()
    notile = re.search(r'<a class="film[^"]*" href="/film/[^"]+/"[^>]*>(?:(?!</a>).)*?<span class="pst" style="--pc:#1D2A4A">.*?</a>', home, re.S).group(0)
    assert '<span class="pst-t">سبايدر مان' in notile and '<span class="t">سبايدر مان' in notile


def test_live_shape_subs_list_and_iso_lang(tmp_path):
    """Live latest.json (Task 2): show lang is an ISO key and subs a list — the ticket names them in words."""
    def m(d):
        for s in d["shows"]:
            s["lang"], s["subs"] = "en", ["ar", "en"]
    out = _built(tmp_path, m)
    home = read(out)
    assert "إنجليزي، ترجمة عربي، إنجليزي" in home
    assert "English, Arabic, English subtitles" in read(out, "en")


def test_mirrored_poster_paths_are_kept_and_made_absolute(tmp_path):
    """posters.py writes site-root paths (/posters/<fid>-<hash>-342.webp); they must survive the URL
    sanitiser (which only knew http/https) and become absolute for og:image. Other relative paths still drop."""
    def m(d):
        d["films"]["crawlers"].update(poster="/posters/crawlers-0123456789-342.webp", poster_2x="/posters/crawlers-0123456789-684.webp")
        d["films"]["resident-evil"].update(poster="/etc/passwd", poster_2x="//evil.example/x.webp")
    out = _built(tmp_path, m)
    film = read(out, "film", "crawlers")
    assert 'src="/posters/crawlers-0123456789-342.webp"' in film
    assert 'content="https://cinema.elyoxe.com/posters/crawlers-0123456789-684.webp"' in film
    re_ = read(out, "film", "resident-evil")
    assert "/etc/passwd" not in re_ and "evil.example" not in re_
