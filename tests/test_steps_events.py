"""steps/events.py: recovers chain-labelled events from raw title text (Task 2 fix round 1,
review Critical finding)."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("steps.events", ROOT / "steps" / "events.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_raw(tmp_path, chain, cinemas, shows):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / f"{chain}.json").write_text(json.dumps({"cinemas": cinemas, "shows": shows}), encoding="utf-8")


def test_candidates_extracts_bracket_paren_and_prefix():
    mod = _load()
    assert mod._candidates("Exhuma (K-Fest)") == ["K-Fest"]
    assert mod._candidates("Revolver [K-Fest]") == ["K-Fest"]
    assert mod._candidates("Immersive Dining - IV Elements of Hoshena") == ["Immersive Dining"]
    assert mod._candidates("Avengers Endgame: Encore (Infinity Vision)") == ["Infinity Vision"]
    assert mod._candidates("Shish Dou [Arabic]") == ["Arabic"]   # a candidate -- filtering happens by lookup


def test_recovers_k_fest_label_lost_by_normalize_clean_title(tmp_path):
    mod = _load()
    _write_raw(tmp_path, "roxy",
               [{"id": "roxy-dubai-hills-mall", "city": "dubai"}],
               [{"film_title": "Exhuma (K-Fest)", "cinema": "roxy-dubai-hills-mall"},
                {"film_title": "Revolver [K-Fest]", "cinema": "roxy-dubai-hills-mall"}])
    data = {}
    out = mod.run(data, {"data_dir": str(tmp_path)})
    assert out["labels"] == 1
    ev = data["events"][0]
    assert ev["label"] == "k-fest" and ev["name_en"] == "K-Fest"
    assert ev["fids"] == ["exhuma", "revolver"]     # normalize.film_fid on the raw title -- matches data["films"]
    assert ev["chains"] == ["roxy"]
    assert ev["cities"] == ["dubai"]


def test_unrecognised_bracket_text_is_ignored_not_invented(tmp_path):
    mod = _load()
    _write_raw(tmp_path, "roxy",
               [{"id": "roxy-x", "city": "dubai"}],
               [{"film_title": "Shish Dou [Arabic]", "cinema": "roxy-x"},
                {"film_title": "Avengers Endgame: Encore (Infinity Vision)", "cinema": "roxy-x"}])
    data = {}
    out = mod.run(data, {"data_dir": str(tmp_path)})
    assert out["labels"] == 0
    assert data["events"] == []


def test_immersive_dining_prefix_across_a_different_chain(tmp_path):
    mod = _load()
    _write_raw(tmp_path, "roxy",
               [{"id": "roxy-y", "city": "abu-dhabi"}],
               [{"film_title": "Immersive Dining - IV Elements of Hoshena", "cinema": "roxy-y"}])
    data = {}
    out = mod.run(data, {"data_dir": str(tmp_path)})
    assert out["labels"] == 1
    ev = data["events"][0]
    assert ev["label"] == "immersive dining"
    assert ev["fids"] == ["immersive-dining-iv-elements-of-hoshena"]
    assert ev["cities"] == ["abu-dhabi"]


def test_same_label_across_two_chains_merges_into_one_entry(tmp_path):
    mod = _load()
    _write_raw(tmp_path, "roxy", [{"id": "roxy-x", "city": "dubai"}],
               [{"film_title": "Exhuma (K-Fest)", "cinema": "roxy-x"}])
    _write_raw(tmp_path, "star", [{"id": "star-y", "city": "sharjah"}],
               [{"film_title": "Exhuma (K-Fest)", "cinema": "star-y"}])
    data = {}
    out = mod.run(data, {"data_dir": str(tmp_path)})
    assert out["labels"] == 1
    ev = data["events"][0]
    assert ev["fids"] == ["exhuma"]
    assert sorted(ev["chains"]) == ["roxy", "star"]
    assert sorted(ev["cities"]) == ["dubai", "sharjah"]


def test_no_raw_dir_yields_no_events(tmp_path):
    mod = _load()
    out = mod.run({}, {"data_dir": str(tmp_path / "nope")})
    assert out["labels"] == 0


def test_missing_or_unreadable_events_yaml_yields_no_labels(tmp_path):
    mod = _load()
    assert mod._load_labels(tmp_path / "missing-events.yaml") == {}


def test_run_marker_file_in_raw_dir_is_not_treated_as_a_chain(tmp_path):
    mod = _load()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / ".run.json").write_text('{"id": "x"}', encoding="utf-8")
    data = {}
    out = mod.run(data, {"data_dir": str(tmp_path)})
    assert out["labels"] == 0 and data["events"] == []
