"""The show key (MASTER-PLAN §2.2, W1-P1): /film/<fid>/#s-<key>, key = FNV-1a 32-bit over the UTF-8 of «cinema|date|
time|hall key», base36, left-padded to 6. Its two twins, site_kit.Kit.show_key and showKey() in src/js/core.js, must give
the same key for every show; the key names one show (asserted on the fixture; on the day's real data a same-film twin
only warns, so the hourly deploy never stops on chance); and no page carries a duplicate id (the film page's time links
will carry id="s-<key>", W2-P3). Node parts skip without node, as tests/test_js.py does (the Fold may not have it)."""
import json, os, re, shutil, subprocess, sys, warnings
from collections import Counter
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
from site_kit import Halls, Kit  # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node not installed")
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
REAL = os.path.join(ROOT, "data", "latest.json")


def js_show_key(tmp_path, rows):
    """showKey() as core.js declares it, run in node over [cinema, date, time, hall key] rows."""
    core = Path(ROOT, "src", "js", "core.js").read_text(encoding="utf-8")
    fn = re.search(r"^function showKey\(.*?^\}$", core, re.S | re.M).group(0)
    (tmp_path / "k.js").write_text(fn + "\nprocess.stdout.write(JSON.stringify(" + json.dumps(rows) + ".map(function (r) { return showKey(r[0], r[1], r[2], r[3]); })));\n",
                                   encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "k.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def shows_of(path):
    """Every show of a latest.json as [cinema, date, time, hall key], the hall key as Kit.hkey computes it."""
    d = json.load(open(path, encoding="utf-8"))
    h = Halls(os.path.join(ROOT, "halls.yaml"))
    cin = d["cinemas"]
    return [[s["cinema"], s["date"], s["time"], h.key(cin[s["cinema"]]["chain"], s.get("hall") or "OTHER", s.get("hall_label") or "")]
            for s in d["shows"] if s.get("cinema") in cin]


def test_the_python_key_is_fnv1a_base36_padded():
    # no hall key means the regular hall, as Kit.hkey and showKey() both say it
    assert Kit.show_key("reel-dubai-mall", "2026-09-28", "21:30", "Standard") == Kit.show_key("reel-dubai-mall", "2026-09-28", "21:30", None)
    k = Kit.show_key("reel-dubai-mall", "2026-09-28", "21:30", "IMAX")
    assert re.fullmatch(r"[0-9a-z]{6,7}", k)
    h = 0x811C9DC5
    for b in "reel-dubai-mall|2026-09-28|21:30|IMAX".encode():
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    assert int(k, 36) == h
    # 2^32 is 7 base36 digits at most; a small hash is left-padded to 6
    ks = [Kit.show_key("c", "d", str(t), "h") for t in range(3000)]
    assert all(6 <= len(x) <= 7 for x in ks) and all(int(x, 36) < 2 ** 32 for x in ks)


@needs_node
def test_python_and_js_agree_on_every_show_of_the_fixture(tmp_path):
    rows = shows_of(DATA)
    assert len(rows) > 100
    py = [Kit.show_key(*r) for r in rows]
    assert js_show_key(tmp_path, rows) == py
    assert all(re.fullmatch(r"[0-9a-z]{6,7}", k) for k in py)
    # one key per show: distinct shows never share a key in the fixture
    assert len(set(py)) == len({tuple(r) for r in rows})
    # non-ASCII fields hash their UTF-8 bytes on both sides
    odd = [["سينما", "2026-09-28", "22:10", "قاعة"], ["c", "2026-09-28", "00:05", ""], ["c", "2026-09-28", "00:05", None]]
    assert js_show_key(tmp_path, odd) == [Kit.show_key(*r) for r in odd]


def same_film_twins(films, rows, key=Kit.show_key):
    """Distinct shows of one film that share a key: [(film, key, [show, show…])]. The key only lives under
    /film/<fid>/#s-<key>, so a key shared across two films names nothing twice; inside one film it would."""
    by = {}
    for f, r in zip(films, rows):
        by.setdefault((f, key(*r)), set()).add(tuple(r))
    return [(f, k, sorted(s)) for (f, k), s in by.items() if len(s) > 1]


def test_a_same_film_twin_is_found_and_a_cross_film_one_is_not():
    rows = [["a", "2026-09-28", "21:30", "IMAX"], ["b", "2026-09-28", "22:00", "Standard"], ["a", "2026-09-28", "21:30", "IMAX"]]
    one = lambda *r: "000000"                     # every show on one key: the only way to force a 32-bit collision
    assert same_film_twins(["f1", "f2", "f1"], rows, one) == []                      # across films, and a repeated row
    assert same_film_twins(["f1", "f1", "f1"], rows, one) == [("f1", "000000", sorted({tuple(rows[0]), tuple(rows[1])}))]
    assert same_film_twins(["f1", "f1"], rows[:2]) == []                             # the real key keeps them apart


@needs_node
@pytest.mark.skipif(not os.path.exists(REAL), reason="no data/latest.json")
def test_python_and_js_agree_on_every_real_show(tmp_path):
    """Parity over every show of data/latest.json: a property of the code, so it asserts whatever the day's data.

    Uniqueness is a property of the data, so it only warns (review I1). The Fold runs `pytest -x` before every hourly
    deploy, and a 32-bit key over the Fold's 5,087 distinct shows (2026-09-28) meets a twin by chance: 1 day's data in
    ~330 across films (harmless: the key lives under one film's page) and 1 in ~3,800 inside one film (0.026 %; the
    busiest film has 903 shows). A
    failing assertion here would stop every deploy for as long as the two shows stay in the data. No page prints the key
    yet; the page that will (W2-P3's time links, id="s-<key>") resolves a same-film twin at build time (docs/PLUGINS.md).
    The fixture's shows are fixed, so there uniqueness is asserted (test above)."""
    d = json.load(open(REAL, encoding="utf-8"))
    rows = shows_of(REAL)
    films = [s.get("film") for s in d["shows"] if s.get("cinema") in d["cinemas"]]
    assert len(films) == len(rows)
    py = [Kit.show_key(*r) for r in rows]
    assert js_show_key(tmp_path, rows) == py
    twins = same_film_twins(films, rows)
    if twins:
        warnings.warn(f"show key: {len(twins)} same-film twin(s) in data/latest.json, first {twins[:2]}; the film page must "
                      "resolve them at build time (W2-P3)", UserWarning)


def test_the_key_only_reads_the_four_fields():
    s = {"cinema": "reel-dubai-mall", "film": "a", "date": "2026-09-28", "time": "21:30", "hall": "IMAX", "hall_label": "IMAX with Laser",
         "prices": [{"seat": "x", "aed": 60}], "book": "https://x/1"}
    site = build.Site(json.load(open(DATA, encoding="utf-8")), build.load_discounts(DISC), Halls(os.path.join(ROOT, "halls.yaml")), "unused",
                      modules=build.discover(only=("core",)))
    site.cinemas = dict(site.cinemas, **{"reel-dubai-mall": {"chain": "reel", "city": "dubai"}})
    k = site.show_key_of(s)
    for change in ({"film": "b"}, {"prices": []}, {"book": None}, {"seats_left": 3}, {"lang": "en", "subs": "ar"}):
        assert site.show_key_of(dict(s, **change)) == k
    for change in ({"time": "21:31"}, {"date": "2026-09-29"}, {"cinema": "reel-dubai-mall-2"}):
        t = dict(s, **change)
        if t["cinema"] not in site.cinemas: site.cinemas[t["cinema"]] = {"chain": "reel", "city": "dubai"}
        assert site.show_key_of(t) != k
    assert k == Kit.show_key("reel-dubai-mall", "2026-09-28", "21:30", site.hkey(s))


def test_the_slices_hall_key_is_the_keys_hall_field(tmp_path):
    """The board's rows and the film page find a show by the key; both read the hall key the slices carry (H[i][1] after
    the chain), which is Kit.hkey: the same field the Python twin hashes."""
    out = str(tmp_path / "o")
    build.build(DATA, DISC, out, noindex=False, modules=build.discover(only=("core",)))
    d = json.load(open(DATA, encoding="utf-8"))
    h = Halls(os.path.join(ROOT, "halls.yaml"))
    want = {Kit.show_key(s["cinema"], s["date"], s["time"], h.key(d["cinemas"][s["cinema"]]["chain"], s.get("hall") or "OTHER", s.get("hall_label") or ""))
            for s in d["shows"] if s.get("cinema") in d["cinemas"] and d["films"].get(s["film"], {}).get("status") != "archived"}
    got = set()
    for f in Path(out, "data").glob("*-20*.json"):
        j = json.loads(f.read_text(encoding="utf-8"))
        day = re.search(r"(\d{4}-\d\d-\d\d)\.json$", f.name).group(1)
        got |= {Kit.show_key(j["C"][a[0]][0], day, a[2], j["H"][a[3]][1].split("|", 1)[1]) for a in j["S"]}
    assert got == want


def test_no_page_carries_a_duplicate_id(tmp_path):
    """§7.3 #9: an id names one element. The film page's time links will each carry id="s-<key>" (W2-P3), so the guard
    is in place before they land: every page of the fixture build, both languages."""
    out = str(tmp_path / "o")
    build.build(DATA, DISC, out, noindex=False)
    bad, n = [], 0
    for f in Path(out).rglob("*.html"):
        ids = re.findall(r'\sid="([^"]+)"', f.read_text(encoding="utf-8"))
        n += 1
        d = [k for k, c in Counter(ids).items() if c > 1]
        if d: bad.append((str(f.relative_to(out)), d[:3]))
    assert n > 100 and not bad, bad[:5]
