"""steps/cinema_coords.py (owner 2026-11-18): a cinema a chain opened after cinemas.yaml was written gets its coordinates
by itself, and a cinema nobody could place no longer stops the publish. VOX Moonlight (2026-11-12) froze the site for a
week because the gate wanted its lat/lng in the yaml. Never a network call here: the lookup is injected."""
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import alerts  # noqa: E402
import coords  # noqa: E402
import refresh  # noqa: E402
from steps import cinema_coords as cc  # noqa: E402

NOW = "2026-11-18T17:00:00+04:00"


def cinema(cid, city="dubai", **kw):
    return {"id": cid, "chain": cid.split("-")[0], "city": city, "mall": "Galleria Mall Dubai-Moonlight", **kw}


def ctx(tmp_path, calls, answer=(25.2067, 55.2545, "vox cinema page (map link)"), **kw):
    def locate(cid, c):
        calls.append(cid)
        return answer
    return {"offline": False, "now": NOW, "data_dir": str(tmp_path), "locate": locate, **kw}


def test_a_cinema_without_coordinates_gets_them_on_latest_json_and_in_the_cache(tmp_path):
    calls = []
    data = {"cinemas": {"vox-new": cinema("vox-new", lat=None, lng=None), "star-old": cinema("star-old", lat=24.1, lng=55.7)}}
    r = cc.run(data, ctx(tmp_path, calls))
    c = data["cinemas"]["vox-new"]
    assert (c["lat"], c["lng"]) == (25.2067, 55.2545)
    assert c["coord_source"] == "auto: vox cinema page (map link)"
    assert c["maps"] == "https://www.google.com/maps/search/?api=1&query=25.2067,55.2545"
    assert calls == ["vox-new"]                                         # a cinema that has coordinates is never looked up
    assert r["auto"] == ["vox-new"] and r["missing"] == []
    saved = json.loads((tmp_path / "auto_coords.json").read_text(encoding="utf-8"))
    assert saved["vox-new"]["lat"] == 25.2067 and saved["vox-new"]["at"] == NOW


def test_a_cached_hit_is_used_without_a_lookup(tmp_path):
    (tmp_path / "auto_coords.json").write_text(json.dumps(
        {"vox-new": {"lat": 25.2, "lng": 55.25, "coord_source": "openstreetmap nominatim: Galleria Mall, Dubai", "at": NOW}}))
    calls = []
    data = {"cinemas": {"vox-new": cinema("vox-new")}}
    cc.run(data, ctx(tmp_path, calls))
    assert calls == [] and data["cinemas"]["vox-new"]["lat"] == 25.2


def test_a_miss_is_retried_only_after_its_wait(tmp_path):
    calls = []
    data = {"cinemas": {"vox-new": cinema("vox-new")}}
    r = cc.run(data, ctx(tmp_path, calls, answer=None))
    assert calls == ["vox-new"] and r["missing"] == ["vox-new"] and data["cinemas"]["vox-new"].get("lat") is None
    cc.run(data, ctx(tmp_path, calls, answer=None))                    # the next run, 3 h later: the miss stands
    assert calls == ["vox-new"]
    later = (datetime.fromisoformat(NOW) + timedelta(days=cc.MISS_DAYS, hours=1)).isoformat()
    cc.run(data, ctx(tmp_path, calls, now=later))
    assert calls == ["vox-new", "vox-new"] and data["cinemas"]["vox-new"]["lat"] == 25.2067


def test_coordinates_outside_the_cinemas_city_are_refused(tmp_path):
    calls = []
    data = {"cinemas": {"vox-new": cinema("vox-new", city="dubai")}}
    r = cc.run(data, ctx(tmp_path, calls, answer=(24.2, 55.7, "openstreetmap nominatim: x")))   # that is Al Ain
    assert data["cinemas"]["vox-new"].get("lat") is None and r["missing"] == ["vox-new"]


