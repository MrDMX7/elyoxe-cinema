"""W1-P1 · seams and guards (MASTER-PLAN §5.2): the split by owner, the base [hidden] rule, the stubs, the week phase, and
the measuring tools' isolation (the exclusive server, X-Served-By, the perf lock). The slots and page-scoped CSS are in
tests/test_plugins.py, the show key in tests/test_showkey.py, the clock and the hook bus in tests/test_js.py, the
budgets' guards in tests/test_build.py. Node parts skip without node (the Fold may not have it)."""
import datetime as dt
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
from pages import core  # noqa: E402
from site_kit import Kit  # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node not installed")
SRC = Path(ROOT, "src")
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
UAE = dt.timezone(dt.timedelta(hours=4))


# ---------------------------------------------------------------- the week phase
@pytest.mark.parametrize("when,phase", [
    ("2026-09-30T17:59", "rest"), ("2026-09-30T18:00", "wed-eve"), ("2026-09-30T23:59", "wed-eve"),   # Wednesday
    ("2026-10-01T00:00", "thu-sat"), ("2026-10-02T12:00", "thu-sat"), ("2026-10-03T23:59", "thu-sat"),  # Thu, Fri, Sat
    ("2026-10-04T00:00", "rest"), ("2026-10-05T09:00", "rest"), ("2026-09-29T20:00", "rest"),          # Sun, Mon, Tue
])
def test_week_phase_in_uae_time(when, phase):
    naive = dt.datetime.fromisoformat(when)
    assert Kit.week_phase(naive) == phase
    assert Kit.week_phase(naive.replace(tzinfo=UAE)) == phase
    # the same instant read from another zone still answers in UAE time
    assert Kit.week_phase(naive.replace(tzinfo=UAE).astimezone(dt.timezone(dt.timedelta(hours=-4)))) == phase


# ---------------------------------------------------------------- the split by owner
def test_every_core_partial_exists_is_listed_once_and_the_edge_is_page_scoped():
    listed = list(core.CSS) + [n for ns in core.PAGE_CSS.values() for n in ns]
    files = sorted(p.stem for p in (SRC / "css").glob("ui-*.css"))
    assert sorted(listed) == files and len(listed) == len(set(listed))
    assert core.PAGE_CSS == {"404": ("ui-edge",)} and "ui-edge" not in core.CSS
    for stub in ("ui-paper", "ui-lights", "ui-edge"):          # W1-P2, W2-P1 and W2-P10 fill them: no rule yet
        assert build.minify_css((SRC / "css" / f"{stub}.css").read_text(encoding="utf-8")).strip() == ""
    for n in files:
        if n not in ("ui-paper", "ui-lights", "ui-edge"):
            assert build.minify_css((SRC / "css" / f"{n}.css").read_text(encoding="utf-8")).strip(), n


def test_the_base_sheet_keeps_tokens_and_base_only():
    base = (SRC / "cinema.css").read_text(encoding="utf-8")
    assert ":root{" in base and "@font-face" in base and "--gold:#E2B659" in base
    for comp in (r"\.bill\b", r"\.fhero\b", r"\.ticket\b", r"\.dock\b", r"\.rail\b", r"\.tile\b", r"\.sheet\b", r"\.tabs\b", r"\.fcity\b",
                 r"\.nr\b", r"\.matrix\b", r"\.cf\b", r"\.top\b", r"\.foot\b(?!\{position)"):
        rules = re.sub(r":not\([^)]*\)", "", re.sub(r"/\*.*?\*/", "", base, flags=re.S)).replace("main,.foot{position:relative}", "")
        assert not re.search(comp + r"[^{]*\{", rules), comp


def test_each_component_lives_in_its_owners_partial():
    """A sample of the §6.2 table: the rule a Wave 2 package will change is in the file it owns."""
    at = {"ui-chrome": [".top{", ".pill{", ".foot-l{", ".gnote{"], "ui-tabs": [".tabs{"], "ui-sheet": [".sheet{", ".opt{"],
          "ui-near": [".now{", ".nr{"], "ui-bill": [".bill{", ".bill-in{", ".bd{"], "ui-fhero": [".fhero{", ".ft{", ".trl-d{"],
          "ui-rows": [".rail{", ".strip{", "#now{"], "ui-tile": [".tile{", ".pst{"], "ui-grid": [".grid{", ".all-h{", ".ctl{"],
          "ui-film": [".dbar{", ".tabsx{", ".dy{"], "ui-sched": [".fcity{", ".cg{", ".tm{", ".tl{"], "ui-dock": [".dock{"],
          "ui-ticket": [".ticket{", ".tk-act{", ".tkcol{"], "ui-places": [".split{", ".cf{", ".srow{", ".clist{"],
          "ui-money": [".matrix{", ".crd{", ".chains{", ".links{", ".more{"]}
    for f, rules in at.items():
        css = (SRC / "css" / f"{f}.css").read_text(encoding="utf-8")
        for r in rules:
            assert r in css, (f, r)


