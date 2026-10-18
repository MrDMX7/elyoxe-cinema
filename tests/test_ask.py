"""«اسأل الفيلم» (2026-10-18): the site's half (pages/ask.py: one facts file per showing film, the tab and its panel, the
lazy chunk filled with the backend's endpoint, the CSP allowing it) and the backend's pure helpers (infra/ask/src/handler.py:
question normalisation, the dialect pass, the unreadable-question guard). Never a network call or a model call here."""
import importlib.util
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("ask") / "out")
    build.build(DATA, DISC, out, modules=build.discover(only=("core", "people", "ask")))
    return out


def test_every_showing_film_has_a_facts_file_with_no_spoiler_of_its_own(site):
    d = json.load(open(DATA, encoding="utf-8"))
    showing = [fid for fid, f in d["films"].items() if f.get("status") != "archived" and any(s["film"] == fid for s in d["shows"])]
    assert showing
    for fid in showing:
        j = json.loads(read(site, "data", "ask", fid + ".json"))
        assert j["fid"] == fid and j.get("title")
        assert not {"plot", "ending", "qa"} & set(j)      # the plot is fetched by the backend, never published here
        assert all(v not in (None, [], {}, "") for v in j.values())


def test_the_film_page_carries_the_tab_the_panel_and_the_chunk(site):
    d = json.load(open(DATA, encoding="utf-8"))
    fid = d["shows"][0]["film"]
    h = read(site, "film", fid, "index.html")
    assert '<a href="#ask" data-tab="ask" class="js-only">اسأل الفيلم</a>' in h
    tabs = re.findall(r'data-tab="([a-z]+)"', h)
    assert tabs.index("ask") == tabs.index("about") + 1             # right after «عن الفيلم»
    assert f'<div class="ask" data-ask data-fid="{fid}" hidden>' in h  # shown by the chunk only
    assert h.count('class="ask-chip"') == 6 and 'maxlength="240"' in h
    chunk = re.search(r'"ask":\s*"(/assets/ask\.[0-9a-f]{10}\.js)"', h).group(1)
    js = read(site, *chunk.lstrip("/").split("/"))
    api = build.counter_config()["__ASK_API__"]
    assert api.startswith("https://") and api in js and "__ASK_API__" not in js
    assert "box.hidden = false" in js and "ask-sp" in js           # a spoiler sits behind its own <details>
    assert "/assets/ask." not in read(site, "index.html")          # film pages only


def test_the_csp_lets_the_page_reach_the_backend():
    tpl = open(os.path.join(ROOT, "infra", "template.yaml"), encoding="utf-8").read()
    api = build.counter_config()["__ASK_API__"].rstrip("/")
    csp = re.search(r"connect-src ([^;]+);", tpl).group(1)
    assert api in csp


def _handler(monkeypatch):
    monkeypatch.setenv("TABLE", "test-table")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
    src = os.path.join(ROOT, "infra", "ask", "src")
    if not os.path.exists(os.path.join(src, "lexicon.json")):
        pytest.skip("infra/ask/src/lexicon.json is written by make_system.py")
    spec = importlib.util.spec_from_file_location("ask_handler", os.path.join(src, "handler.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_question_normalisation_folds_spelling_variants(monkeypatch):
    h = _handler(monkeypatch)
    assert h.norm("شو نوع الفيلم؟") == h.norm("شو  نوع الفيلْم") == h.norm("شو نوع الفيلم")
    assert h.norm("إيش القصة") == h.norm("ايش القصه")


def test_the_dialect_pass_fixes_whole_words_only(monkeypatch):
    h = _handler(monkeypatch)
    assert h.dialect("الفيلم مو للعيال") == "الفيلم مب للعيال"
    assert h.dialect("أيه، يستاهل") == "إيه، يستاهل"
    assert h.dialect("موسيقى الفيلم") == "موسيقى الفيلم"          # «مو» inside a word is left alone


def test_an_unreadable_question_is_refused_before_any_cache_or_model(monkeypatch):
    h = _handler(monkeypatch)
    monkeypatch.setattr(h, "off", lambda: False)
    def boom(*a, **k):
        raise AssertionError("no table access for an unreadable question")
    monkeypatch.setattr(h.TABLE, "get_item", boom)
    ev = {"headers": {"origin": "https://cinema.elyoxe.com"}, "requestContext": {"http": {"method": "POST"}},
          "body": json.dumps({"fid": "street-fighter", "q": "????? ??", "lang": "ar"})}
    r = h.handler(ev, None)
    assert r["statusCode"] == 400
    ev["headers"]["origin"] = "https://evil.example"
    assert h.handler(ev, None)["statusCode"] == 403
