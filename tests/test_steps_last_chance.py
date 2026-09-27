"""steps/last_chance.py: a film qualifies in a city only with >=14 days seen and no show dated
after tomorrow there (Task 2, design spec A)."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = "2026-09-27T12:00:00+04:00"
TODAY, TOMORROW = "2026-09-27", "2026-09-28"


def _load():
    spec = importlib.util.spec_from_file_location("steps.last_chance", ROOT / "steps" / "last_chance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _data(shows):
    return {"cinemas": {"vox-x": {"city": "dubai"}, "vox-y": {"city": "abu-dhabi"}}, "shows": shows}


def test_qualifies_when_seen_long_enough_and_only_today_tomorrow(tmp_path):
    mod = _load()
    history = {"old-film": {"first_seen": "2026-09-01"}}  # 26 days by 2026-09-27 -- well past 14
    (tmp_path / "film_history.json").write_text(json.dumps(history), encoding="utf-8")
    data = _data([
        {"film": "old-film", "cinema": "vox-x", "date": TODAY},
        {"film": "old-film", "cinema": "vox-x", "date": TOMORROW},
    ])
    out = mod.run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance"] == {"dubai": ["old-film"]}
    assert out["cities"] == {"dubai": 1}


def test_excluded_when_a_show_exists_beyond_tomorrow():
    mod = _load()
    data = _data([
        {"film": "long-runner", "cinema": "vox-x", "date": TODAY},
        {"film": "long-runner", "cinema": "vox-x", "date": "2026-09-30"},  # still running past tomorrow
    ])
    out = mod.run(data, {"data_dir": "/nonexistent", "now": NOW})
    assert data["last_chance"] == {}
    assert out["cities"] == {}


def test_excluded_when_not_seen_long_enough(tmp_path):
    mod = _load()
    history = {"new-film": {"first_seen": "2026-09-20"}}  # only 7 days
    (tmp_path / "film_history.json").write_text(json.dumps(history), encoding="utf-8")
    data = _data([{"film": "new-film", "cinema": "vox-x", "date": TODAY}])
    out = mod.run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance"] == {}


def test_per_city_independent(tmp_path):
    mod = _load()
    history = {"film-a": {"first_seen": "2026-09-01"}}
    (tmp_path / "film_history.json").write_text(json.dumps(history), encoding="utf-8")
    data = _data([
        {"film": "film-a", "cinema": "vox-x", "date": TODAY},                # dubai: last chance
        {"film": "film-a", "cinema": "vox-y", "date": "2026-10-05"},         # abu-dhabi: still running
    ])
    out = mod.run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance"] == {"dubai": ["film-a"]}
    assert "abu-dhabi" not in data["last_chance"]


def test_missing_or_corrupt_film_history_yields_no_last_chance(tmp_path):
    mod = _load()
    data = _data([{"film": "x", "cinema": "vox-x", "date": TODAY}])
    out = mod.run(data, {"data_dir": str(tmp_path), "now": NOW})  # no film_history.json written
    assert data["last_chance"] == {} and out["cities"] == {}
