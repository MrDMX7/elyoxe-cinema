"""price_history.py + steps/history.py: the daily price snapshot, its merge rule, and the bucket copy."""
import importlib.util, json, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import price_history as ph  # noqa: E402
import refresh  # noqa: E402


def load_step():
    spec = importlib.util.spec_from_file_location("steps_history_t", os.path.join(ROOT, "steps", "history.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def show(cin, film, date, time, aed, hall="Standard", **kw):
    return {"cinema": cin, "film": film, "date": date, "time": time, "hall": hall, "hall_label": "",
            "prices": [{"seat": "A", "aed": aed}, {"seat": "B", "aed": aed + 10}] if aed else None, **kw}


def data(shows, generated="2026-09-27T09:00:00+04:00"):
    return {"generated": generated,
            "cinemas": {"v1": {"chain": "vox", "city": "dubai"}, "v2": {"chain": "vox", "city": "dubai"},
                        "s1": {"chain": "star", "city": "al-ain"}},
            "films": {"a": {"title": "A"}, "b": {"title": "B"}, "old": {"title": "Old", "status": "archived"}},
            "shows": shows}


SHOWS = [show("v1", "a", "2026-09-27", "10:00", 40), show("v1", "a", "2026-09-27", "19:00", 50),
         show("v2", "a", "2026-09-27", "22:00", 60), show("v2", "b", "2026-09-27", "13:00", 90, hall="IMAX"),
         show("s1", "b", "2026-09-27", "00:30", 30), show("s1", "b", "2026-09-27", "16:00", None),
         show("s1", "b", "2026-09-27", "17:00", 99, price_source="table"),
         show("v1", "old", "2026-09-27", "18:00", 5), show("v1", "a", "2026-09-28", "18:00", 45)]


def test_snapshot_medians_per_chain_hall_city_and_uae():
    snap = ph.snapshot(data(SHOWS))
    assert sorted(snap) == ["2026-09-27", "2026-09-28"]
    d = snap["2026-09-27"]
    assert d["n"] == 7 and d["priced"] == 5            # the archived film's show is out; table + unpriced not priced
    P = {(r[0], r[1], r[2]): r[3:] for r in d["prices"]}
    assert P[("vox", "Standard", "dubai")] == [50.0, 40.0, 60.0, 3]      # cheapest seat per show
    assert P[("vox", "Standard", "")] == [50.0, 40.0, 60.0, 3]
    assert P[("vox", "IMAX", "")] == [90.0, 90.0, 90.0, 1]
    assert P[("star", "Standard", "al-ain")] == [30.0, 30.0, 30.0, 1]   # the fallback-table 99 never enters
    assert d["films"] == {"a": [3, 2], "b": [4, 2]}
    parts = {(r[0], r[1], r[2]): r[3:] for r in d["parts"]}
    assert parts[("vox", "Standard", "morning")] == [40.0, 1] and parts[("star", "Standard", "night")] == [30.0, 1]


def test_part_of_day():
    assert [ph.part_of_day(t) for t in ("04:59", "05:00", "11:59", "12:00", "17:00", "21:00", "23:59")] == \
        ["night", "morning", "morning", "afternoon", "evening", "night", "night"]


def test_merge_is_idempotent_and_keeps_the_fuller_read():
    first = ph.snapshot(data(SHOWS))
    m, ch = ph.merge({}, first)
    assert ch == ["2026-09-27", "2026-09-28"]
    assert ph.merge(m, first) == (m, [])                               # the same data twice: nothing moves
    thinner = ph.snapshot(data(SHOWS[2:]))                                 # later that day, early shows gone
    assert ph.merge(m, thinner)[1] == []
    fuller = ph.snapshot(data(SHOWS + [show("v1", "a", "2026-09-28", "20:00", 45)]))
    m2, ch2 = ph.merge(m, fuller)
    assert ch2 == ["2026-09-28"] and m2["2026-09-28"]["n"] == 2 and m2["2026-09-27"] is m["2026-09-27"]
    # more shows but fewer live prices (a chain on the fallback table) does not replace the better-priced read
    more_unpriced = ph.snapshot(data(SHOWS + [show("v2", "b", "2026-09-27", h, None) for h in ("11:00", "12:00", "14:00")]))
    assert more_unpriced["2026-09-27"]["n"] > m["2026-09-27"]["n"]
    assert ph.merge(m, {"2026-09-27": dict(more_unpriced["2026-09-27"], priced=1)})[1] == []


def test_dump_load_roundtrip_skips_torn_lines(tmp_path):
    p = str(tmp_path / "h.jsonl")
    m, _ = ph.merge({}, ph.snapshot(data(SHOWS)))
    ph.dump(m, p)
    txt = open(p, encoding="utf-8").read()
    assert txt.count("\n") == 2 and txt.index("2026-09-27") < txt.index("2026-09-28")
    open(p, "a", encoding="utf-8").write('{"date": "2026-09-29", "pri')                 # a killed write
    assert ph.load(p) == json.loads(json.dumps(m))
    assert ph.load(str(tmp_path / "none.jsonl")) == {}


def line(d, med, parts=(), films=None, n=10):
    return {"date": d, "n": n, "priced": n, "prices": [["vox", "Standard", "", med, med, med, n]],
            "parts": [["vox", "Standard", p, v, 5] for p, v in parts], "films": films or {}}


def test_series_cheapest_time_and_week():
    L = {"2026-09-01": line("2026-09-01", 40, [("morning", 30), ("night", 50)]),   # Tuesday
         "2026-09-08": line("2026-09-08", 42, [("morning", 32), ("night", 52)]),   # Tuesday again
         "2026-09-09": line("2026-09-09", 45, [("morning", 20)]),                   # one Wednesday: an anecdote
         "2026-09-10": {"date": "2026-09-10", "n": 3, "priced": 0, "prices": [], "parts": []}}
    assert ph.days(L) == ["2026-09-01", "2026-09-08", "2026-09-09"]
    assert ph.series(L, "vox") == [("2026-09-01", 40, 10), ("2026-09-08", 42, 10), ("2026-09-09", 45, 10)]
    assert ph.series(L, "vox", upto="2026-09-08")[-1][0] == "2026-09-08"
    ct = ph.cheapest_time(L, "vox")
    assert ct[0] == (1, "morning", 31.0, 10, 2) and ct[-1][:3] == (1, "night", 51.0)
    assert all(r[0] != 2 for r in ct)
    W = {"2026-09-20": line("2026-09-20", 1, films={"a": [10, 3]}), "2026-09-26": line("2026-09-26", 1, films={"a": [5, 4], "b": [7, 1]}),
         "2026-09-27": line("2026-09-27", 1, films={"b": [1, 1]})}
    tot, used = ph.week_films(W, "2026-09-26")
    assert used == ["2026-09-20", "2026-09-26"] and tot == {"a": [15, 4], "b": [7, 1]}


def test_week_over_week_and_ranked_fids():
    """/boxoffice/'s arrows: the previous span is the `span` dates immediately before the current one, and
    ranked_fids sorts exactly the way pages/insights.py's Insights.week() sorts `tot` (most shows, then most
    cinemas, then fid) so a rank computed from either side agrees."""
    W = {"2026-09-13": line("2026-09-13", 1, films={"a": [20, 3], "b": [5, 1]}),   # previous week
         "2026-09-20": line("2026-09-20", 1, films={"a": [10, 3]}),                # current week
         "2026-09-26": line("2026-09-26", 1, films={"a": [5, 4], "b": [7, 1]})}
    tot, used, prev_tot, prev_used = ph.week_over_week(W, "2026-09-26")
    assert used == ["2026-09-20", "2026-09-26"]
    assert prev_used == ["2026-09-13"]
    assert prev_tot == {"a": [20, 3], "b": [5, 1]}
    assert ph.ranked_fids(prev_tot) == ["a", "b"]           # a: 20 shows beats b's 5
    assert ph.ranked_fids(tot) == ["a", "b"]                # tied differently this week (15 vs 7), same order


# ---------------------------------------------------------------- the step
@pytest.fixture
def step(monkeypatch, tmp_path):
    """The step with a fake bucket: tmp_path/bucket.jsonl is the object (absent until written)."""
    m = load_step()
    obj = tmp_path / "bucket.jsonl"
    m.calls, m.fail_get, m.fail_put = [], False, False

    def get(path):
        m.calls.append("get")
        if m.fail_get: return "failed: AccessDenied"
        if not obj.exists(): return "absent"
        open(path, "wb").write(obj.read_bytes()); return "ok"

    def put(path):
        m.calls.append("put")
        if m.fail_put: return "failed: timeout"
        obj.write_bytes(open(path, "rb").read()); return "ok"

    m.s3_get, m.s3_put, m.obj = get, put, obj
    legacy = tmp_path / "legacy.jsonl"          # the old public copy, s3://elyoxe-cinema-…/state/ (served by the site)
    m.fail_legacy = False

    def legacy_get(path):
        m.calls.append("legacy_get")
        if m.fail_legacy: return "failed: timeout"
        if not legacy.exists(): return "absent"
        open(path, "wb").write(legacy.read_bytes()); return "ok"

    def legacy_rm():
        m.calls.append("legacy_rm")
        legacy.unlink(); return "ok"
    m.legacy_get, m.legacy_rm, m.legacy = legacy_get, legacy_rm, legacy
    monkeypatch.setenv("CINEMA_HISTORY_S3", "1")      # tmp dirs are sandboxes: force the (faked) bucket
    (tmp_path / "d").mkdir()
    m.ctx = {"data_dir": str(tmp_path / "d")}
    m.local = str(tmp_path / "d" / "price_history.jsonl")
    return m


def lines_of(d0, n):
    return {x["date"]: x for x in (line(f"2026-09-{d0 + i:02d}", 40 + i) for i in range(n))}


def test_step_first_run_starts_the_history_and_pushes_it(step):
    out = step.run(data(SHOWS), step.ctx)
    assert step.calls == ["get", "legacy_get", "put"] and out["bucket"] == "absent" and out["pushed"] == "ok" and out["new"] is True
    assert sorted(ph.load(str(step.obj))) == ["2026-09-27", "2026-09-28"] == sorted(ph.load(step.local))


def test_step_merges_the_bucket_every_run_and_never_shrinks_it(step):
    ph.dump(lines_of(1, 20), str(step.obj))              # the bucket: 20 days
    ph.dump(lines_of(1, 2), step.local)                  # a stale local file (another machine, an old copy)
    out = step.run(data(SHOWS), step.ctx)
    assert out["bucket"] == "ok" and out["days"] == 22
    assert len(ph.load(str(step.obj))) == 22 and len(ph.load(step.local)) == 22
    step.calls.clear()
    assert step.run(data(SHOWS), step.ctx)["changed"] == [] and step.calls == ["get", "legacy_get"]   # nothing new: no upload


def test_step_lost_local_file_comes_back_from_the_bucket(step):
    ph.dump(lines_of(1, 20), str(step.obj))
    out = step.run(data(SHOWS), step.ctx)
    assert out["days"] == 22 and "new" not in out


def test_step_bucket_missing_with_local_history_is_flagged_and_restored(step):
    ph.dump(lines_of(1, 20), step.local)
    out = step.run(data(SHOWS), step.ctx)
    assert out["bucket"] == "absent" and "warning" in out and out["pushed"] == "ok"
    assert len(ph.load(str(step.obj))) == 22


def test_step_failed_download_keeps_local_and_skips_the_upload(step):
    ph.dump(lines_of(1, 20), str(step.obj))
    step.fail_get = True
    with pytest.raises(RuntimeError, match="download"):
        step.run(data(SHOWS), step.ctx)
    assert step.calls == ["get"] and len(ph.load(str(step.obj))) == 20      # the bucket untouched
    assert len(ph.load(step.local)) == 2                                     # today kept locally; merged next run
    step.fail_get = False
    assert step.run(data(SHOWS), step.ctx)["days"] == 22


def test_step_failed_upload_raises(step):
    step.fail_put = True
    with pytest.raises(RuntimeError, match="upload"):
        step.run(data(SHOWS), step.ctx)
    assert len(ph.load(step.local)) == 2


def test_step_offline_and_bucket_off(step, monkeypatch):
    assert step.run(data(SHOWS), dict(step.ctx, offline=True)) == {"skipped": "offline"}
    assert not os.path.exists(step.local)
    monkeypatch.setenv("CINEMA_HISTORY_S3", "0")
    out = step.run(data(SHOWS), step.ctx)
    assert step.calls == [] and out["changed"] and "pushed" not in out


def test_bucket_only_for_the_runners_data_dir(monkeypatch, tmp_path):
    m = load_step()
    monkeypatch.delenv("CINEMA_HISTORY_S3", raising=False)
    assert m.use_bucket(os.path.join(ROOT, "data", "price_history.jsonl")) is True
    assert m.use_bucket(str(tmp_path / "price_history.jsonl")) is False     # the test suite's refresh sandboxes
    monkeypatch.setenv("CINEMA_HISTORY_S3", "0")
    assert m.use_bucket(os.path.join(ROOT, "data", "price_history.jsonl")) is False


def test_step_runs_isolated_under_refresh(tmp_path, monkeypatch):
    """refresh.run_steps loads it by file (other steps are other tasks': only this one is run here)."""
    d = tmp_path / "steps"; d.mkdir()
    real = os.path.join(ROOT, "steps", "history.py")
    (d / "history.py").write_text("import importlib.util as u" + chr(10)
                                  + f"s = u.spec_from_file_location('h', {real!r})" + chr(10)
                                  + "m = u.module_from_spec(s); s.loader.exec_module(m); run = m.run" + chr(10), encoding="utf-8")
    monkeypatch.setenv("CINEMA_HISTORY_S3", "0")
    res = refresh.run_steps(data(SHOWS), {"data_dir": str(tmp_path), "offline": False}, steps_dir=d)
    assert res["history"]["ok"] is True and res["history"]["days"] == 2
    assert os.path.exists(tmp_path / "price_history.jsonl")


def test_history_lives_where_the_site_never_serves_it():
    """cinema.elyoxe.com serves its whole bucket (OAC on elyoxe-cinema-…): the history is kept in the private
    media bucket instead, which no distribution has as an origin."""
    assert ph.BUCKET != "elyoxe-cinema-574771023173" and ph.BUCKET == "elyoxe-media-574771023173"
    assert ph.KEY == "cinema-state/price_history.jsonl"
    assert (ph.LEGACY_BUCKET, ph.LEGACY_KEY) == ("elyoxe-cinema-574771023173", "state/price_history.jsonl")


def test_step_moves_the_public_legacy_copy_then_removes_it(step):
    ph.dump(lines_of(1, 20), str(step.legacy))           # only the old public copy exists
    out = step.run(data(SHOWS), step.ctx)
    assert out["pushed"] == "ok" and out["legacy"] == "moved" and not step.legacy.exists()
    assert len(ph.load(str(step.obj))) == 22             # nothing lost in the move
    step.calls.clear()
    assert "legacy" not in step.run(data(SHOWS), step.ctx) and "legacy_rm" not in step.calls


def test_step_keeps_the_legacy_copy_when_the_new_one_is_not_safely_written(step):
    ph.dump(lines_of(1, 20), str(step.legacy))
    step.fail_put = True
    with pytest.raises(RuntimeError, match="upload"):
        step.run(data(SHOWS), step.ctx)
    assert step.legacy.exists() and "legacy_rm" not in step.calls
    step.fail_put, step.fail_legacy = False, True        # the old copy unreadable: never removed unread
    out = step.run(data(SHOWS), step.ctx)
    assert step.legacy.exists() and out["legacy"].startswith("failed") and "legacy_rm" not in step.calls


def test_step_legacy_copy_already_contained_is_removed_without_an_upload(step):
    ph.dump(lines_of(1, 20), str(step.obj))
    ph.dump(lines_of(1, 20), str(step.legacy))
    step.run(data(SHOWS), step.ctx)                       # today pushed; the legacy copy (a subset) removed
    assert not step.legacy.exists()
