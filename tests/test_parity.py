"""Python <-> JS discount parity: discounts.compute() and cinema.js discAfter() must give the same answer
for every (price, chain, hall, hall key, cinema, card, date) — the pages are built by one and rewritten in
the browser by the other. The JS side is the block between `disc:begin` and `disc:end` in src/cinema.js,
run as-is in node (installed on both machines and on the CI runner)."""
import itertools
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import discounts  # noqa: E402

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")

# every branch of the semantics, on top of the real discounts.yaml
SYNTH = {
    "t": {
        "pct": {"type": "percent", "value": 20},
        "pct_odd": {"type": "percent", "value": 15},
        "bogo": {"type": "bogo"},
        "fixed": {"type": "fixed", "value": 21},
        "exc": {"type": "percent", "value": 25, "excluded_halls": ["IMAX", "SKY"]},
        "exc_alias": {"type": "bogo", "halls_excluded": ["THEATRE"]},
        "inc": {"type": "percent", "value": 25, "included_halls": ["SUITES"]},
        "inc_empty": {"type": "percent", "value": 25, "included_halls": []},
        "cin": {"type": "fixed", "value": 21, "included_halls": ["Standard"], "included_cinemas": ["c-1"]},
        "until": {"type": "percent", "value": 50, "valid_until": "2026-09-26"},
        "gone": {"type": "bogo", "valid_until": "2026-05-23"},
        "none": {"status": "none_found", "type": "percent", "value": 20},
        "odd_type": {"type": "cashback", "value": 10},
    }
}
PRICES = [42, 52.5, 46, 33.33, 19.99, 0.05, 195, 1.005, 10.125]
HALLS = [("Standard", "Standard"), ("VIP", "SKY"), ("VIP", "7STAR"), ("IMAX", "IMAX"), ("THEATRE", "THEATRE"),
         ("SUITES", "PLATINUM"), ("OTHER", "t|DOLBY"), ("KIDS", None), (None, None)]
CINEMAS = ["c-1", "c-2", None]
DATES = ["2026-05-22", "2026-09-26", "2026-09-27", "2027-12-31"]


def _rules():
    real = json.loads(json.dumps(discounts.load()["rules"], default=str))  # as discounts.json carries them
    return {**real, **SYNTH}


def _cases(rules):
    real = [(ch, card) for ch, cards in rules.items() for card in cards]
    real += [("t", "missing"), ("nochain", "fazaa")]
    out = []
    for (chain, card), (hall, hk), cin, day in itertools.product(real, HALLS, CINEMAS, DATES):
        for price in (PRICES if chain == "t" else PRICES[:3]):
            out.append({"price": price, "chain": chain, "hall": hall, "hk": hk, "cin": cin, "card": card, "day": day})
    return out


def _js_block():
    src = open(os.path.join(ROOT, "src", "cinema.js"), encoding="utf-8").read()
    m = re.search(r"/\* disc:begin.*?\*/(.*?)/\* disc:end \*/", src, re.S)
    assert m, "cinema.js lost its disc:begin/disc:end block"
    return m.group(1)


def _run_js(rules, cases, tmp_path):
    harness = _js_block() + r"""
var input = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
var out = input.cases.map(function (k) {
  var x = discAfter(input.rules, k.day, k.price, k.chain, k.hall, k.hk, k.cin, k.card);
  return { a: x.a, st: x.st, per: discPayNote(x.a != null ? x.r : null, { per_person: "PP" }) };
});
process.stdout.write(JSON.stringify(out));
"""
    (tmp_path / "h.js").write_text(harness, encoding="utf-8")
    (tmp_path / "in.json").write_text(json.dumps({"rules": rules, "cases": cases}), encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "h.js"), str(tmp_path / "in.json")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _py(rules, k):
    hk = k["hk"].split("|", 1)[1] if k["hk"] and "|" in k["hk"] else k["hk"]
    a, st, r = discounts.compute(k["price"], k["chain"], k["hall"], k["card"], rules, hall_key=hk, cinema=k["cin"], today=k["day"])
    return {"a": a, "st": st, "per": "PP" if a is not None and r.get("type") == "bogo" else ""}


