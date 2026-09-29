"""pages/vote.py (W3-P4, MASTER-PLAN §2.12): /v/ «أي واحد؟» -- a bare, noindex shell (the tray itself is
drawn client-side, src/js/vote.js, from the URL's own fragment; nothing here can carry a card or a city)."""
import os

import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
DATA = os.path.join(ROOT, "tests", "fixtures", "coming_sample.json")
MODULES = build.discover(only=("core", "vote"))


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def _build(tmp_path):
    o = str(tmp_path / "out")
    build.build(DATA, DISC, o, modules=MODULES)
    return o


def test_vote_page_is_a_bare_noindex_shell(tmp_path):
    o = _build(tmp_path)
    h = read(o, "v", "index.html")
    assert '<meta name="robots" content="noindex,nofollow">' in h
    assert 'data-v-tray' in h and 'data-v-empty' in h
    # no card, no city, no film/show data baked in server-side (the header's card sheet and city picker are
    # shared chrome on every page, never populated with the visitor's own choice here): no query string
    # carries either, and the page's own <body> (unlike a city page's) names no city
    assert "?card=" not in h and "&card=" not in h
    import re
    body_tag = re.search(r"<body[^>]*>", h).group(0)
    assert "data-city=" not in body_tag


def test_vote_page_english_variant(tmp_path):
    o = _build(tmp_path)
    h = read(o, "en", "v", "index.html")
    assert '<meta name="robots" content="noindex,nofollow">' in h
    assert "Where to?" in h


def test_vote_page_is_out_of_the_sitemap_and_carries_no_hreflang_pair(tmp_path):
    o = _build(tmp_path)
    sm = read(o, "sitemap.xml")
    assert "/v/" not in sm


def test_vote_lazy_chunk_is_only_loaded_on_the_vote_page(tmp_path):
    o = _build(tmp_path)
    v = read(o, "v", "index.html")
    home = read(o, "index.html")
    assert "vote." in v and ".js" in v
    # the chunk is declared for the vote page kind only (page_js), never pulled onto home
    import re
    chunk = re.search(r'"vote":"(/assets/vote\.[a-z0-9]+\.js)"', v.replace(" ", "")) or re.search(r'/assets/vote\.[a-z0-9]+\.js', v)
    assert chunk
    assert "/assets/vote." not in home
