"""cinema_photos.py: mirroring a landscape photo per cinema (reusing posters.py's http/decode/upload
plumbing), the landscape filter, the cap, and steps/cinema_photo.py's offline guard."""
import io
import json
import os
import sys
from pathlib import Path

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cinema_photos as cph  # noqa: E402
import steps.cinema_photo as step  # noqa: E402


def _jpeg(w, h, color=(60, 90, 80)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "JPEG")
    return buf.getvalue()


def _sources(tmp_path, mapping):
    p = tmp_path / "cinema_photos.yaml"
    body = "cinemas:\n" + "".join(f'  {k}: "{v}"\n' for k, v in mapping.items())
    p.write_text(body, encoding="utf-8")
    return p


def test_mirrors_a_landscape_photo_and_attaches_it(tmp_path):
    blob = _jpeg(1600, 900)
    sources = _sources(tmp_path, {"c1": "https://chain.example/c1.jpg"})
    data = {"cinemas": {"c1": {"city": "dubai"}}}
    stats = cph.mirror(data, sources_path=sources, cache_path=tmp_path / "cp.json",
                       out_dir=tmp_path / "posters", fetch=lambda url: blob)
    photo = data["cinemas"]["c1"]["photo"]
    assert photo["w1280"].startswith("/posters/cin-c1-") and photo["w1280"].endswith("-1280.webp")
    assert photo["w640"].endswith("-640.webp")
    assert stats["downloaded"] == 1 and stats["with_photo"] == 1
    img = Image.open(tmp_path / "posters" / photo["w1280"].rsplit("/", 1)[1])
    assert img.format == "WEBP" and img.width == 1280


def test_rejects_a_portrait_source_as_not_landscape_enough(tmp_path):
    blob = _jpeg(400, 900)   # a poster-shaped image, not a cinema photo band
    sources = _sources(tmp_path, {"c1": "https://chain.example/c1.jpg"})
    data = {"cinemas": {"c1": {}}}
    stats = cph.mirror(data, sources_path=sources, cache_path=tmp_path / "cp.json",
                       out_dir=tmp_path / "posters", fetch=lambda url: blob)
    assert "photo" not in data["cinemas"]["c1"]
    assert stats["failed"] == 1


def test_no_source_means_no_photo_and_no_network(tmp_path):
    sources = _sources(tmp_path, {})
    data = {"cinemas": {"c1": {}}}
    stats = cph.mirror(data, sources_path=sources, cache_path=tmp_path / "cp.json", out_dir=tmp_path / "posters",
                       fetch=lambda url: (_ for _ in ()).throw(AssertionError("no source, must not fetch")))
    assert stats["cinemas"] == 0 and "photo" not in data["cinemas"]["c1"]


def test_second_run_reuses_the_cache_without_a_new_download(tmp_path):
    blob = _jpeg(1600, 900)
    sources = _sources(tmp_path, {"c1": "https://chain.example/c1.jpg"})
    data = {"cinemas": {"c1": {}}}
    cph.mirror(data, sources_path=sources, cache_path=tmp_path / "cp.json", out_dir=tmp_path / "posters",
              fetch=lambda url: blob)
    data2 = {"cinemas": {"c1": {}}}
    stats2 = cph.mirror(data2, sources_path=sources, cache_path=tmp_path / "cp.json", out_dir=tmp_path / "posters",
                        fetch=lambda url: (_ for _ in ()).throw(AssertionError("downloaded twice")))
    assert stats2["downloaded"] == 0 and data2["cinemas"]["c1"]["photo"]


def test_respects_the_per_run_download_cap(tmp_path):
    blob = _jpeg(1600, 900)
    sources = _sources(tmp_path, {f"c{i}": f"https://chain.example/c{i}.jpg" for i in range(5)})
    data = {"cinemas": {f"c{i}": {} for i in range(5)}}
    calls = []
    stats = cph.mirror(data, sources_path=sources, cache_path=tmp_path / "cp.json", out_dir=tmp_path / "posters",
                       fetch=lambda url: calls.append(url) or blob, cap=2)
    assert len(calls) == 2
    assert stats["downloaded"] == 2 and stats["skipped_cap"] == 3


def test_step_offline_applies_cache_but_never_downloads(tmp_path, monkeypatch):
    blob = _jpeg(1600, 900)
    sources = _sources(tmp_path, {"c1": "https://chain.example/c1.jpg"})
    monkeypatch.setattr(cph, "SOURCES_PATH", sources)
    # seed the cache with an injected fetch -- never the real network
    cph.mirror({"cinemas": {"c1": {}}}, sources_path=sources, cache_path=tmp_path / "cinema_photos.json",
              out_dir=tmp_path / "posters", fetch=lambda url: blob)

    def boom(*a, **kw):
        raise AssertionError("offline must not fetch")
    import posters as pm
    monkeypatch.setattr(pm, "_default_fetch", boom)
    data2 = {"cinemas": {"c1": {}}}
    out = step.run(data2, {"data_dir": str(tmp_path), "offline": True})
    assert data2["cinemas"]["c1"]["photo"]["w1280"].startswith("/posters/cin-c1-")
    assert out["downloaded"] == 0
