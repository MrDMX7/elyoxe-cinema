"""«أفضل وقت تروح» on the cinema page (pages/_core/places.py's cinema_head): the line renders only when
data["cinemas"][cid]["best_time"] is present (steps/occupancy_history.py's own contract — never guessed by
the page), and never for a cinema without one."""
import json
import shutil
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


@pytest.fixture
def data_with_best_time(tmp_path):
    d = json.loads(DATA.read_text(encoding="utf-8"))
    d["cinemas"][CID]["best_time"] = {"part": "morning", "occ": 0.2}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def test_renders_the_line_when_best_time_is_present(data_with_best_time, tmp_path):
    out = tmp_path / "out"
    build.build(str(data_with_best_time), DISC, str(out), noindex=False)
    city = json.loads(data_with_best_time.read_text(encoding="utf-8"))["cinemas"][CID]["city"]
    h = main_of((out / city / CID / "index.html").read_text(encoding="utf-8"))
    assert "best-time" in h
    assert "الصبح" in h


def test_no_line_for_a_cinema_without_best_time(tmp_path):
    out = tmp_path / "out"
    build.build(str(DATA), DISC, str(out), noindex=False)
    d = json.loads(DATA.read_text(encoding="utf-8"))
    city = d["cinemas"][CID]["city"]
    h = main_of((out / city / CID / "index.html").read_text(encoding="utf-8"))
    assert "best-time" not in h