def test_offline_makes_no_lookup_and_the_lookups_are_capped(tmp_path):
    calls = []
    data = {"cinemas": {f"vox-n{i}": cinema(f"vox-n{i}") for i in range(cc.CAP + 3)}}
    cc.run(data, ctx(tmp_path, calls, offline=True))
    assert calls == []
    cc.run(data, ctx(tmp_path, calls))
    assert len(calls) == cc.CAP


def test_a_failing_lookup_is_a_miss_not_a_failed_run(tmp_path):
    def locate(cid, c):
        raise RuntimeError("Nominatim 429")
    data = {"cinemas": {"vox-new": cinema("vox-new")}}
    r = cc.run(data, {"offline": False, "now": NOW, "data_dir": str(tmp_path), "locate": locate})
    assert r["missing"] == ["vox-new"]


def test_the_real_lookup_keeps_its_own_page_cache_not_coords_py_s(tmp_path, monkeypatch):
    """test_every_nominatim_coordinate_is_a_name_matched_cached_hit reads data/geocode_cache.json whenever it exists, and the
    runner has none: the step writing it would freeze the very gate it keeps open."""
    seen = {}

    class FakeGeo:
        def __init__(self, cache_path=coords.CACHE):
            seen["path"] = cache_path

        def save(self):
            seen["saved"] = True

    monkeypatch.setattr(coords, "Geo", FakeGeo)
    monkeypatch.setattr(coords, "locate", lambda cid, c, geo: (25.2067, 55.2545, "vox cinema page (map link)"))
    data = {"cinemas": {"vox-new": cinema("vox-new")}}
    cc.run(data, {"offline": False, "now": NOW, "data_dir": str(tmp_path)})
    assert seen["path"] == tmp_path / "auto_geocode.json" and seen["saved"]
    assert data["cinemas"]["vox-new"]["lat"] == 25.2067


def test_vox_map_link_is_read_with_the_equals_sign_escaped():
    """VOX's page writes the MAP button as maps.google.com/maps?q&#x3D;25.2067,55.2545 since November 2026."""
    assert coords.vox_map_ll('<a href="http://maps.google.com/maps?q&#x3D;25.2067,55.2545">Map</a>') == [25.2067, 55.2545]
    assert coords.vox_map_ll('<a href="https://maps.google.com/maps?g=24.48,54.6">Map</a>') == [24.48, 54.6]
    assert coords.vox_map_ll("<p>no map</p>") is None


def test_a_cinema_missing_from_the_yaml_is_one_low_priority_alert_until_its_line_is_written():
    meta = {"vox-old": {"ar": "فوكس — قديم", "lat": 25.0, "lng": 55.0}}
    data = {"cinemas": {"vox-old": cinema("vox-old"), "vox-galleria-mall-dubai-moonlight": cinema("vox-galleria-mall-dubai-moonlight")}}
    h = refresh.yaml_health(data, meta)
    assert h["ok"] is False and "vox-galleria-mall-dubai-moonlight" in h["error"]
    state, line = alerts.health_line({}, {"cinemas.yaml": h}, NOW)
    assert line.startswith("(ثانوي)") and "vox-galleria-mall-dubai-moonlight" in line
    state, line = alerts.health_line(state, {"cinemas.yaml": h}, NOW)
    assert line == ""                                                   # a standing condition stays quiet
    meta["vox-galleria-mall-dubai-moonlight"] = {"ar": "فوكس — مونلايت", "lat": 25.2, "lng": 55.25}
    state, line = alerts.health_line(state, {"cinemas.yaml": refresh.yaml_health(data, meta)}, NOW)
    assert "رجع طبيعي" in line


def test_the_price_share_counts_cached_keys_too():
    """VOX 2026-11-18: «priced=12000%» (120 priced keys, most from today's cache, over 1 live read) and «0%» (all
    cached, none read live); the site itself had 98-99% of VOX shows priced."""
    assert refresh.price_share(1, 120, 119) == (100.0, False)
    assert refresh.price_share(0, 49, 50) == (98.0, False)
    assert refresh.price_share(20, 2, 0) == (10.0, True)          # live reads failing, nothing cached: degraded
    assert refresh.price_share(0, 0, 0) == (0.0, False)           # nothing to price: not degraded