def test_hidden_means_hidden_one_rule_no_patches(tmp_path):
    base = (SRC / "cinema.css").read_text(encoding="utf-8")
    assert ":where([hidden]:not([data-hold])),:where(:root:not(.js) [hidden]){display:none!important}" in base
    for f in [SRC / "cinema.css", *sorted((SRC / "css").glob("ui-*.css"))]:
        css = re.sub(r"/\*.*?\*/", "", f.read_text(encoding="utf-8"), flags=re.S)
        patches = re.findall(r"[^{}\n]*\[hidden\][^{}]*\{display:none\}", css)
        assert not patches, (f.name, patches)
    out = str(tmp_path / "o")
    build.build(DATA, DISC, out, noindex=False, modules=build.discover(only=("core",)))
    home = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    held = re.findall(r"<[^>]*\bdata-hold\b[^>]*>", home)
    assert len(held) == 1 and 'id="now" data-near-row data-hold hidden' in held[0]
    city = open(os.path.join(out, "dubai", "index.html"), encoding="utf-8").read()
    assert '<a class="now" href="#all" data-now data-hold hidden>' in city
    # each held slot keeps a «.js …[hidden]» rule that lays it out invisible
    css = open(os.path.join(out, "assets", "cinema.css"), encoding="utf-8").read()
    assert ".js .now[data-now][hidden]{display:flex;visibility:hidden}" in css and ".js .rail[data-near-row][hidden]{display:block;visibility:hidden}" in css


def test_the_wave2_stubs_are_declared_and_cost_nothing():
    js = list(core.JS)
    assert js[-3:] == ["chrome", "places", "main"] and core.LAZY_JS == ("drag",)
    for f in ("chrome.js", "places.js", "drag.js"):
        assert build.minify_lite((SRC / "js" / f).read_text(encoding="utf-8")).strip() == "", f
    without = types.SimpleNamespace(__name__="pages.core", JS=tuple(n for n in core.JS if n not in ("chrome", "places")))
    mods = build.discover()
    assert build.bundle_js(modules=[without] + mods[1:]) == build.bundle_js(modules=mods)   # not one byte in the bundle


def test_docs_name_every_seam():
    d = Path(ROOT, "docs", "PLUGINS.md").read_text(encoding="utf-8")
    for s in ("head.inline", "home.after_bill", "home.after_board", "film.first", "cinema.top", "city.hero", "notfound.body",
              "offline.body", "ticket.actions", "sources.body", "PAGE_CSS", "pages/_core/", "kit/filters.py", "Kit.show_key",
              "Kit.week_phase", "on(ev, fn)", "emit(ev, x)", "`minute`", "BudgetError", "data-hold", "tools/serve.py", "perf_lock"):
        assert s in d, s


# ---------------------------------------------------------------- byte identity (tools/out_hash.py)
def test_out_hash_sees_the_same_build_as_the_same_and_names_a_change(tmp_path):
    mk = lambda name: subprocess.run([sys.executable, os.path.join(ROOT, "tools", "out_hash.py"), "build", "--out", str(tmp_path / name),
                                      "--manifest", str(tmp_path / (name + ".json")), "--data", DATA, "--discounts", DISC],
                                     capture_output=True, text=True, timeout=600)
    assert mk("a").returncode == 0 and mk("b").returncode == 0
    cmp = lambda *x: subprocess.run([sys.executable, os.path.join(ROOT, "tools", "out_hash.py"), "compare", *x], capture_output=True, text=True, timeout=60)
    r = cmp(str(tmp_path / "a.json"), str(tmp_path / "b.json"))
    assert r.returncode == 0 and "identical" in r.stdout, r.stdout + r.stderr
    m = json.load(open(tmp_path / "b.json", encoding="utf-8"))
    m["files"]["index.html"][0] = m["files"]["index.html"][1] = "0" * 64
    json.dump(m, open(tmp_path / "c.json", "w", encoding="utf-8"))
    r = cmp(str(tmp_path / "a.json"), str(tmp_path / "c.json"))
    assert r.returncode == 1 and "DIFF index.html" in r.stdout


