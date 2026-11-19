"""«عروض مجانية» (owner 2026-11-19): steps/free_screenings.py reads JLT, NYU Abu Dhabi, Cinema Akil's free sessions and
Alserkal, adds free_screenings.yaml, and keeps what is still to come. Samples in tests/fixtures/free/ are the sources'
own responses of 2026-11-19, trimmed."""
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "free"
spec = importlib.util.spec_from_file_location("free_screenings", ROOT / "steps" / "free_screenings.py")
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)
CITIES = {"dubai", "abu-dhabi", "sharjah", "al-ain", "ajman", "ras-al-khaimah", "fujairah", "umm-al-quwain"}


def test_jlt_reads_the_whole_saturday_line_up():
    items = fs.parse_jlt((FIX / "jlt.html").read_text(encoding="utf-8"))
    assert [(i["date"], i["title"]) for i in items[:2]] == [("2026-11-21", "Inside Out 2"), ("2026-11-28", "Toy Story")]
    assert (items[-1]["date"], items[-1]["title"]) == ("2027-01-30", "Rio")      # the season runs into the next year
    assert len(items) == 11 and {i["time"] for i in items} == {"19:30"}
    assert all(i["price"] == 0 and i["city"] == "dubai" and i["venue_ar"] for i in items)


def test_nyuad_keeps_screenings_only_one_per_performance():
    items = fs.parse_nyuad(json.loads((FIX / "nyuad.json").read_text(encoding="utf-8")))
    assert [(i["title"], i["date"], i["time"]) for i in items] == [("Hekayah | The Story", "2026-11-25", "19:30")]
    assert items[0]["city"] == "abu-dhabi" and items[0]["url"].startswith("https://publicprograms.nyuad.nyu.edu/en/")


def test_akil_lists_only_sessions_priced_zero():
    items = fs.parse_akil(json.loads((FIX / "akil.json").read_text(encoding="utf-8")))
    assert {i["title"] for i in items} == {"Taxi Driver", "Police Story", "The Dating Menu"}   # Fjord costs 52.50
    police = next(i for i in items if i["title"] == "Police Story")
    assert (police["date"], police["time"], police["price"]) == ("2026-11-07", "19:00", 0)
    assert "Yard" in police["venue"] and police["url"].startswith("https://www.cinemaakil.com/now-showing-booking/")


def test_alserkal_takes_the_film_screening_cards():
    items = fs.parse_alserkal((FIX / "alserkal.html").read_text(encoding="utf-8"))
    assert len(items) == 3 and all(i["url"].startswith("https://alserkal.online/event/") for i in items)
    assert items[0]["title"] == "Crossings: Kaleh Ziyarat" and items[0]["date"] == "2026-11-20"
    assert "Common Room" in items[0]["venue"]


def test_the_hand_list_is_complete_and_sourced():
    items = fs.hand_items()
    assert items, "free_screenings.yaml has no items"
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids))
    for i in items:
        assert i["city"] in CITIES and i["url"].startswith("https://") and i.get("checked"), i["id"]
        assert "price" in i and (i["price"] is None or i["price"] >= 0), i["id"]
        assert i["title_ar"] and i["venue_ar"], i["id"]
        date.fromisoformat(i["date"])
        if i.get("end_date"):
            assert i["end_date"] >= i["date"], i["id"]


def _it(id_, d, source="jlt", **kw):
    return {"id": id_, "title": id_, "city": "dubai", "date": d, "time": "19:30", "price": 0, "url": "u", "source": source, **kw}


def test_collect_keeps_what_is_to_come_and_a_failed_source_keeps_its_last_items():
    today = date(2026, 11, 20)
    fetched = {"jlt": [_it("past", "2026-11-19"), _it("sat", "2026-11-21"), _it("far", "2027-06-01")],
               "nyuad": RuntimeError("503")}
    previous = [_it("ny-old", "2026-11-18", "nyuad"), _it("ny-next", "2026-11-25", "nyuad")]
    hand = [_it("fest", "2026-11-01", "hand", end_date="2026-12-01"), _it("sat", "2026-11-21", "hand")]
    items, report = fs.collect(fetched, hand, previous, today)
    assert [i["id"] for i in items] == ["fest", "sat", "ny-next"]     # a running festival stays; past and far go
    assert report["jlt"] == 3 and report["nyuad"].startswith("error: RuntimeError") and "kept 2" in report["nyuad"]


def test_offline_run_writes_the_hand_list(monkeypatch, tmp_path):
    data = {}
    out = fs.run(data, {"offline": True, "now": "2026-11-20T10:00:00", "data_dir": str(tmp_path)})
    assert out["items"] == len(data["free"]) > 0
    assert all(i["source"] == "hand" for i in data["free"])
    assert "dhc-jumeirah-park-2026-11-20" in {i["id"] for i in data["free"]}


@pytest.mark.parametrize("text, want", [("Saturday, 7:30 PM", "19:30"), ("@ 7:30pm", "19:30"), ("12 am", "00:00"),
                                        ("21:15", "21:15"), ("soon", "")])
def test_hhmm(text, want):
    assert fs._hhmm(text) == want


def test_nyuad_event_page_gives_the_real_place_and_the_free_entry():
    d = fs.nyuad_detail((FIX / "nyuad_event.html").read_text(encoding="utf-8"))
    assert d["venue"] == "Public Art Abu Dhabi Biennial Stage, Souq Al Mina"    # not the Arts Center
    assert d["price"] == 0 and d["rsvp"] is False                                # «not ticketed … first come first serve»


def test_alserkal_event_page_gives_the_start_time():
    assert fs.alserkal_detail((FIX / "alserkal_event.html").read_text(encoding="utf-8")) == {"time": "19:00"}


def test_the_hand_list_goes_into_latest_json_as_is():
    """YAML reads «checked: 2026-11-19» as a date; latest.json is JSON, so every value must already be a string."""
    json.dumps(fs.hand_items())
