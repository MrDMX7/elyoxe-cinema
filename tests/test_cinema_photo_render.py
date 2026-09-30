"""The cinema page's own photo (pages/_core/places.py's cinema_head): renders a darkened full-bleed
band only when cinema["photo"] is present, never guessed."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

import build  # noqa: E402

FIX = ROOT / "fixtures"
DATA, DISC = FIX / "sample_latest.json", str(FIX / "sample_discounts.yaml")
CID = "vox-al-jimi-mall"


def main_of(h):
    return h[h.index("<main"):h.index("</main>")]


def test_renders_the_photo_band_when_present(tmp_path):
    d = json.loads(DATA.read_text(encoding="utf-8"))
    d["cinemas"][CID]["photo"] = {"w1280": "/posters/cin-x-1280.webp", "w640": "/posters/cin-x-640.webp",
                                  "w": 1600, "h": 900}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    out = tmp_path / "out"
    build.build(str(p), DISC, str(out), noindex=False)
    city = d["cinemas"][CID]["city"]
    h = main_of((out / city / CID / "index.html").read_text(encoding="utf-8"))
    assert "chead-photo" in h and "chead-bd" in h and "/posters/cin-x-1280.webp" in h


def test_no_photo_band_without_a_photo(tmp_path):
    out = tmp_path / "out"
    build.build(str(DATA), DISC, str(out), noindex=False)
    d = json.loads(DATA.read_text(encoding="utf-8"))
    city = d["cinemas"][CID]["city"]
    h = main_of((out / city / CID / "index.html").read_text(encoding="utf-8"))
    assert "chead-photo" not in h and "chead-bd" not in h