# ---------------------------------------------------------------- measuring in isolation (MASTER-PLAN §5.0 #6)
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def start_server(out, port, name):
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "serve.py"), "--out", out, "--port", str(port), "--name", name, "--no-proxy"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = p.stdout.readline()
    return p, line


def test_the_server_binds_its_port_alone_and_stamps_every_answer(tmp_path):
    out = tmp_path / "o"; out.mkdir(); (out / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    (out / "assets").mkdir(); (out / "assets" / "cinema.css").write_text("p{}", encoding="utf-8")
    port = free_port()
    a, line = start_server(str(out), port, "w1-test")
    try:
        assert "serving" in line and "as w1-test-" in line
        stamp = line.strip().rsplit(" ", 1)[1]
        import urllib.request
        for u in ("/", "/assets/cinema.css", "/missing"):
            try:
                r = urllib.request.urlopen(f"http://127.0.0.1:{port}{u}", timeout=10); h = r.headers
            except urllib.error.HTTPError as e:
                h = e.headers
            assert h["X-Served-By"] == stamp, u
        # a second server on the same port does not share it: it refuses to start (exit 3)
        b = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "serve.py"), "--out", str(out), "--port", str(port), "--name", "intruder"],
                           capture_output=True, text=True, timeout=30)
        assert b.returncode == 3 and "taken" in b.stderr
    finally:
        a.kill(); a.wait()


@needs_node
def test_a_check_pointed_at_another_server_stops_on_x_served_by(tmp_path):
    out = tmp_path / "o"; out.mkdir(); (out / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    (out / "assets").mkdir(); (out / "assets" / "cinema.css").write_text("p{}", encoding="utf-8")
    port = free_port()
    srv, line = start_server(str(out), port, "some-other-package")
    try:
        js = (f"require({json.dumps(os.path.join(ROOT, 'tools', 'pw_kit.cjs'))}).assertServed('http://127.0.0.1:{port}', 'w1-p1-abc1234')"
              ".then(() => { console.log('MEASURED'); }, (e) => { console.log(e.message); process.exit(1); });")
        r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=60)
        assert r.returncode == 1 and "X-Served-By" in r.stdout and "some-other-package" in r.stdout and "MEASURED" not in r.stdout
        good = line.strip().rsplit(" ", 1)[1]
        js2 = js.replace("w1-p1-abc1234", good)
        assert subprocess.run([NODE, "-e", js2], capture_output=True, text=True, timeout=60).stdout.strip() == "MEASURED"
    finally:
        srv.kill(); srv.wait()


@needs_node
def test_two_perf_runs_started_together_take_turns(tmp_path):
    """The second waits for the lock the first holds (a mkdir lock with the owner's package and pid), then runs."""
    env = dict(os.environ, CINEMA_PERF_LOCK=str(tmp_path / "perf.lock"))
    lock = os.path.join(ROOT, "tools", "perf_lock.cjs")
    hold = [NODE, lock, "run", "--pkg", "first", "--", NODE, "-e", "setTimeout(() => {}, 4000)"]
    second = [NODE, lock, "run", "--pkg", "second", "--", NODE, "-e", "console.log('second ran')"]
    a = subprocess.Popen(hold, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    t0 = time.time()
    while not (tmp_path / "perf.lock" / "owner.json").exists() and time.time() - t0 < 20: time.sleep(0.05)
    owner = json.loads((tmp_path / "perf.lock" / "owner.json").read_text(encoding="utf-8"))
    assert owner["pkg"] == "first" and owner["pid"]
    b = subprocess.run(second, env=env, capture_output=True, text=True, timeout=60)
    a.wait(timeout=30)
    assert b.returncode == 0 and "second ran" in b.stdout
    assert "waiting for first" in b.stderr and time.time() - t0 >= 3
    waited = float(re.search(r"waited ([\d.]+) s", b.stderr).group(1))
    assert waited >= 2.0, b.stderr
    assert not (tmp_path / "perf.lock").exists()            # released when the run ended


@needs_node
def test_a_stale_lock_is_taken_over(tmp_path):
    """Older than 20 minutes and its process gone: stale, taken over; never a live one."""
    lockdir = tmp_path / "perf.lock"; lockdir.mkdir()
    (lockdir / "owner.json").write_text(json.dumps({"pkg": "gone", "pid": 999999, "at": "2026-01-01T00:00:00Z"}), encoding="utf-8")
    env = dict(os.environ, CINEMA_PERF_LOCK=str(lockdir))
    r = subprocess.run([NODE, os.path.join(ROOT, "tools", "perf_lock.cjs"), "run", "--pkg", "next", "--", NODE, "-e", "console.log('ran')"],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "ran" in r.stdout and "stale" in r.stderr
