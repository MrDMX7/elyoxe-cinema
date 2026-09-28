"""steps/last_chance.py: a film qualifies in a city only with >=14 days seen and no show dated
after tomorrow there (Task 2, design spec A). The step ships switched off (W0-P2, MASTER-PLAN §4.1 #13):
the rule's tests run it with ENABLED set, the last two check that the default writes nothing."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = "2026-09-27T12:00:00+04:00"
TODAY, TOMORROW = "2026-09-27", "2026-09-28"


def _load(enabled=False):
    spec = importlib.util.spec_from_file_location("steps.last_chance", ROOT / "steps" / "last_chance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if enabled:
        mod.ENABLED = True   # the rule itself, as it would run once a real signal turns it back on
    return mod


def _data(shows):
    return {"cinemas": {"vox-x": {"city": "dubai"}, "vox-y": {"city": "abu-dhabi"}}, "shows": shows}


def test_qualifies_when_seen_long_enough_and_only_today_tomorrow(tmp_path):
    mod = _load(enabled=True)
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
    mod = _load(enabled=True)
    data = _data([
        {"film": "long-runner", "cinema": "vox-x", "date": TODAY},
        {"film": "long-runner", "cinema": "vox-x", "date": "2026-09-30"},  # still running past tomorrow
    ])
    out = mod.run(data, {"data_dir": "/nonexistent", "now": NOW})
    assert data["last_chance"] == {}
    assert out["cities"] == {}


def test_excluded_when_not_seen_long_enough(tmp_path):
    mod = _load(enabled=True)
    history = {"new-film": {"first_seen": "2026-09-20"}}  # only 7 days
    (tmp_path / "film_history.json").write_text(json.dumps(history), encoding="utf-8")
    data = _data([{"film": "new-film", "cinema": "vox-x", "date": TODAY}])
    out = mod.run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance"] == {}


def test_per_city_independent(tmp_path):
    mod = _load(enabled=True)
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
    mod = _load(enabled=True)
    data = _data([{"film": "x", "cinema": "vox-x", "date": TODAY}])
    out = mod.run(data, {"data_dir": str(tmp_path), "now": NOW})  # no film_history.json written
    assert data["last_chance"] == {} and out["cities"] == {}


def test_switched_off_by_default_writes_no_film_even_for_a_qualifier(tmp_path):
    """With a two-day read "no show after tomorrow" is always true: the shipped step flags nothing."""
    mod = _load()
    assert mod.ENABLED is False
    (tmp_path / "film_history.json").write_text(json.dumps({"old-film": {"first_seen": "2026-09-01"}}), encoding="utf-8")
    data = _data([{"film": "old-film", "cinema": "vox-x", "date": TODAY}])
    data["last_chance"] = {"dubai": ["stale-film"]}   # a previous run's list never survives
    out = mod.run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance"] == {} and out["cities"] == {}
    assert mod.qualify(data, {"data_dir": str(tmp_path), "now": NOW}) == {"dubai": ["old-film"]}   # the rule is intact


def test_the_real_steps_run_leaves_last_chance_empty(tmp_path):
    import refresh
    data = json.loads((ROOT / "fixtures" / "sample_latest.json").read_text(encoding="utf-8"))
    (tmp_path / "film_history.json").write_text(json.dumps({f: {"first_seen": "2026-01-01"} for f in data["films"]}), encoding="utf-8")
    out = refresh.run_steps(data, {"offline": True, "now": data["generated"], "data_dir": str(tmp_path)})
    assert out["last_chance"]["ok"] is True and data["last_chance"] == {}
