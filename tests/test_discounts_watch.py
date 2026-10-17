"""discounts_watch.py (roadmap 195): source pages of discounts.yaml are hashed on their offer lines only, a change
or an outage is reported once, and the baseline moves — never a network call here (fake fetcher)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import discounts_watch as dw  # noqa: E402

PAGE = """<html><head><title>Offers</title><script>var x = Date.now();</script></head><body>
<nav>Home · Movies · Offers</nav>
<h1>Fazaa card: 20% off cinema tickets</h1>
<p>Valid at the box office, 4 tickets a day.</p>
<footer>© 2026 — last updated Thursday</footer></body></html>"""


def test_sources_collects_every_rule_url_from_the_real_yaml():
    src = dw.sources()
    assert len(src) >= 15
    assert all(u.startswith("http") for u in src)
    assert any("star/" in r for rules in src.values() for r in rules)


def test_relevant_text_keeps_offer_lines_and_drops_scripts_and_noise():
    t = dw.relevant_text(PAGE)
    assert "Fazaa card: 20% off cinema tickets" in t
    assert "4 tickets a day" in t
    assert "Date.now" not in t and "<" not in t


def test_digest_ignores_whitespace_and_footer_dates():
    a = dw.digest(PAGE)
    b = dw.digest(PAGE.replace("last updated Thursday", "last updated Friday").replace("  ", " "))
    assert a == b
    c = dw.digest(PAGE.replace("20% off", "25% off"))
    assert a != c


def test_compare_states():
    prev = {"a": {"status": 200, "hash": "1"}, "b": {"status": 200, "hash": "2"}, "c": {"status": 404, "hash": None},
            "d": {"status": 200, "hash": "4"}}
    now = {"a": {"status": 200, "hash": "1"}, "b": {"status": 200, "hash": "x"}, "c": {"status": 200, "hash": "3"},
           "d": {"status": None, "hash": None}, "e": {"status": 200, "hash": "5"}}
    assert dw.compare(prev, now) == {"a": "same", "b": "changed", "c": "back", "d": "down", "e": "new"}


def test_run_reports_once_and_moves_the_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(dw, "GAP", 0)
    y = tmp_path / "d.yaml"
    y.write_text("rules:\n  star:\n    fazaa: {type: percent, value: 20, source: 'https://x/offers'}\n"
                 "    esaad: {status: none_found, source: 'https://y/esaad'}\n", encoding="utf-8")
    st = tmp_path / "state.json"
    pages = {"https://x/offers": (200, PAGE), "https://y/esaad": (200, PAGE)}
    fetcher = lambda u: pages[u]  # noqa: E731
    assert dw.run(fetcher=fetcher, state_path=st, yaml_path=y) == ""          # first read: a baseline, no alarm
    assert json.loads(st.read_text(encoding="utf-8"))["https://x/offers"]["status"] == 200
    assert dw.run(fetcher=fetcher, state_path=st, yaml_path=y) == ""          # nothing moved
    pages["https://x/offers"] = (200, PAGE.replace("20% off", "15% off"))
    pages["https://y/esaad"] = (None, "ERR Timeout")
    line = dw.run(fetcher=fetcher, state_path=st, yaml_path=y)
    assert "تغيّرت صفحة x (star/fazaa)" in line and "ما ترد صفحة y (star/esaad)" in line
    assert dw.run(fetcher=fetcher, state_path=st, yaml_path=y) == ""          # reported once; the baseline moved
    pages["https://y/esaad"] = (200, PAGE)
    assert dw.run(fetcher=fetcher, state_path=st, yaml_path=y) == ""          # a page coming back is not an alarm
    before = st.read_text(encoding="utf-8")
    assert dw.run(dry=True, fetcher=fetcher, state_path=st, yaml_path=y) == ""
    assert st.read_text(encoding="utf-8") == before                           # --dry never writes
