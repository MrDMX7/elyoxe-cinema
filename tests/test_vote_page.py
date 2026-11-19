"""«صوّتوا مع الربع» front end (owner 2026-11-20): the ticket's «+ للتصويت», the tray bar, and /v/?p=<id> in the app's
design, on the counter API (counter.yaml «api»; infra/counter/lambdas/vote.py)."""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

import build_app  # noqa: E402
from site_kit import Halls, load_discounts  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")


def _build(tmp_path, lang):
    out = str(tmp_path / lang)
    os.makedirs(out)
    data = json.load(open(DATA, encoding="utf-8"))
    build_app.LANG = lang
    try:
        app = build_app.App(data, load_discounts(DISC), Halls(os.path.join(ROOT, "halls.yaml")), out,
                            "/en/" if lang == "en" else "/", live=True)
        app.run()
    finally:
        build_app.LANG = "ar"
    return out, app


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def test_the_poll_page_is_a_noindex_shell(tmp_path):
    out, app = _build(tmp_path, "ar")
    h = read(out, "v", "index.html")
    assert '<meta name="robots" content="noindex">' in h and 'data-kind="vote"' in h
    for hook in ("data-poll", "data-v-opts", "data-v-who", "data-v-no", "data-v-note", "data-v-list", "data-v-share"):
        assert hook in h, hook
    assert 'class="tabbar' not in h and "data-vbar" not in h                 # a page of its own: no tab bar, no tray


def test_tickets_and_pages_carry_the_vote(tmp_path):
    out, app = _build(tmp_path, "ar")
    api = build_app.counter_api()
    assert api and build_app.VOTE_API == api
    film = read(out, "film", app.films[0], "index.html")
    assert f'<div class="pg film" data-fid="{app.films[0]}">' in film       # the ticket needs the film's id
    assert "data-tk-vote" in film and "+ للتصويت مع الربع" in film
    assert f'vote:"{api}"' in film
    for page in (film, read(out, "index.html")):
        assert re.search(r'<div class="vbar" data-vbar hidden>.*?data-vbar-send.*?data-vbar-clear', page, re.S)


def test_the_english_poll_page(tmp_path):
    out, app = _build(tmp_path, "en")
    for h in (read(out, "v", "index.html"), read(out, "film", app.films[0], "index.html")):
        body = re.sub(r"<script.*?</script>", "", h, flags=re.S)
        left = {x.strip() for x in re.findall(r"[؀-ۿ][^<>\"]*", body)} - {"العربية"}
        assert not left, left
    assert "Where shall we go?" in read(out, "v", "index.html")
    js_t = re.search(r"t:(\{.*?\})\}</script>", read(out, "v", "index.html"), re.S).group(1)
    t = json.loads(js_t)
    assert t["أنا معكم"] == "I'm in" and t["وين نروح؟"] == "Where shall we go?"


def test_the_script_speaks_to_the_api_and_parses():
    js = read(ROOT, "app", "app.js")
    for s in ('fetch(VAPI + "vote"', 'VAPI + "vote/" + pid', '"/v/?p="', "[data-poll]", "[data-vbar]", "[data-tk-vote]",
              'store.set("vote"', 'store.set("vname"', "setInterval(load, 10000)"):
        assert s in js, s
    for k in re.findall(r'tx\("([^"]+)"\)', js[js.index("صوّتوا مع الربع"):]):
        assert k in build_app.JS_KEYS, k                                     # every phrase the vote script says has its English
    assert subprocess.run(["node", "--check", os.path.join(ROOT, "app", "app.js")]).returncode == 0
