"""The privacy counter's client is wired (2026-10-17): counter.yaml's endpoint lands in beacon.js and push.js at
bundle time, the beacon chunk loads on every page, and the laptop's run.sh can reach the owner by mail."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "tests", "fixtures", "coming_sample.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
MODULES = build.discover(only=("core", "coming", "beacon", "vote", "voteadd"))


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def _build(tmp_path):
    o = str(tmp_path / "out")
    build.build(DATA, DISC, o, modules=MODULES)
    return o


def test_counter_config_reads_counter_yaml_and_tolerates_a_missing_file(tmp_path):
    cfg = build.counter_config()
    assert cfg["__COUNTER_API__"].startswith("https://") and cfg["__COUNTER_API__"].endswith("/")
    assert len(cfg["__VAPID_PUBLIC_KEY__"]) > 40
    empty = build.counter_config(str(tmp_path / "none.yaml"))
    assert empty == {"__COUNTER_API__": "", "__VAPID_PUBLIC_KEY__": ""}


def test_fill_counter_replaces_both_placeholders():
    js = 'var API = "__COUNTER_API__"; var V = "__VAPID_PUBLIC_KEY__";'
    out = build.fill_counter(js, {"__COUNTER_API__": "https://x/", "__VAPID_PUBLIC_KEY__": "K"})
    assert out == 'var API = "https://x/"; var V = "K";'


def test_beacon_chunk_is_filled_and_loads_on_every_page(tmp_path):
    o = _build(tmp_path)
    api = build.counter_config()["__COUNTER_API__"]
    for page in (("index.html",), ("coming", "index.html"), ("en", "index.html")):
        html = read(o, *page)
        m = re.search(r'/assets/beacon\.[0-9a-f]{10}\.js', html)
        assert m, page
    chunk = read(o, *m.group(0).lstrip("/").split("/"))
    assert api in chunk and "__COUNTER_API__" not in chunk
    assert "sendBeacon" in chunk and '"view"' in chunk and '"book_click"' in chunk and '"return"' in chunk
    home = read(o, "index.html")
    main = re.search(r'/assets/cinema\.[0-9a-f]{10}\.js', home).group(0)
    js = read(o, *main.lstrip("/").split("/"))
    assert "sendBeacon" not in js   # a lazy chunk, never the shared bundle


def test_push_chunk_carries_the_real_endpoint_and_vapid_key(tmp_path):
    o = _build(tmp_path)
    coming = read(o, "coming", "index.html")
    chunk = re.search(r'/assets/push\.[0-9a-f]+\.js', coming).group(0)
    js = read(o, *chunk.lstrip("/").split("/"))
    cfg = build.counter_config()
    assert cfg["__COUNTER_API__"] in js and cfg["__VAPID_PUBLIC_KEY__"] in js
    assert "__COUNTER_API__" not in js and "__VAPID_PUBLIC_KEY__" not in js


def test_run_sh_mails_the_owner_when_the_phone_notifier_is_absent():
    code = open(os.path.join(ROOT, "run.sh"), encoding="utf-8").read()
    body = re.search(r"\nnote\(\) \{\n(.*?)\n\}", code, re.S).group(1)
    assert "tools/notify_mail.py" in body
    assert 'declare -F notify' in body                       # the Fold's road still comes first
    assert '[ -z "${CINEMA_ENV_SH:-}" ]' in body             # never under the test sandbox (it always sets it)
    assert 'notify (unavailable)' in body                    # the last fallback is still the log line the tests read
    assert os.path.exists(os.path.join(ROOT, "tools", "notify_mail.py"))


def test_watchdog_workflow_fails_on_a_stale_site():
    wf = open(os.path.join(ROOT, ".github", "workflows", "watchdog.yml"), encoding="utf-8").read()
    assert "schedule:" in wf and "cinema.elyoxe.com" in wf and "25200" in wf and "exit 1" in wf


def test_a_late_geo_answer_reorders_the_page_inside_a_view_transition():
    """geo.js (2026-10-17): the network's city arrives after first paint; moving the visitor's city first then shifted a
    whole schedule (CLS 0.27). The reorder runs inside document.startViewTransition where it exists (reduced motion
    and older browsers: the plain call)."""
    js = open(os.path.join(ROOT, "src", "js", "geo.js"), encoding="utf-8").read()
    body = js[js.index("function geoApply"):js.index("function geoNote")]
    assert "document.startViewTransition(function () { pickCity(c); })" in body
    assert "prefers-reduced-motion: reduce" in body and "else pickCity(c);" in body
