"""steps/occupancy_history.py: folding, trimming, and best_time()'s thresholds."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import steps.occupancy_history as oh  # noqa: E402


def test_best_time_none_below_min_days():
    entry = {"days": [f"2026-09-0{i}" for i in range(1, 6)],  # 5 days, below MIN_DAYS=7
             "parts": {"morning": {"n": 20, "sum": 2.0}}}
    assert oh.best_time(entry) is None


def test_best_time_none_below_min_samples():
    entry = {"days": [f"2026-09-{i:02d}" for i in range(1, 9)],  # 8 days
             "parts": {"morning": {"n": 5, "sum": 0.5}}}          # 5 samples, below MIN_SAMPLES=12
    assert oh.best_time(entry) is None


def test_best_time_picks_lowest_average_with_enough_days_and_samples():
    entry = {"days": [f"2026-09-{i:02d}" for i in range(1, 9)],
             "parts": {"morning": {"n": 5, "sum": 1.0},        # avg .2, but below MIN_PART_SAMPLES=3? no, 5>=3
                       "night": {"n": 8, "sum": 6.4}}}          # avg .8
    bt = oh.best_time(entry)
    assert bt == {"part": "morning", "occ": 0.2}


def test_best_time_ignores_part_with_too_few_samples_even_if_lowest():
    entry = {"days": [f"2026-09-{i:02d}" for i in range(1, 9)],
             "parts": {"morning": {"n": 2, "sum": 0.02}},          # only 2 samples: below MIN_PART_SAMPLES
             "evening": {"n": 10, "sum": 5.0}}
    entry["parts"]["evening"] = {"n": 10, "sum": 5.0}
    bt = oh.best_time(entry)
    assert bt == {"part": "evening", "occ": 0.5}


def test_best_time_tie_keeps_earlier_part_order():
    entry = {"days": [f"2026-09-{i:02d}" for i in range(1, 9)],
             "parts": {"night": {"n": 6, "sum": 3.0}, "morning": {"n": 6, "sum": 3.0}}}
    assert oh.best_time(entry)["part"] == "morning"


# -------- run(): folding + attaching + trimming

def _show(cid, date, time, free, total):
    return {"cinema": cid, "date": date, "time": time, "film": "f1", "hall_label": "Standard",
            "seats": {"free": free, "total": total}}


def test_run_folds_samples_and_attaches_when_enough_history(tmp_path):
    hist = {"c1": {"days": [f"2026-09-{i:02d}" for i in range(1, 8)],
                   "parts": {"morning": {"n": 12, "sum": 1.2}}}}
    (tmp_path / "occupancy_history.json").write_text(json.dumps(hist))
    data = {"cinemas": {"c1": {}}, "shows": [_show("c1", "2026-09-08", "09:00", 90, 100)]}  # morning, occ .1
    out = oh.run(data, {"now": "2026-09-08T10:00:00+04:00", "data_dir": str(tmp_path)})
    assert data["cinemas"]["c1"]["best_time"] == {"part": "morning", "occ": round((1.2 + 0.1) / 13, 4)}
    assert out["attached"] == 1


def test_run_ignores_shows_without_seats(tmp_path):
    data = {"cinemas": {"c1": {}}, "shows": [{"cinema": "c1", "date": "2026-09-08", "time": "09:00"}]}
    out = oh.run(data, {"now": "2026-09-08T10:00:00+04:00", "data_dir": str(tmp_path)})
    assert out["folded"] == 0
    assert "best_time" not in data["cinemas"]["c1"]


def test_run_trims_history_older_than_hist_days(tmp_path, monkeypatch):
    monkeypatch.setattr(oh, "HIST_DAYS", 10)
    hist = {"c1": {"days": ["2026-01-01", "2026-09-05"], "parts": {"morning": {"n": 1, "sum": 0.1}}}}
    (tmp_path / "occupancy_history.json").write_text(json.dumps(hist))
    data = {"cinemas": {}, "shows": []}
    oh.run(data, {"now": "2026-09-08T10:00:00+04:00", "data_dir": str(tmp_path)})
    saved = json.loads((tmp_path / "occupancy_history.json").read_text())
    assert saved["c1"]["days"] == ["2026-09-05"]


def test_run_never_raises_on_malformed_history(tmp_path):
    (tmp_path / "occupancy_history.json").write_text("not json at all")
    data = {"cinemas": {"c1": {}}, "shows": [_show("c1", "2026-09-08", "09:00", 90, 100)]}
    out = oh.run(data, {"now": "2026-09-08T10:00:00+04:00", "data_dir": str(tmp_path)})
    assert out["folded"] == 1


def _show_at(cid, date, time, free, total, at):
    s = _show(cid, date, time, free, total)
    s["seats"]["at"] = at
    return s


def test_run_does_not_refold_the_same_sample_within_freshness_window(tmp_path):
    """occupancy.py keeps a fresh sample attached for up to 90 min: a manual re-run inside that
    window must not fold the exact same seats reading a second time (double-weighting one show)."""
    data = {"cinemas": {"c1": {}},
            "shows": [_show_at("c1", "2026-09-08", "09:00", 90, 100, "2026-09-08T08:50:00+04:00")]}
    out1 = oh.run(data, {"now": "2026-09-08T09:00:00+04:00", "data_dir": str(tmp_path)})
    assert out1["folded"] == 1
    data2 = {"cinemas": {"c1": {}},
             "shows": [_show_at("c1", "2026-09-08", "09:00", 90, 100, "2026-09-08T08:50:00+04:00")]}
    out2 = oh.run(data2, {"now": "2026-09-08T09:20:00+04:00", "data_dir": str(tmp_path)})
    assert out2["folded"] == 0
    saved = json.loads((tmp_path / "occupancy_history.json").read_text())
    assert saved["c1"]["parts"]["morning"]["n"] == 1


def test_run_folds_a_genuinely_new_sample_for_the_same_show(tmp_path):
    data = {"cinemas": {"c1": {}},
            "shows": [_show_at("c1", "2026-09-08", "09:00", 90, 100, "2026-09-08T08:50:00+04:00")]}
    oh.run(data, {"now": "2026-09-08T09:00:00+04:00", "data_dir": str(tmp_path)})
    data2 = {"cinemas": {"c1": {}},
             "shows": [_show_at("c1", "2026-09-08", "09:00", 85, 100, "2026-09-08T08:55:00+04:00")]}
    out2 = oh.run(data2, {"now": "2026-09-08T09:05:00+04:00", "data_dir": str(tmp_path)})
    assert out2["folded"] == 1
    saved = json.loads((tmp_path / "occupancy_history.json").read_text())
    assert saved["c1"]["parts"]["morning"]["n"] == 2