def test_python_and_js_discounts_agree(tmp_path):
    rules = _rules()
    cases = _cases(rules)
    js = _run_js(rules, cases, tmp_path)
    assert len(js) == len(cases)
    diff = [(k, p, j) for k, j in zip(cases, js) for p in [_py(rules, k)] if p != j]
    assert not diff, f"{len(diff)} of {len(cases)} differ, first: {diff[:3]}"
    # the matrix really exercises every branch
    states = {j["st"] for j in js}
    assert states == {"ok", "excluded", "expired", "none_found", "unchecked"}
    assert any(j["per"] == "PP" for j in js)


def test_branches_give_the_expected_answers():
    rules = _rules()

    def a(price, card, hall="Standard", hk=None, cin=None, day="2026-09-26"):
        return discounts.compute(price, "t", hall, card, rules, hall_key=hk, cinema=cin, today=day)[:2]
    assert a(52.5, "pct") == (42.0, "ok")
    assert a(46, "bogo") == (23.0, "ok")
    assert a(44, "fixed") == (21.0, "ok") and a(18, "fixed") == (18.0, "ok")        # never above the real price
    assert a(60, "exc", "VIP", "SKY") == (None, "excluded")                           # by halls.yaml key
    assert a(60, "exc", "VIP", "7STAR") == (45.0, "ok")
    assert a(60, "exc_alias", "THEATRE") == (None, "excluded")                        # halls_excluded spelling
    assert a(60, "inc", "Standard") == (None, "excluded") and a(100, "inc", "SUITES") == (75.0, "ok")
    assert a(40, "cin", cin="c-1") == (21.0, "ok") and a(40, "cin", cin="c-2") == (None, "excluded")
    assert a(40, "until", day="2026-09-26") == (20.0, "ok") and a(40, "until", day="2026-09-27") == (None, "expired")
    assert a(40, "none") == (None, "none_found") and a(40, "odd_type") == (None, "none_found")
    assert a(40, "missing") == (None, "unchecked")
    assert a(1.005, "pct") == (0.8, "ok") and a(10.125, "bogo") == (5.06, "ok")      # half-up, as JS rounds


def test_the_four_reviewed_rows():
    """Final review, Important 5 — the rows that published wrong math."""
    R = discounts.load()["rules"]
    day = "2026-09-26"
    # Novo Esaad: not in SKY (code VIP, key SKY) nor IMAX; other VIP halls keep it
    assert discounts.compute(60, "novo", "VIP", "esaad", R, hall_key="SKY", today=day)[1] == "excluded"
    assert discounts.compute(60, "novo", "IMAX", "esaad", R, hall_key="IMAX", today=day)[1] == "excluded"
    assert discounts.compute(60, "novo", "Standard", "esaad", R, hall_key="Standard", today=day)[0] == 48.0
    # Cine Royal ENBD: regular (Standard) tickets only
    assert discounts.compute(45, "cineroyal", "VIP", "enbd", R, hall_key="VIP", today=day)[1] == "excluded"
    assert discounts.compute(45, "cineroyal", "OTHER", "enbd", R, hall_key="ROYALPLUS", today=day)[1] == "excluded"
    assert discounts.compute(45, "cineroyal", "Standard", "enbd", R, hall_key="Standard", today=day)[0] == 22.5
    # Cine Royal RAKBANK: 2D Standard/VIP only — and the offer ended on 2026-05-23
    assert discounts.compute(45, "cineroyal", "Standard", "rakbank", R, today=day)[1] == "expired"
    assert R["cineroyal"]["rakbank"]["included_halls"] == ["Standard", "VIP"]
    # Reel FAB: no longer an HSBC-sourced BOGO; FAB's own fixed regular-2D price at its three branches
    fab = R["reel"]["fab"]
    assert "hsbc" not in fab["source"].lower() and "bankfab.com" in fab["source"]
    assert discounts.compute(44, "reel", "Standard", "fab", R, hall_key="Standard", cinema="reel-dubai-mall", today=day)[0] == 21.0
    assert discounts.compute(90, "reel", "SUITES", "fab", R, hall_key="PLATINUM", cinema="reel-dubai-mall", today=day)[1] == "excluded"
