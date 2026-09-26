"""PREVIEW=1 python build.py: the preview on cinema.elyoxe.com must never be indexed — every page carries
noindex,nofollow and robots.txt disallows everything without advertising the sitemap. Without PREVIEW the
site stays indexable (only 404.html is noindex)."""
import os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
META = '<meta name="robots" content="noindex,nofollow">'


def pages(out):
    for d, _, fs in os.walk(out):
        for f in fs:
            if f.endswith(".html"):
                yield os.path.join(d, f)


def run(tmp, monkeypatch, env):
    if env is None: monkeypatch.delenv("PREVIEW", raising=False)
    else: monkeypatch.setenv("PREVIEW", env)
    out = str(tmp)
    build.build(DATA, DISC, out)
    return out


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


@pytest.mark.parametrize("env", [None, "0", ""])
def test_default_build_stays_indexable(tmp_path, monkeypatch, env):
    out = run(tmp_path, monkeypatch, env)
    for p in pages(out):
        html = open(p, encoding="utf-8").read()
        if os.path.basename(p) in ("404.html", "offline.html"):   # never pages to index
            continue
        assert "noindex" not in html, p
    robots = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    assert "Sitemap: https://cinema.elyoxe.com/sitemap.xml" in robots
    assert "Disallow: /\n" not in robots


def test_preview_mode_parsing():
    assert build.preview_mode({"PREVIEW": "1"}) and build.preview_mode({"PREVIEW": "true"})
    assert not build.preview_mode({}) and not build.preview_mode({"PREVIEW": "0"})
