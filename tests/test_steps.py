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
    assert out["b_ok"] == {"ok": True, "error": None, "n": 1}
    assert "_private" not in out


def test_missing_steps_dir_is_empty(tmp_path):
    assert refresh.run_steps({}, {}, steps_dir=tmp_path / "nope") == {}
