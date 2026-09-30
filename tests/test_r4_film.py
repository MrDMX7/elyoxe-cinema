"""R4-film (owner round 4, #298-300): the ticket-count stepper's slot, «باقي N مقعد» wired from the build's own
occupancy samples (pages/seats.py had declared s["seats_left"] and never set it), and «وين أرخص؟»'s container and
lazy-chunk registration. The DOM-driving parts of each (the stepper's math, the compare table's rows, the badge's
90-minute/15-seat gate) are src/js/ticket.js, src/js/cinecompare.js and src/js/seatmap.js — reviewed by hand and by
tests/test_js.py (the bundle parses); these hold the server side, where a build can actually be asserted on."""
import json
import os
import re
import sys
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import seats  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


# ---------------------------------------------------------------- #298: the ticket's stepper slot
def test_ticket_carries_the_qty_stepper_slot(tmp_path):
    """kit/ticket.py's ticket() always writes the stepper's (empty, hidden) slot — cinema.js draws its rows and
    total (R4 §298: the stepper needs a tap, so a no-script visitor keeps just the seats table above it)."""
    out = str(tmp_path / "o")
    build.build(DATA, DISC, out, noindex=False)
    home = read(out, "index.html")
    assert '<div class="tk-qty" data-tk-qty hidden></div>' in home
    # never .js-only: that class forces display:flex once .js is on <html>, which would show the slot empty
    # before cinema.js ever fills it — [hidden] alone is what keeps it invisible until then
    assert 'class="tk-qty js-only"' not in home
    # its own lazy chunk (pages/tkqty.py), not the always-loaded bundle: build.JS_WARN_GZ stays clear
    assert re.search(r'"tkqty":\s*"/assets/tkqty\.[0-9a-f]{10}\.js"', home)


# ---------------------------------------------------------------- #299: «وين أرخص؟»
def test_cheapest_chunk_registered_and_container_on_film_pages(tmp_path):
    out = str(tmp_path / "o")
    build.build(DATA, DISC, out, noindex=False)
    d = json.load(open(DATA, encoding="utf-8"))
    fid = d["shows"][0]["film"]
    film = read(out, "film", fid, "index.html")
    # film only (KINDS in pages/cheapest.py): the chunk never reaches a page kind with no ticket to compare
    assert re.search(r'"cinecompare":\s*"/assets/cinecompare\.[0-9a-f]{10}\.js"', film)
    assert '<div class="wrap cheap-cmp" data-cheapest hidden></div>' in film
    assert "cinecompare" not in read(out, "index.html")
    # a page with no schedule at all (archived) carries no empty container either: nothing for cinecompare.js to fill
    archived = next((f for f, meta in d["films"].items() if meta.get("status") == "archived"), None)
    if archived:
        assert "data-cheapest" not in read(out, "film", archived, "index.html")


# ---------------------------------------------------------------- #300: «باقي N مقعد» from real occupancy
def test_seats_left_only_from_a_fresh_scarce_sample(tmp_path):
    """pages/seats.py.build_data sets show["seats_left"] (kit/sched.py's data-left, kit/ticket.py's own badge —
    both already read it, and nothing ever set it): fresh (< 90 min) AND scarce (<= 15) only. A healthy hall
    (36 free) and a stale sample (free but sampled 200 min ago) both say nothing, on the button or the ticket."""
    d = json.load(open(DATA, encoding="utf-8"))
    gen = seats._parse_at(d["generated"])
    upcoming, seen = [], set()
    for s in d["shows"]:
        if (s["date"], s["time"]) > (gen.date().isoformat(), gen.strftime("%H:%M")) and s["film"] not in seen:
            seen.add(s["film"]); upcoming.append(s)
        if len(upcoming) >= 3:
            break
    scarce, healthy, stale = upcoming
    scarce["seats"] = {"free": 8, "total": 120, "at": (gen - timedelta(minutes=20)).isoformat()}
    healthy["seats"] = {"free": 36, "total": 120, "at": (gen - timedelta(minutes=20)).isoformat()}
    stale["seats"] = {"free": 3, "total": 120, "at": (gen - timedelta(minutes=200)).isoformat()}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    out = str(tmp_path / "o")
    build.build(str(p), DISC, out, noindex=False)
    assert 'data-left="8"' in read(out, "film", scarce["film"], "index.html")
    assert "data-left=" not in read(out, "film", healthy["film"], "index.html")
    assert "data-left=" not in read(out, "film", stale["film"], "index.html")
