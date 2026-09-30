"""pages/voteadd.py + src/js/voteadd.js (round-3 follow-up, 2026-09-30): /v/ «أي واحد؟» was live but
reachable from nowhere on the site. This covers the entry points added to fix that -- the ticket's own
«اسأل القروب: أي واحد؟» / «+ للتصويت» toggle (kit/ticket.py + pages/voteadd.py + src/js/ticket.js), /v/'s
own «أرسل للقروب» resend and per-option film links (src/js/vote.js), and the Thursday push opt-in wired
onto /coming/ (pages/coming.py + src/js/push.js). Python-only: the bundle text is grepped for the
client logic's presence and scope (which pages load which chunk), not executed -- src/js/vote.js and
src/js/push.js's own Node-run behaviour stays with tests/test_js.py's harness."""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "tests", "fixtures", "coming_sample.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
MODULES = build.discover(only=("core", "coming", "vote", "voteadd"))


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def _build(tmp_path):
    o = str(tmp_path / "out")
    build.build(DATA, DISC, o, modules=MODULES)
    return o


def _tk_act(html):
    return html[html.index('<div class="tk-act">'):html.index("</aside>", html.index('<div class="tk-act">'))]


def test_ticket_carries_a_vote_add_button_next_to_the_share_link(tmp_path):
    o = _build(tmp_path)
    tk = _tk_act(read(o, "film", "heart-of-the-beast", "index.html"))
    assert tk.index("data-tk-share") < tk.index("data-v-add")
    assert 'data-v-fid="heart-of-the-beast"' in tk
    for attr in ("data-v-city", "data-v-date", "data-v-key", "data-v-title", "data-v-cin", "data-v-time"):
        assert f'{attr}="' in tk
    assert "اسأل القروب: أي واحد؟" in tk


def test_ticket_aside_itself_carries_the_shows_vote_identity(tmp_path):
    """kit/ticket.py: data-fid/data-city/data-d/data-key on <aside> -- src/js/ticket.js's fillTicket
    keeps the button's own data-v-* in step with these whenever a different time is tapped."""
    o = _build(tmp_path)
    film = read(o, "film", "heart-of-the-beast", "index.html")
    m = re.search(r'<aside class="ticket"[^>]*>', film)
    assert m
    tag = m.group(0)
    assert 'data-fid="heart-of-the-beast"' in tag
    for attr in ("data-city", "data-d", "data-key"):
        assert f'{attr}="' in tag


def _ct(html):
    return json.loads(re.search(r"<script>window\.CT = (.*?);</script>", html).group(1))


def test_voteadd_js_is_a_lazy_chunk_loaded_on_every_page_kind(tmp_path):
    """LAZY_JS + page_js["*"] (the pages/appfeel.py/search.py pattern): the ticket isn't confined to one
    page kind, but build.py's JS_WARN_GZ budget counts only the eager main bundle, so this stays a lazy
    chunk (CT.chunks["voteadd"]) everywhere rather than landing in it -- an early eager version of this
    file pushed the fixture bundle past the warning line (round-3 review)."""
    o = _build(tmp_path)
    home_ct, film_ct = _ct(read(o, "index.html")), _ct(read(o, "film", "heart-of-the-beast", "index.html"))
    assert "voteadd" in home_ct.get("chunks", {}) and "voteadd" in film_ct.get("chunks", {})
    js = read(o, *home_ct["chunks"]["voteadd"].lstrip("/").split("/"))
    assert "data-v-add" in js and "v-bar" in js
    main = re.search(r'/assets/cinema\.[a-z0-9]+\.js', read(o, "index.html")).group(0)
    main_js = read(o, *main.lstrip("/").split("/"))
    # ticket.js (eager, core) does reference the [data-v-add] selector to keep its attrs in step -- what
    # must NOT be eager is voteadd.js's own body: the queue, the bar, the toggle/WhatsApp-message logic
    assert "v-bar" not in main_js and "ensureBar" not in main_js and "waMsg" not in main_js


def test_vote_page_has_a_resend_button_and_per_option_film_links(tmp_path):
    o = _build(tmp_path)
    v = read(o, "v", "index.html")
    assert 'data-v-resend' in v and 'data-v-act' in v and "أرسل للقروب" in v
    m = re.search(r'/assets/vote\.[a-z0-9]+\.js', v)
    assert m
    js = read(o, *m.group(0).lstrip("/").split("/"))
    assert "v-open" in js and "filmHref" in js and "resendBtn" in js


def test_coming_masthead_carries_a_hidden_push_row_with_its_own_chunk(tmp_path):
    o = _build(tmp_path)
    c = read(o, "coming", "index.html")
    m = re.search(r'<p class="cs-mast-push"[^>]*>', c)
    assert m and "hidden" in m.group(0)
    assert "data-push-btn" in c and "ذكّرني بالخميس" in c
    chunk = re.search(r'/assets/push\.[a-z0-9]+\.js', c)
    assert chunk
    home = read(o, "index.html")
    assert "/assets/push." not in home  # push.js loads only on /coming/, like vote's chunk on /v/


def test_coming_push_chunk_is_a_lazy_chunk_not_the_main_bundle(tmp_path):
    o = _build(tmp_path)
    home = read(o, "index.html")
    m = re.search(r'/assets/cinema\.[a-z0-9]+\.js', home)
    js = read(o, *m.group(0).lstrip("/").split("/"))
    assert "__COUNTER_API__" not in js  # push.js's own placeholder never leaks into the shared bundle
