"""Wave 0 integration (MASTER-PLAN §5.1 «Shipping Wave 0»): what only exists once the four packages sit together.

#32's page half. W0-P4 routes a not-a-film session (Roxy's «Immersive Dining - …») to data["event_shows"] and out of
films; W0-P2 owns pages/hubs.py. Until /events/ reads event_shows, the dining event was on no page at all (it used
to be a wrong "film"). The patch W0-P4 handed over (w0-p4-events-hubs.patch) lists each upcoming session under its
event, with the cinema, the day, its times and the chain's own booking link."""
import copy
import json
import os

import pytest

import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
DATA = os.path.join(ROOT, "tests", "fixtures", "coming_sample.json")
MODULES = build.discover(only=("core", "coming", "hubs"))
BOOK = "https://www.theroxycinemas.com/booking/hoshena-2030"
DINING = {"label": "immersive dining", "name_ar": "عشاء غامر", "name_en": "Immersive Dining", "kind": "dining",
          "fids": ["immersive-dining-iv-elements-of-hoshena"], "chains": ["roxy"], "cities": ["dubai"]}


def session(date, time, book=BOOK):
    return {"cinema": "roxy-city-walk", "title": "Immersive Dining - IV Elements of Hoshena", "event": "immersive dining",
            "date": date, "time": time, "book": book}


def build_with(tmp_path, sessions, generated=None):
    d = json.load(open(DATA, encoding="utf-8"))          # generated 2026-09-25 18:00
    d["events"] = list(d.get("events") or []) + [copy.deepcopy(DINING)]
    d["event_shows"] = sessions
    if generated:
        d["generated"] = generated
    p = tmp_path / "data.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = str(tmp_path / "out")
    build.build(str(p), DISC, o, modules=MODULES)
    read = lambda *parts: open(os.path.join(o, *parts), encoding="utf-8").read()
    return read


def test_events_page_lists_upcoming_dining_sessions_with_their_booking_link(tmp_path):
    read = build_with(tmp_path, [session("2026-09-25", "17:00"), session("2026-09-25", "21:30"),
                                 session("2026-09-25", "20:00"), session("2026-09-26", "19:00")])
    ar, en = read("events", "index.html"), read("en", "events", "index.html")
    assert "عشاء غامر" in ar and "Immersive Dining" in en
    assert f'href="{BOOK}" rel="noopener nofollow" target="_blank"' in ar
    assert '<bdi lang="en">Immersive Dining - IV Elements of Hoshena</bdi>' in ar   # a Latin title on an Arabic page
    assert "<span>20:00 21:30</span>" in ar and "<span>19:00</span>" in ar         # grouped by day, sorted
    assert "17:00" not in ar                                                       # started before the build
    assert "/film/immersive-dining-iv-elements-of-hoshena/" not in ar             # never a film page
    assert "K-Fest" in ar or "مهرجان كي-فست" in ar                                 # the film event stays
    assert "noindex" not in ar


def test_a_session_without_its_own_link_falls_back_to_the_chain(tmp_path):
    read = build_with(tmp_path, [session("2026-09-25", "20:00", book=None)])
    ar = read("events", "index.html")
    assert "عشاء غامر" in ar and 'href="None"' not in ar and 'href=""' not in ar


def test_an_event_whose_sessions_have_all_passed_leaves_the_page(tmp_path):
    read = build_with(tmp_path, [session("2026-09-25", "17:00")])
    ar = read("events", "index.html")
    assert "عشاء غامر" not in ar and "Hoshena" not in ar
    assert "K-Fest" in ar or "مهرجان كي-فست" in ar
