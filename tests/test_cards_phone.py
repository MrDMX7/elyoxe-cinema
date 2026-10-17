"""/cards/ on a phone (W2-P9, 2026-10-17): one block per card beside the matrix — the best current offer in gold with the
chains that give it, every other chain's offer on one line, «ما لقينا خصم» for a card with none; the matrix stays for
the desktop."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def test_cards_index_carries_a_phone_block_per_card_and_keeps_the_matrix(tmp_path):
    o = str(tmp_path / "out")
    build.build(DATA, DISC, o, modules=build.discover(only=("core",)))
    for lang in ("ar", "en"):
        h = read(o, *(("cards", "index.html") if lang == "ar" else ("en", "cards", "index.html")))
        assert '<table class="matrix">' in h
        blocks = re.findall(r'<a class="cph" href="([^"]+)">(.*?)</a>', h, re.S)
        rows = re.findall(r'<tr><th scope="row"><a href="([^"]+)">', h)
        assert [b[0] for b in blocks] == rows                      # the same cards, in the same order, as the matrix
        assert all('class="cph-n"' in b[1] and 'class="cph-b"' in b[1] for b in blocks)
        gold = [b for b in blocks if 'class="off"' in b[1]]
        assert gold, "at least one card has a current offer in the fixture"
        assert all(('في ' if lang == "ar" else 'at ') in b[1] for b in gold)   # …with where it works
        assert all('class="cph-c"' in b[1] or 'class="off"' in b[1] or 'class="nil"' in b[1] for b in blocks)
    css = read(o, "assets", "cinema.css")
    assert ".cph-l{display:none}" in css.replace(" ", "") or "cph-l{display:none" in css
