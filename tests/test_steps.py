"""refresh.run_steps: discovers steps/*.py in name order, isolates failures."""
import refresh


def test_steps_run_in_order_and_failures_are_isolated(tmp_path):
    (tmp_path / "b_ok.py").write_text("def run(data, ctx):\n    data['seen'].append('b')\n    return {'n': 1}\n")
    (tmp_path / "a_boom.py").write_text("def run(data, ctx):\n    data['seen'].append('a')\n    raise ValueError('x')\n")
    (tmp_path / "_private.py").write_text("raise SystemExit('never imported')\n")
    data = {"seen": []}
    out = refresh.run_steps(data, {}, steps_dir=tmp_path)
    assert data["seen"] == ["a", "b"]
    assert out["a_boom"]["ok"] is False and "ValueError" in out["a_boom"]["error"]
    assert {k: v for k, v in out["b_ok"].items() if k != "sec"} == {"ok": True, "error": None, "n": 1}
    assert all(isinstance(r["sec"], float) and r["sec"] >= 0 for r in out.values())   # health shows each step's cost
    assert "_private" not in out


def test_missing_steps_dir_is_empty(tmp_path):
    assert refresh.run_steps({}, {}, steps_dir=tmp_path / "nope") == {}


def test_every_real_step_honours_offline(tmp_path):
    """--offline (and every orchestration test) runs the real steps/: none may reach the network (conftest's
    guard fails the test on any attempt, even a swallowed one) and together they stay quick."""
    import json
    import os
    import time

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = json.load(open(os.path.join(root, "fixtures", "sample_latest.json"), encoding="utf-8"))
    t0 = time.monotonic()
    out = refresh.run_steps(data, {"offline": True, "now": data["generated"], "data_dir": str(tmp_path)})
    assert set(out) >= {"coming", "events", "history", "last_chance", "occupancy", "people"}
    assert all(r["ok"] for r in out.values()), {n: r["error"] for n, r in out.items() if not r["ok"]}
    assert time.monotonic() - t0 < 10
    assert not (tmp_path / "price_history.jsonl").exists()          # fixture prices never enter the history
