"""pages/coming.py + pages/hubs.py (Task 2): /coming/, /arabic/, /events/, the last-chance strip,
and the «نازل الخميس» nav re-point -- built with only core + these two modules so this test
never depends on other in-flight phase-2 page modules landing in pages/ at the same time."""
import json
import os
import re

import pytest

import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
DATA = os.path.join(ROOT, "tests", "fixtures", "coming_sample.json")
MODULES = build.discover(only=("core", "coming", "hubs"))


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("coming_hubs"))
    build.build(DATA, DISC, o, modules=MODULES)
    return o


def test_coming_page_groups_by_release_thursday_and_dated_countdown(out):
    h = read(out, "coming", "index.html")
    assert "نازل الخميس" in h
    assert "1 أكتوبر 2026" in h        # Verity's release_date (2026-10-01) is itself a Thursday
    assert "التاريخ لاحقاً" in h        # Gatto has no release_date
    assert "cs-card" in h and h.count("cs-card") == 2
    assert '<button type="button" class="btn ghost cs-notify" disabled>' in h  # phase-3 placeholder, inert


def test_coming_page_english_variant(out):
    h = read(out, "en", "coming", "index.html")
    assert "Out Thursday" in h and "Date to be announced" in h


def test_thursday_nav_link_repoints_to_coming(out):
    home = read(out, "index.html")
    nav = re.search(r'<nav class="nav".*?</nav>', home, re.S).group(0)
    assert '<a href="/coming/">نازل الخميس</a>' in nav


def test_coming_data_slice_written(out):
    d = json.loads(read(out, "data", "coming.json"))
    assert set(d) == {"verity", "gatto"}
    assert d["verity"]["release_date"] == "2026-10-01"


def test_arabic_hub_lists_only_arabic_language_films(out):
    ar = read(out, "arabic", "index.html")
    assert 'data-fid="shish-dou"' in ar
    for other in ("heart-of-the-beast", "resident-evil", "the-paradise"):
        assert f'data-fid="{other}"' not in ar   # English/Telugu films never show up here


def test_arabic_hub_english_variant(out):
    en = read(out, "en", "arabic", "index.html")
    assert "Arabic & Gulf" in en


def test_events_hub_lists_recognised_events_from_data(out):
    h = read(out, "events", "index.html")
    assert "K-Fest" in h or "مهرجان كي-فست" in h
    assert '<a class="nm" href="/film/heart-of-the-beast/">' in h
    assert "noindex" not in h   # real event data exists -- indexed normally
    sm = read(out, "sitemap.xml")
    assert "<loc>https://cinema.elyoxe.com/events/</loc>" in sm


def test_events_hub_empty_state_is_noindex_and_out_of_sitemap(tmp_path):
    # Fix round 2 (re-review, Critical persisted): a genuinely empty /events/ must be noindex and
    # excluded from the sitemap -- tests/test_preview.py carries a matching exemption for this
    # exact honest-empty text so that pre-existing, project-wide contract still holds.
    data = json.loads(open(DATA, encoding="utf-8").read())
    data["events"] = []
    empty_data = tmp_path / "no_events.json"
    empty_data.write_text(json.dumps(data), encoding="utf-8")
    o = str(tmp_path / "out")
    build.build(str(empty_data), DISC, o, modules=MODULES)

    h = open(os.path.join(o, "events", "index.html"), encoding="utf-8").read()
    assert "ما عندنا فعاليات مؤكدة" in h
    assert '<meta name="robots" content="noindex,nofollow">' in h
    en = open(os.path.join(o, "en", "events", "index.html"), encoding="utf-8").read()
    assert "No chain-confirmed events yet" in en
    assert '<meta name="robots" content="noindex,nofollow">' in en

    sm = open(os.path.join(o, "sitemap.xml"), encoding="utf-8").read()
    assert "/events/" not in sm   # excluded entirely, ar and en both


def test_events_hub_with_real_events_is_indexed_and_in_sitemap(out):
    # `out` is the module fixture built from tests/fixtures/coming_sample.json, which carries a
    # real (K-Fest) event -- the opposite case from the empty-state test above.
    h = read(out, "events", "index.html")
    assert "noindex" not in h
    sm = read(out, "sitemap.xml")
    assert "<loc>https://cinema.elyoxe.com/events/</loc>" in sm
    assert "<loc>https://cinema.elyoxe.com/en/events/</loc>" in sm


def test_last_chance_strip_on_home_and_its_city_only(out):
    home = read(out, "index.html")
    assert "آخر فرصة" in home and 'data-fid="heart-of-the-beast"' in home

    al_ain = read(out, "al-ain", "index.html")
    assert "آخر فرصة" in al_ain and 'data-fid="heart-of-the-beast"' in al_ain

    dubai = read(out, "dubai", "index.html")
    assert "class=\"tonight wrap last-chance\"" not in dubai   # only the al-ain slice has one
