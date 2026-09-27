"""PREVIEW=1 python build.py: the preview on cinema.elyoxe.com must never be indexed — every page carries
noindex,nofollow and robots.txt disallows everything without advertising the sitemap. Without PREVIEW the
site stays indexable (only 404.html is noindex)."""
import json, os, sys
from datetime import date

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
from pages import seasons  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
META = '<meta name="robots" content="noindex,nofollow">'


def pages(out):
    for d, _, fs in os.walk(out):
        for f in fs:
            if f.endswith(".html"):
                yield os.path.join(d, f)


def run(tmp, monkeypatch, env, generated=None):
    """Builds the fixtures; `generated` freezes the build's clock (site.today) — the only clock a page reads."""
    if env is None: monkeypatch.delenv("PREVIEW", raising=False)
    else: monkeypatch.setenv("PREVIEW", env)
    data = DATA
    if generated:
        d = json.load(open(DATA, encoding="utf-8"))
        d["generated"] = generated
        data = os.path.join(str(tmp), "_data.json")
        os.makedirs(str(tmp), exist_ok=True)
        json.dump(d, open(data, "w", encoding="utf-8"), ensure_ascii=False)
    out = os.path.join(str(tmp), "o")
    build.build(data, DISC, out)
    return out


def build_day(generated):
    return date.fromisoformat((generated or json.load(open(DATA, encoding="utf-8"))["generated"])[:10])


def test_preview_env_marks_every_page_noindex(tmp_path, monkeypatch):
    out = run(tmp_path, monkeypatch, "1")
    ps = list(pages(out))
    assert len(ps) > 20
    for p in ps:
        html = open(p, encoding="utf-8").read()
        assert html.count(META) == 1, p
        assert html.count('name="robots"') == 1, p
    robots = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    assert "Disallow: /\n" in robots
    assert "Sitemap" not in robots and "Allow:" not in robots


@pytest.mark.parametrize("env,generated", [(None, None), ("0", None), ("", None),
                                           (None, "2026-09-25T18:00:00+04:00"), (None, "2026-07-20T18:00:00+04:00")])
def test_default_build_stays_indexable(tmp_path, monkeypatch, env, generated):
    out = run(tmp_path, monkeypatch, env, generated)
    in_summer = seasons.summer_active(build_day(generated))   # the same clock the build used
    for p in pages(out):
        html = open(p, encoding="utf-8").read()
        if os.path.basename(p) in ("404.html", "offline.html"):   # never pages to index
            continue
        if os.path.relpath(p, out).replace(os.sep, "/") in ("summer/index.html", "en/summer/index.html"):
            # /summer/ is indexed in July–August only; outside them it waits at its URL, noindex
            assert ("noindex" in html) is (not in_summer), p
            continue
        if "no confirmed discount for this card" in html or "ما لقينا خصم مؤكد لهالبطاقة" in html:
            continue   # an unconfirmed card's old URL: a noindex note by design (test_hourly_safe.py)
        if "No chain-confirmed events yet" in html or "ما عندنا فعاليات مؤكدة" in html:
            continue   # an honestly-empty /events/ hub: noindex by design (task-2 fix round 2)
        if "We have no reliable number today" in html or "ما عندنا رقم موثوق اليوم" in html:
            continue   # a /q/ question today's data cannot answer: kept at its URL, noindex by design (task-5 fix round 1)
        assert "noindex" not in html, p
    robots = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    assert "Sitemap: https://cinema.elyoxe.com/sitemap.xml" in robots
    assert "Disallow: /\n" not in robots


def test_preview_mode_parsing():
    assert build.preview_mode({"PREVIEW": "1"}) and build.preview_mode({"PREVIEW": "true"})
    assert not build.preview_mode({}) and not build.preview_mode({"PREVIEW": "0"})
