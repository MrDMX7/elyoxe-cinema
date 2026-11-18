"""steps/last_chance.py (owner 2026-11-18, the spec's third signal): «آخر فرصة» is a film seen for 14+ days whose
shows today and tomorrow are down to a quarter of its peak day in the last 28 — never «no show after tomorrow», which
the two-day read makes true of every film (the rule switched off on 2026-09-28)."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = "2026-11-18T12:00:00+04:00"
TODAY, TOMORROW = "2026-11-18", "2026-11-19"


def _load():
    spec = importlib.util.spec_from_file_location("steps.last_chance", ROOT / "steps" / "last_chance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _world(tmp_path, peaks, first_seen="2026-10-01"):
    """peaks: {fid: shows on 2026-11-08}; every film also has 2026-11-12 at a third of that."""
    (tmp_path / "film_history.json").write_text(json.dumps({f: {"first_seen": first_seen} for f in peaks}), encoding="utf-8")
    lines = [{"date": "2026-11-08", "films": {f: [n, 10] for f, n in peaks.items()}},
             {"date": "2026-11-12", "films": {f: [n // 3, 5] for f, n in peaks.items()}},
             {"date": "2026-09-01", "films": {f: [999, 40] for f in peaks}}]          # older than the 28-day window
    (tmp_path / "price_history.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")


def _data(per_film):
    """per_film: {fid: (shows today in dubai, shows tomorrow in abu dhabi)}"""
    shows = []
    for fid, (a, b) in per_film.items():
        shows += [{"film": fid, "cinema": "vox-x", "date": TODAY}] * a + [{"film": fid, "cinema": "vox-y", "date": TOMORROW}] * b
    return {"cinemas": {"vox-x": {"city": "dubai"}, "vox-y": {"city": "abu-dhabi"}}, "shows": shows}


def test_a_film_down_to_a_quarter_of_its_peak_is_flagged_with_its_numbers(tmp_path):
    _world(tmp_path, {"fading": 120, "steady": 120})
    data = _data({"fading": (12, 9), "steady": (70, 60)})
    out = _load().run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance"] == {"dubai": ["fading"], "abu-dhabi": ["fading"]}
    assert data["last_chance_info"] == {"fading": {"peak": 120, "peak_date": "2026-11-08", "now": 12}}
    assert out == {"films": 1, "cities": {"dubai": 1, "abu-dhabi": 1}}


def test_a_film_that_never_played_big_or_is_new_is_not_flagged(tmp_path):
    _world(tmp_path, {"small": 12})
    data = _data({"small": (2, 1)})
    _load().run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance_info"] == {}                       # a peak under 20 shows a day: never arrived big
    _world(tmp_path, {"new": 120}, first_seen="2026-11-10")
    data = _data({"new": (10, 10)})
    _load().run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance_info"] == {}                       # seen 8 days: not on its way out


def test_the_peak_is_from_the_last_28_days_and_the_history_line_for_today_counts(tmp_path):
    _world(tmp_path, {"f": 60})
    lines = (tmp_path / "price_history.jsonl").read_text(encoding="utf-8")
    (tmp_path / "price_history.jsonl").write_text(lines + "\n" + json.dumps({"date": TODAY, "films": {"f": [40, 8]}}),
                                                  encoding="utf-8")
    data = _data({"f": (5, 0)})                                  # this run sees 5 (the day's early shows are gone)
    _load().run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance_info"] == {}                       # the history's full read of today: 40, not 5


def test_no_history_flags_nothing_and_a_stale_list_never_survives(tmp_path):
    data = _data({"f": (1, 1)})
    data["last_chance"] = {"dubai": ["stale"]}
    out = _load().run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert data["last_chance"] == {} and data["last_chance_info"] == {} and out["films"] == 0


def test_the_real_steps_run_is_ok_on_the_sample(tmp_path):
    import refresh
    data = json.loads((ROOT / "fixtures" / "sample_latest.json").read_text(encoding="utf-8"))
    out = refresh.run_steps(data, {"offline": True, "now": data["generated"], "data_dir": str(tmp_path)})
    assert out["last_chance"]["ok"] is True and data["last_chance"] == {}


def test_a_film_still_playing_wide_is_not_flagged_even_after_a_big_drop(tmp_path):
    """Godzilla Minus Zero on the first live run: 329 shows at its peak, 76 a day now — a quarter, but still everywhere."""
    _world(tmp_path, {"wide": 329, "leaving": 250})
    data = _data({"wide": (76, 40), "leaving": (1, 1)})
    _load().run(data, {"data_dir": str(tmp_path), "now": NOW})
    assert set(data["last_chance_info"]) == {"leaving"}
