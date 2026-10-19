"""The app (app/build_app.py, owner 2026-10-18): in live mode it writes the home, every showing film and every cinema at
the old URLs, indexable, with the film's JSON-LD, the show table the ticket reads, and the quiet footer; deploy.sh runs
it after build.py, and a failure there leaves the old pages to publish."""
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))
import build_app  # noqa: E402
from site_kit import Halls, load_discounts  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("app") / "out")
    os.makedirs(out)
    open(os.path.join(out, "keep.html"), "w").write("old page")     # the old build's other pages stay
    data = json.load(open(DATA, encoding="utf-8"))
    app = build_app.App(data, load_discounts(DISC), Halls(os.path.join(ROOT, "halls.yaml")), out, "/", live=True)
    app.run()
    return out, app


def test_live_writes_over_the_old_urls_and_keeps_the_rest(live):
    out, app = live
    assert read(out, "keep.html") == "old page"
    assert app.films and os.path.exists(os.path.join(out, "film", app.films[0], "index.html"))
    cid = app.cins[0]
    city = app.k.cinemas[cid].get("city")
    assert os.path.exists(os.path.join(out, city, cid, "index.html"))
    assert not os.path.exists(os.path.join(out, "f")) and not os.path.exists(os.path.join(out, "c"))


def test_live_pages_are_indexable_with_their_canonical_and_film_json_ld(live):
    out, app = live
    fid = app.films[0]
    h = read(out, "film", fid, "index.html")
    assert "noindex" not in h
    assert f'<link rel="canonical" href="https://cinema.elyoxe.com/film/{fid}/">' in h
    assert 'hreflang="en"' in h
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S).group(1))
    movie = next(x for x in ld["@graph"] if x["@type"] == "Movie")
    assert movie["url"].endswith(f"/film/{fid}/")
    assert '<script type="application/json" id="shows">' in h          # the ticket's table
    assert '<footer class="foot">' in h and 'href="/en/"' in h and 'href="/cards/"' in h
    # every link inside points at a live URL
    assert not re.search(r'href="/(f|c)/', h)


def test_the_home_is_the_approved_merge(live):
    out, _ = live
    h = read(out, "index.html")
    assert 'data-pager' in h and 'data-pane="0"' in h and 'data-pane="1"' in h   # الأفلام / السينمات
    assert 'data-soon' in h and 'id="soon"' in h                               # «يبدأ قريب منك»
    assert 'data-chips' in h and 'class="grid"' in h


def test_twelve_hour_times_and_the_dirham_sign():
    assert build_app.t12("16:25") == ("4:25", "مساء")
    assert build_app.t12("00:45") == ("12:45", "بالليل")
    assert build_app.t12("10:00") == ("10:00", "الصبح")
    assert build_app.ap("16:25") == "م" and build_app.ap("10:00") == "ص"
    assert 'aria-label="درهم"' in build_app.DIRHAM


def test_deploy_builds_the_app_after_the_old_site_and_falls_back_to_it():
    sh = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
    i_old, i_app = sh.index('"$PY" build.py --data data/latest.json'), sh.index('"$PY" app/build_app.py')
    assert i_old < i_app
    line = sh[i_app - 60: sh.index("\n", i_app) + 200]
    assert "--live" in line and "||" in line                              # a failed app build publishes the old pages


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="node not installed")
def test_the_app_script_parses():
    r = subprocess.run(["node", "--check", os.path.join(ROOT, "app", "app.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_chain_wears_its_own_icon(live):
    """Owner 2026-10-19: the chain's logo beside each cinema — its app icon from app/logos/, content-hashed."""
    out, app = live
    chains = {c["chain"] for c in app.k.cinemas.values()}
    assert chains <= set(app.logos), chains - set(app.logos)
    for url in app.logos.values():
        assert re.fullmatch(r"/assets/logos/[a-z]+\.[0-9a-f]{10}\.webp", url)
        assert os.path.getsize(os.path.join(out, *url.lstrip("/").split("/"))) < 8000
    cid = app.cins[0]
    h = read(out, app.k.cinemas[cid]["city"], cid, "index.html")
    assert f'<span class="cc-logo lg img ch-{app.k.cinemas[cid]["chain"]}"><img src="{app.logos[app.k.cinemas[cid]["chain"]]}"' in h
    assert '"logos":{' in h.replace("logos:{", '"logos":{')        # the script's marks read window.APP.logos
