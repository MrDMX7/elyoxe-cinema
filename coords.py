"""coords.py — give every cinema in cinemas.yaml a lat, lng and coord_source (run by hand).

The site's «أقرب سينما» and «الوصول» need coordinates for every cinema; readers only carry a
few. Sources, first that answers wins, each checked against the cinema's city box:
  1. the chain's own API coordinates (Star's cinema_latitude/longitude minus its placeholder
     values, Novo's lat/long) as the reader returned them;
  2. VOX's own cinema page (uae.voxcinemas.com/cinemas/<slug>: its MAP button is
     maps.google.com/maps?g=<lat>,<lng>);
  3. the Google Maps link the chain itself publishes for that cinema (Star's goo.gl links),
     resolved to the place pin (!3d<lat>!4d<lng> — never the viewport '@', which follows the
     requester's IP);
  4. OpenStreetMap Nominatim search for the mall (usage policy: <= 1 request/s, a real
     User-Agent with a contact address, results cached in data/geocode_cache.json).
Rewrites only the `lat`, `lng`, `coord_source` keys on each cinema's line in cinemas.yaml, so
the file's comments and layout survive. A cinema that already has coordinates is left alone
unless --force.

python coords.py [--force] [--only cid,cid]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
YAML_PATH = ROOT / "cinemas.yaml"
CACHE = ROOT / "data" / "geocode_cache.json"
UA = "elyoxe-cinema/1.0 (+https://cinema.elyoxe.com; contact hello@elyoxe.com)"

# rough boxes: (lat_min, lat_max, lng_min, lng_max)
CITY_BOX = {
    "abu-dhabi": (22.6, 24.95, 51.4, 55.1),
    "al-ain": (23.9, 24.5, 55.4, 56.0),
    "dubai": (24.75, 25.4, 54.85, 55.7),
    "sharjah": (25.15, 25.45, 55.35, 55.8),
    "ajman": (25.33, 25.48, 55.4, 55.62),
    "ras-al-khaimah": (25.55, 26.1, 55.7, 56.2),
    "fujairah": (25.0, 25.7, 56.1, 56.45),
    "umm-al-quwain": (25.45, 25.65, 55.5, 55.8),
}

# Nominatim queries where "<mall>, <city>" is not enough to land on the right place.
QUERIES = {
    "reel-dubai-mall": ["The Dubai Mall"],
    "reel-dubai-marina-mall": ["Dubai Marina Mall"],
    "reel-the-springs-souk": ["The Springs Souk", "Springs Souk, Dubai"],
    "roxy-dubai-hills-mall": ["Dubai Hills Mall"],
    "roxy-circle-mall": ["Circle Mall, Jumeirah Village Circle", "Circle Mall, Dubai"],
    "roxy-city-walk": ["City Walk, Dubai", "City Walk, Al Wasl"],
    "roxy-the-beach-jbr": ["The Beach, JBR", "The Beach, Jumeirah Beach Residence"],
    "roxy-boxpark": ["Boxpark, Dubai", "Box Park, Al Wasl Road"],
    "roxy-al-khawaneej": ["Al Khawaneej Walk", "Khawaneej Walk, Dubai"],
    "cineroyal-khalidiyah-mall": ["Khalidiyah Mall, Abu Dhabi", "Khalidiyah Mall"],
    "cineroyal-dalma-mall": ["Dalma Mall"],
    "cineroyal-al-dhannah-mall": ["Dhannah Mall", "Al Dhannah Mall, Ruwais", "Ruwais Mall"],
    "cineroyal-deerfields-mall": ["Deerfields Mall", "Deerfields Townsquare"],
    "cineroyal-wtc-mall-abu-dhabi": ["World Trade Center Mall, Abu Dhabi", "WTC Mall Abu Dhabi", "The Souk at Central Market, Abu Dhabi"],
    "cinemacity-alqana": ["The National Aquarium, Abu Dhabi", "Al Qana Abu Dhabi", "Al Qana"],
    "cinemacity-starlight": ["Marina Mall, Abu Dhabi"],
    "cinemacity-fountain-views": ["The Dubai Mall"],
    "cinemacity-arabian-centre": ["Arabian Center, Dubai", "Arabian Centre, Al Khawaneej"],
    "cinemacity-rahmania": ["Rahmania Mall", "Al Rahmaniya Mall", "Rahmaniya, Sharjah"],
    "cinemacity-zero-6-mall": ["Zero 6 Mall", "Zero6 Mall", "Zero 6, Al Juraina"],
    "vox-city-centre-sharjah": ["Sharjah City Centre", "City Centre Sharjah, Al Wahda Street"],
    "vox-dubai-festival-city-mall": ["Dubai Festival City Mall", "Festival City Mall", "Dubai Festival City"],
    "vox-megaplex-cineplex-grand-hyatt": ["Grand Hyatt Dubai", "Grand Hyatt, Umm Hurair"],
    "vox-wafi-mall-at-wafi-city": ["Wafi Mall", "Wafi City, Dubai", "Wafi"],
    "novo-img-worlds": ["IMG Worlds of Adventure"],
    "star-grand-mall-ajman": ["Grand Mall, Ajman"],
    "star-grand-safeer-abu-dhabi": ["Safeer Mall, Mussafah", "Grand Safeer Mall, Abu Dhabi"],
}
# the same building as another id: an old id spelling, or a cinema inside another's mall
SAME_SITE = {
    "vox-kempinski-mall-of-emirates": "vox-mall-of-the-emirates",
    "vox-yas-mall": "vox-yas-mall-abu-dhabi",
    "star-bawadi-mall": "star-bawadi-mall-al-ain",
    "cinemacity-zero6-mall": "cinemacity-zero-6-mall",
}
CITY_WORD = {"abu-dhabi": "Abu Dhabi", "al-ain": "Al Ain", "dubai": "Dubai", "sharjah": "Sharjah",
             "ajman": "Ajman", "ras-al-khaimah": "Ras Al Khaimah", "fujairah": "Fujairah",
             "umm-al-quwain": "Umm Al Quwain"}
_DUMMY = {21.12345, 12.12345}


# words that never identify a place on their own
_STOP = {"the", "mall", "al", "at", "of", "and", "in", "uae", "dubai", "abu", "dhabi", "sharjah", "ajman",
         "fujairah", "ras", "khaimah", "umm", "quwain", "ain", "city", "centre", "center", "shopping"}


def _tokens(text: str) -> list[str]:
    t = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower().replace("centre", "center"))
    return [w for w in t.split() if w]


def name_matches(query: str, display_name: str) -> bool:
    """A Nominatim hit is accepted only when it names what was asked for: every distinctive
    query token (not a city word, not "mall"/"centre") appears in its display_name; a query
    made only of such words ("Abu Dhabi Mall", "The Dubai Mall") needs all its words there."""
    have = set(_tokens(display_name))
    want = [w for w in _tokens(query) if w not in _STOP] or [w for w in _tokens(query) if w != "the"]
    return bool(want) and all(w in have for w in want)


def in_box(city, lat, lng) -> bool:
    b = CITY_BOX.get(city)
    if not b:
        return 22.0 < lat < 26.5 and 51.0 < lng < 56.6
    return b[0] <= lat <= b[1] and b[2] <= lng <= b[3]


def known_cinemas() -> dict:
    """{cid: cinema record} from data/latest.json, data/raw/*.json and fixtures/*.json."""
    out: dict = {}
    paths = [ROOT / "data" / "latest.json", *sorted((ROOT / "data" / "raw").glob("*.json")),
             *sorted((ROOT / "fixtures").glob("*.json"))]
    for p in paths:
        if p.name == "sample_latest.json" or not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        cin = d.get("cinemas") or {}
        for c in (cin.values() if isinstance(cin, dict) else cin):
            if p.name == "latest.json":  # finalized: its lat/lng are cinemas.yaml's own, not a reader's
                c = {k: v for k, v in c.items() if k not in ("lat", "lng", "coord_source", "maps")}
            prev = out.get(c["id"], {})
            out[c["id"]] = {**c, **{k: v for k, v in prev.items() if v not in (None, "")}}
    return out


class Geo:
    def __init__(self):
        from curl_cffi import requests as cr

        self.cr = cr
        self.s = cr.Session(impersonate="chrome")
        self.last = 0.0
        try:
            self.cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.cache = {}

    def save(self):
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    def _wait(self, gap):
        w = gap - (time.monotonic() - self.last)
        if w > 0:
            time.sleep(w)
        self.last = time.monotonic()

    def vox_page(self, slug):
        key = f"vox2:{slug}"
        if key not in self.cache:
            self._wait(1.2)
            r = self.s.get(f"https://uae.voxcinemas.com/cinemas/{slug}", timeout=30)
            # the MAP button: maps.google.com/maps?g=<lat>,<lng> or google.com/maps?q=<lat>,<lng>
            m = re.search(r"google\.[a-z.]+/maps\?[gq]=(-?\d+\.\d+),(-?\d+\.\d+)", r.text) if r.status_code == 200 else None
            self.cache[key] = [float(m.group(1)), float(m.group(2))] if m else None
        return self.cache[key]

    def cinemacity_page(self, code):
        """The chain's own location page carries schema.org GeoCoordinates in its JSON-LD."""
        key = f"cinemacity:{code}"
        if key not in self.cache:
            if "cinemacity:_index" not in self.cache:
                self._wait(1.2)
                t = self.s.get("https://www.cinemacity.ae/page-data/our-locations/page-data.json", timeout=30).text
                self.cache["cinemacity:_index"] = sorted(set(re.findall(r"/our-locations/([a-z0-9-]+)", t)))
            slug = next((x for x in self.cache["cinemacity:_index"] if x.startswith(code.lower() + "-")), None)
            ll = None
            if slug:
                self._wait(1.2)
                t = self.s.get(f"https://www.cinemacity.ae/our-locations/{slug}", timeout=30).text
                m = re.search(r'"latitude":\s*(-?\d+\.\d+),\s*"longitude":\s*(-?\d+\.\d+)', t)
                ll = [float(m.group(1)), float(m.group(2))] if m else None
            self.cache[key] = ll
        return self.cache[key]

    def gmaps_link(self, url):
        key = f"gmaps:{url}"
        if key not in self.cache:
            self._wait(1.2)
            try:
                r = self.s.get(url, allow_redirects=True, timeout=30)
                m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", str(r.url)) or \
                    re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", r.text[:400000])
                self.cache[key] = [float(m.group(1)), float(m.group(2))] if m else None
            except Exception:  # noqa: BLE001
                self.cache[key] = None
        return self.cache[key]

    def nominatim(self, q):
        key = f"nominatim:{q}"
        if key not in self.cache:
            import requests

            self._wait(1.1)
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "jsonv2", "limit": 3, "countrycodes": "ae"},
                             headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=30)
            hits = r.json() if r.status_code == 200 else []
            self.cache[key] = [[float(h["lat"]), float(h["lon"]), h.get("display_name", "")] for h in hits]
        return self.cache[key]


def locate(cid: str, c: dict, geo: Geo):
    city = c.get("city")
    lat, lng = c.get("lat"), c.get("lng")
    if lat is not None and lng is not None and lat not in _DUMMY and in_box(city, lat, lng):
        return lat, lng, f"{c['chain']} API"
    if c.get("chain") == "vox":
        ll = geo.vox_page(cid[len("vox-"):])
        if ll and in_box(city, *ll):
            return ll[0], ll[1], "vox cinema page (map link)"
    if c.get("chain") == "cinemacity":
        from readers.cinemacity import CINEMAS_RAW, _cinema_id

        code = next((code for code, name, *_ in CINEMAS_RAW if _cinema_id(name) == cid), None)
        ll = geo.cinemacity_page(code) if code else None
        if ll and in_box(city, *ll):
            return ll[0], ll[1], "cinemacity location page (schema.org geo)"
    maps = c.get("maps") or ""
    if re.search(r"goo\.gl/|google\.[a-z.]+/maps/place/", maps):
        ll = geo.gmaps_link(maps)
        if ll and in_box(city, *ll):
            return ll[0], ll[1], f"google maps link published by {c['chain']}"
    mall = re.sub(r"\s*-\s*[A-Za-z ]+$", "", c.get("mall") or "").strip()
    qs = QUERIES.get(cid) or []
    qs = qs + [f"{mall}, {CITY_WORD.get(city, '')}".strip(", ")]
    for q in qs:
        for lat, lng, name in geo.nominatim(q):
            if in_box(city, lat, lng) and name_matches(q, name):
                return round(lat, 6), round(lng, 6), f"openstreetmap nominatim: {q}"
    return None


def write_yaml(results: dict) -> int:
    lines = YAML_PATH.read_text(encoding="utf-8").split("\n")
    n = 0
    for i, line in enumerate(lines):
        m = re.match(r"^(\s+)([a-z0-9-]+):(\s+)\{(.*)\}\s*$", line)
        if not m or m.group(2) not in results:
            continue
        lat, lng, src = results[m.group(2)]
        body = re.sub(r",\s*(?:lat|lng|coord_source):\s*(?:\"[^\"]*\"|[^,}]+)", "", m.group(4)).rstrip()
        body += f', lat: {lat}, lng: {lng}, coord_source: "{src}"'
        lines[i] = f"{m.group(1)}{m.group(2)}:{m.group(3)}{{{body}}}"
        n += 1
    with open(YAML_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args(argv)
    meta = (yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}).get("cinemas") or {}
    cinemas = known_cinemas()
    only = set(a.only.split(",")) if a.only else None
    geo = Geo()
    results, missing = {}, []
    try:
        for cid in sorted(set(cinemas) | set(meta)):
            if only and cid not in only:
                continue
            if not a.force and (meta.get(cid) or {}).get("lat") is not None:
                continue
            if cid in SAME_SITE:
                continue
            c = cinemas.get(cid)
            if c is None:  # a yaml-only id (an old spelling): borrow a sibling's record
                twin = next((k for k in cinemas if k.replace("-", "") == cid.replace("-", "")), None)
                c = cinemas.get(twin)
            if c is None and cid in QUERIES:  # a yaml-only id with a known query
                c = {"id": cid, "chain": cid.split("-")[0], "city": None, "mall": ""}
            if c is None:
                missing.append(cid)
                continue
            r = locate(cid, c, geo)
            if r:
                results[cid] = r
                print(f"{cid:40s} {r[0]:.5f},{r[1]:.5f}  {r[2]}")
            else:
                missing.append(cid)
                print(f"{cid:40s} NOT FOUND", file=sys.stderr)
        for cid, twin in SAME_SITE.items():
            if (only and cid not in only) or (not a.force and (meta.get(cid) or {}).get("lat") is not None):
                continue
            src = results.get(twin) or ((meta.get(twin) or {}).get("lat") is not None and
                                        (meta[twin]["lat"], meta[twin]["lng"], meta[twin].get("coord_source")))
            if src:
                results[cid] = (src[0], src[1], f"same site as {twin} ({src[2]})")
                missing = [m for m in missing if m != cid]
                print(f"{cid:40s} = {twin}")
    finally:
        geo.save()
    if missing and not a.only:
        print("missing:", ", ".join(missing), file=sys.stderr)
    notin = sorted(set(results) - set(meta))
    if notin:
        print("not in cinemas.yaml (add a name line first):", ", ".join(notin), file=sys.stderr)
    print(f"wrote {write_yaml(results)} line(s)")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
