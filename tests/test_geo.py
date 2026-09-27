"""City from the network (237): infra/geo.js (the CloudFront Function behind /geo) maps CloudFront's viewer
geolocation to our eight city slugs, and src/js/geo.js asks it only on a first visit with no saved city."""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from site_kit import CITIES  # noqa: E402

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")


def node(tmp_path, src):
    (tmp_path / "t.js").write_text(src, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def fn(tmp_path, expr):
    src = open(os.path.join(ROOT, "infra", "geo.js"), encoding="utf-8").read()
    return node(tmp_path, src + "\nprocess.stdout.write(JSON.stringify(" + expr + "));\n")


def hdrs(**kw):
    return {"cloudfront-viewer-" + k.replace("_", "-"): {"value": v} for k, v in kw.items()}


def test_the_function_answers_itself_private_no_store(tmp_path):
    ev = {"request": {"uri": "/geo", "headers": hdrs(country="AE", city="Al Ain", country_region="AZ")}}
    r = fn(tmp_path, f"handler({json.dumps(ev)})")
    assert r["statusCode"] == 200
    assert r["headers"]["cache-control"]["value"] == "private, no-store"
    assert r["headers"]["content-type"]["value"].startswith("application/json")
    assert json.loads(r["body"]["data"]) == {"city": "al-ain"}
    empty = fn(tmp_path, 'handler({request: {uri: "/geo", headers: {}}})')
    assert json.loads(empty["body"]["data"]) == {"city": None}
    assert "console" not in open(os.path.join(ROOT, "infra", "geo.js"), encoding="utf-8").read()


@pytest.mark.parametrize("country,city,region,name,want", [
    ("AE", "Al Ain", "AZ", "Abu Dhabi", "al-ain"),            # the city name wins over its region
    ("AE", "Al%20Ain", "AZ", "", "al-ain"),                    # URI-encoded header values
    ("AE", "Al-Ain", "", "", "al-ain"),
    ("AE", "Abu Dhabi", "AZ", "", "abu-dhabi"),
    ("AE", "Mussafah", "AZ", "", "abu-dhabi"),
    ("AE", "Some Village", "AZ", "", "abu-dhabi"),             # unknown city: the region decides
    ("AE", "Dubai", "DU", "", "dubai"),
    ("AE", "Sharjah", "SH", "", "sharjah"),
    ("AE", "Khor Fakkan", "SH", "", "sharjah"),
    ("AE", "Ajman", "AJ", "", "ajman"),
    ("AE", "Ras al-Khaimah", "RK", "", "ras-al-khaimah"),
    ("AE", "Ras Al Khaimah", "", "", "ras-al-khaimah"),
    ("AE", "Fujairah", "FU", "", "fujairah"),
    ("AE", "Umm Al Quwain", "UQ", "", "umm-al-quwain"),
    ("AE", "", "", "Umm Al Quwain", "umm-al-quwain"),          # region name only
    ("AE", "", "", "Emirate of Dubai", "dubai"),
    ("ae", "", "SH", "", "sharjah"),
    ("AE", "", "", "", None),
    ("SA", "Riyadh", "01", "", None),                           # outside the UAE: nothing
    ("OM", "Al Ain", "", "", None),                             # a same-named place abroad is not ours
    ("", "Dubai", "DU", "", None),
])
def test_city_mapping(tmp_path, country, city, region, name, want):
    assert fn(tmp_path, f"cityOf({json.dumps(country)},{json.dumps(city)},{json.dumps(region)},{json.dumps(name)})") == want


def test_every_answer_is_one_of_our_cities(tmp_path):
    got = fn(tmp_path, "Object.keys(CITY).map(function(k){return CITY[k]}).concat(Object.keys(REGION).map(function(k){return REGION[k]}), Object.keys(REGION_NAME).map(function(k){return REGION_NAME[k]}))")
    ours = {c[0] for c in CITIES}
    assert set(got) <= ours and set(got) == ours


# ---------------------------------------------------------------- the client, src/js/geo.js, with a stub page

HARNESS = r"""
var store = %(store)s, calls = [], picked = [], msgs = [], feats = [];
var AR = true, page = %(page)s, pageCity = %(pageCity)s, C = { cities: { "dubai": "دبي", "al-ain": "العين", "sharjah": "الشارقة" } };
var search = %(search)s;
function get(k) { return store[k] == null ? null : store[k]; }
function set(k, v) { if (v === "" || v == null) delete store[k]; else store[k] = v; }
function param(k) { var m = new RegExp("[?&]" + k + "=([^&]+)").exec(search); return m ? decodeURIComponent(m[1]) : null; }
function sub(s, o) { return String(s).replace(/\{(\w+)\}/g, function (m, k) { return o[k] != null ? o[k] : m; }); }
function esc(s) { return String(s); }
function pickCity(c) { picked.push(c); set("city", c); }
var el = { textContent: "", insertAdjacentHTML: function (p, h) { this.textContent += h; } };
function qa(s) { return s === "[data-near-msg]" ? [el] : []; }
function q() { return null; }
var document = { addEventListener: function () {} };
function feature(f) { feats.push(f); }
var answer = %(answer)s, beforeAnswer = %(before)s;
function fetch(u, o) {
  calls.push(u);
  if (answer === "offline") return Promise.reject(new Error("offline"));
  if (beforeAnswer) set("city", beforeAnswer);
  return Promise.resolve({ ok: answer !== 500, json: function () { return Promise.resolve(answer); } });
}
%(src)s
feats.forEach(function (f) { f(); });
setTimeout(function () {
  process.stdout.write(JSON.stringify({ calls: calls, picked: picked, msg: el.textContent, store: store }));
}, 20);
"""


def client(tmp_path, store=None, page="home", pageCity=None, search="", answer=None, before=None):
    src = open(os.path.join(ROOT, "src", "js", "geo.js"), encoding="utf-8").read()
    return node(tmp_path, HARNESS % {"store": json.dumps(store or {}), "page": json.dumps(page), "pageCity": json.dumps(pageCity),
                                     "search": json.dumps(search), "answer": json.dumps(answer), "before": json.dumps(before), "src": src})


def test_first_visit_picks_the_network_city_and_says_so(tmp_path):
    r = client(tmp_path, answer={"city": "al-ain"})
    assert r["calls"] == ["/geo"] and r["picked"] == ["al-ain"]
    assert r["msg"].startswith("اخترنا العين حسب شبكتك") and "data-geo-change" in r["msg"] and "غيّرها" in r["msg"]
    assert r["store"] == {"city": "al-ain", "geo": "1"}


def test_film_page_too(tmp_path):
    assert client(tmp_path, page="film", answer={"city": "sharjah"})["picked"] == ["sharjah"]


def test_a_saved_city_is_never_overridden_and_never_asks(tmp_path):
    r = client(tmp_path, store={"city": "dubai"}, answer={"city": "al-ain"})
    assert r["calls"] == [] and r["picked"] == [] and r["store"]["city"] == "dubai"


def test_a_city_picked_while_waiting_wins(tmp_path):
    r = client(tmp_path, answer={"city": "al-ain"}, before="sharjah")
    assert r["calls"] == ["/geo"] and r["picked"] == [] and r["msg"] == "" and r["store"]["city"] == "sharjah"


def test_city_pages_and_city_links_do_not_ask(tmp_path):
    assert client(tmp_path, page="city", pageCity="dubai", answer={"city": "al-ain"})["calls"] == []
    assert client(tmp_path, search="?city=dubai", answer={"city": "al-ain"})["calls"] == []
    assert client(tmp_path, page="cards", answer={"city": "al-ain"})["calls"] == []


def test_asked_once(tmp_path):
    r = client(tmp_path, answer={"city": None})
    assert r["calls"] == ["/geo"] and r["picked"] == [] and r["msg"] == "" and r["store"] == {"geo": "1"}
    assert client(tmp_path, store={"geo": "1"}, answer={"city": "al-ain"})["calls"] == []


@pytest.mark.parametrize("answer", ["offline", 500, {"city": "atlantis"}, {"nope": 1}])
def test_failure_changes_nothing(tmp_path, answer):
    r = client(tmp_path, answer=answer)
    assert r["picked"] == [] and r["msg"] == "" and "city" not in r["store"]


def test_geo_is_in_the_bundle():
    import build
    assert any(p.replace("\\", "/").endswith("src/js/geo.js") for p in build.js_files())
