"""pages/bollywood.py (r3-home, owner idea 2026-09-30): /bollywood/ + /en/bollywood/, a language-tabbed hub for
Hindi/Malayalam/Tamil/Telugu films, plus its home row and footer/nav reachability."""
import os
import re

import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
MODULES = build.discover(only=("core", "bollywood"))


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def build_out(tmp_path, data_path=DATA):
    o = str(tmp_path / "out")
    build.build(data_path, DISC, o, noindex=False, modules=MODULES)
    return o


def test_bollywood_hub_lists_only_its_languages_by_tab(tmp_path):
    o = build_out(tmp_path)
    h = read(o, "bollywood", "index.html")
    assert 'data-fid="the-paradise"' in h                 # the fixture's one Telugu film
    for other in ("heart-of-the-beast", "shish-dou"):     # English/Arabic films never show up here
        assert f'data-fid="{other}"' not in h
    assert re.search(r'<h2>تيلوغو</h2>', h)


def test_bollywood_hub_english_variant(tmp_path):
    o = build_out(tmp_path)
    en = read(o, "en", "bollywood", "index.html")
    assert "Bollywood and South India" in en and 'data-fid="the-paradise"' in en


def test_bollywood_hub_is_linked_from_the_footer_even_with_one_film(tmp_path):
    """The footer's NavItem needs only ≥1 qualifying film (register() skips the module with none) — the home
    row's own ≥4 rule (dedupe, §2.1) is a separate, stricter gate."""
    o = build_out(tmp_path)
    home = read(o, "index.html")
    foot = re.search(r'<nav class="foot-l".*?</nav>', home, re.S).group(0)
    assert 'href="/bollywood/"' in foot
    assert "r-bollywood" not in home             # only 1 qualifying film in this fixture: below the row's ≥4


def test_bollywood_row_appears_once_at_least_four_films_qualify_and_links_the_all(tmp_path):
    """4 distinct bollywood-language films, priced above everything else tonight so «أرخص عرض الليلة» never claims
    them first (the dedupe rule, §2.1) — the row needs 4 *fresh* films of its own, not 4 that another row already
    opened with."""
    import json
    d = json.load(open(DATA, encoding="utf-8"))
    for s in d["shows"]:
        if s["film"] == "the-paradise":
            s["prices"] = [dict(p, aed=899) for p in s.get("prices") or []]
    for i, lang in enumerate(("Hindi", "Malayalam", "Tamil")):
        fid = f"bw-extra-{i}"
        d["films"][fid] = dict(d["films"]["the-paradise"], lang=lang, title=f"BW Extra {i}")
        new_shows = []
        for s in d["shows"]:
            if s["film"] == "the-paradise":
                s2 = dict(s, film=fid)
                s2["prices"] = [dict(p, aed=900 + i) for p in s2.get("prices") or []]
                new_shows.append(s2)
        d["shows"] += new_shows
    p = tmp_path / "with_bw.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = build_out(tmp_path, str(p))
    home = read(o, "index.html")
    assert re.search(r'<a class="rail-a" href="/bollywood/"><h2 id="r-bollywood">بوليوود وجنوب الهند</h2>', home)
    row = re.search(r'<section class="rail" aria-labelledby="r-bollywood".*?</section>', home, re.S).group(0)
    assert row.count('class="tile') >= 4


def test_bollywood_module_is_skipped_when_nothing_qualifies(tmp_path):
    """No Hindi/Malayalam/Tamil/Telugu film in the data: register() returns an empty Plugin — no /bollywood/ page,
    no row, no dead footer link (never a page with zero films and a noindex crumb to maintain)."""
    import json
    d = json.load(open(DATA, encoding="utf-8"))
    d["films"]["the-paradise"]["lang"] = "English"
    p = tmp_path / "no_bw.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = build_out(tmp_path, str(p))
    home = read(o, "index.html")
    assert "r-bollywood" not in home and "بوليوود" not in home
    assert not os.path.exists(os.path.join(o, "bollywood", "index.html"))
