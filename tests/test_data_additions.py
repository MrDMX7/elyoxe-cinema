"""Phase 1 data additions: posters, trailers, genres, family/kids flags, show lang/subs, ends,
cinema coordinates, per-chain ad offset, confirmed-only cards. Offline — never the network."""
import io
import json
import sys
from pathlib import Path

import pytest
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import discounts  # noqa: E402
import enrich as enrich_mod  # noqa: E402
import genres  # noqa: E402
import normalize  # noqa: E402
import posters  # noqa: E402
from readers.common import lang_key, subs_keys, youtube_id  # noqa: E402

NOW = "2026-09-26T09:00:00+04:00"


# ---------------------------------------------------------------- common helpers
def test_lang_key_and_subs():
    assert lang_key("English") == "en"
    assert lang_key("ENGLISH") == "en"
    assert lang_key("EN") == "en"
    assert lang_key("Localization.Language.Arabic") == "ar"
    assert lang_key("Malayalam") == "ml"
    assert lang_key("Tagalog") == "tl"
    assert lang_key("Klingon") is None
    assert lang_key(None) is None
    assert subs_keys("Arabic | English ") == ["ar", "en"]
    assert subs_keys("Arabic & English") == ["ar", "en"]
    assert subs_keys(["AR", None, "AR"]) == ["ar"]
    assert subs_keys("") == []


def test_youtube_id():
    assert youtube_id("https://www.youtube.com/watch?v=bdPnr4mJoIU") == "bdPnr4mJoIU"
    assert youtube_id("https://www.youtube.com/watch?v=kiSL6QIqLqA&t=3s") == "kiSL6QIqLqA"
    assert youtube_id("https://youtu.be/KvzlWyV8d5s") == "KvzlWyV8d5s"
    assert youtube_id("https://www.youtube.com/embed/KvzlWyV8d5s?rel&#x3D;0") == "KvzlWyV8d5s"
    assert youtube_id("bdPnr4mJoIU") == "bdPnr4mJoIU"
    assert youtube_id("https://m.boxoffice.media/mp4/358931_high.mp4") is None
    assert youtube_id("") is None
    assert youtube_id("https://www.youtube.com/user/voxcinemas") is None


# ---------------------------------------------------------------- genres
def test_genre_keys_map_chain_and_wikidata_labels():
    assert genres.genre_keys("Action,Adventure,Drama") == ["action", "adventure", "drama"]
    assert genres.genre_keys(["Drama | Comedy"]) == ["drama", "comedy"]
    assert genres.genre_keys(["Survival Thriller"]) == ["adventure", "thriller"]
    assert genres.genre_keys(["superhero film", "computer-animated film", "science fiction film"]) == [
        "action", "animation", "scifi"]
    assert genres.genre_keys(["Biography"]) == ["drama"]
    assert genres.genre_keys(["Musical"]) == ["music"]
    assert genres.genre_keys(["Award winner"]) == ["other"]  # "war" never inside "award"
    assert genres.genre_keys(["Action", "Nonsense"]) == ["action"]
    assert genres.genre_keys(None) == []
    assert genres.genre_keys(["action", "scifi"]) == ["action", "scifi"]  # idempotent on keys


def test_genres_table_has_the_fixed_key_set():
    assert set(genres.GENRES) == {"action", "adventure", "animation", "comedy", "crime", "drama", "family",
                                  "fantasy", "horror", "romance", "scifi", "thriller", "documentary",
                                  "music", "sport", "war", "other"}
    for key, (ar, en) in genres.GENRES.items():
        assert ar and en


# ---------------------------------------------------------------- ratings, flags
@pytest.mark.parametrize("raw,want", [
    ("G", "G"), ("PG", "PG"), ("PG13", "PG13"), ("PG-13", "PG13"), ("PG 13", "PG13"), ("pg15", "PG15"),
    ("15+", "15+"), ("15", "15+"), ("18+", "18+"), ("18TC", "18+"), ("TBA-PG15", "PG15"), ("TBA", None),
    (None, None), ("", None), ("XYZ", None),
])
def test_uae_rating(raw, want):
    assert normalize.uae_rating(raw) == want


def test_family_and_kids_flags():
    assert normalize.derive_flags("G", ["animation"]) == {"family": True, "kids": True}
    assert normalize.derive_flags("PG", ["family", "comedy"]) == {"family": True, "kids": True}
    assert normalize.derive_flags("PG", ["action"]) == {"family": True, "kids": False}
    assert normalize.derive_flags("PG13", ["animation"]) == {"family": True, "kids": False}
    assert normalize.derive_flags("PG15", ["animation"]) == {"family": False, "kids": False}
    assert normalize.derive_flags("15+", []) == {"family": False, "kids": False}
    assert normalize.derive_flags(None, ["animation"]) == {"family": False, "kids": False}


# ---------------------------------------------------------------- ends
def test_end_time_adds_offset_and_runtime_and_wraps_midnight():
    assert normalize.end_time("2026-09-26", "19:00", 100, 15) == "20:55"
    assert normalize.end_time("2026-09-26", "23:30", 101, 15) == "01:26"
    assert normalize.end_time("2026-09-26", "19:00", None, 15) is None
    assert normalize.end_time("2026-09-26", "19:00", 0, 15) is None


def test_chains_yaml_has_an_offset_for_every_chain():
    cfg = normalize.load_chains()
    for chain in ("vox", "star", "reel", "novo", "roxy", "cineroyal", "cinemacity"):
        assert normalize.ad_offset(cfg, chain) == 15
    assert normalize.ad_offset(cfg, "no-such-chain") == 15


# ---------------------------------------------------------------- merge + finalize
def _show(**kw):
    s = {"cinema": "vox-a", "film_title": "Heart of the Beast", "film_lang": "English", "film_rating": "PG13",
         "runtime": 101, "date": "2026-09-26", "time": "23:30", "hall": "Standard", "hall_label": "Standard",
         "prices": None, "book": "https://x"}
    s.update(kw)
    return s


def _cinema(cid, chain):
    return {"id": cid, "chain": chain, "name": cid, "name_ar": None, "city": "dubai", "mall": cid,
            "address": "", "maps": None, "lat": None, "lng": None}


def test_merge_folds_film_extras_and_keeps_show_lang_subs_and_ends():
    results = {
        "vox": {"cinemas": [_cinema("vox-a", "vox")], "shows": [
            _show(film_poster="https://a/p_small.jpg", film_trailer="https://www.youtube.com/watch?v=bdPnr4mJoIU",
                  film_genres=["Action"], lang="en", subs=["ar"])]},
        "star": {"cinemas": [_cinema("star-b", "star")], "shows": [
            _show(cinema="star-b", time="20:00", runtime=None, film_poster="https://b/p_big.jpg",
                  film_genres=["Adventure,Thriller"])]},
    }
    data = normalize.merge(results, None, NOW, aliases={})
    film = data["films"]["heart-of-the-beast"]
    assert film["poster_src"] == ["https://a/p_small.jpg", "https://b/p_big.jpg"]
    assert film["trailer"] == "bdPnr4mJoIU"
    assert film["genres"] == ["action", "adventure", "thriller"]
    vox_show = next(s for s in data["shows"] if s["cinema"] == "vox-a")
    star_show = next(s for s in data["shows"] if s["cinema"] == "star-b")
    assert vox_show["lang"] == "en" and vox_show["subs"] == ["ar"]
    assert vox_show["ends"] == "01:26"
    assert "lang" not in star_show and "subs" not in star_show   # never guessed
    assert "ends" not in star_show                                  # its own runtime unknown here
    assert not any(k.startswith("film_") for s in data["shows"] for k in s)
    normalize.finalize(data, cinema_meta={})
    assert star_show["ends"] == "21:56"                             # film runtime 101 + 15
    assert data["chains"]["vox"]["ad_offset_min"] == 15
    assert film["family"] is True and film["kids"] is False
    assert film["rating"] == "PG13"


def test_merge_keeps_previous_poster_when_no_candidate_this_run():
    prev = {"films": {"heart-of-the-beast": {"title": "Heart of the Beast", "poster": "/posters/x-342.webp",
                                             "poster_2x": "/posters/x-684.webp", "poster_color": "#aa3311",
                                             "trailer": "bdPnr4mJoIU"}}}
    data = normalize.merge({"vox": {"cinemas": [_cinema("vox-a", "vox")], "shows": [_show()]}}, prev, NOW,
                           aliases={})
    film = data["films"]["heart-of-the-beast"]
    assert film["poster"] == "/posters/x-342.webp"
    assert film["poster_color"] == "#aa3311"
    assert film["trailer"] == "bdPnr4mJoIU"


def test_finalize_attaches_coordinates_and_maps_link():
    data = {"chains": {}, "films": {}, "shows": [],
            "cinemas": {"vox-a": _cinema("vox-a", "vox"), "star-b": dict(_cinema("star-b", "star"), lat=24.1, lng=55.7)}}
    meta = {"vox-a": {"lat": 25.1188, "lng": 55.199, "coord_source": "vox cinema page"}}
    normalize.finalize(data, cinema_meta=meta)
    a = data["cinemas"]["vox-a"]
    assert (a["lat"], a["lng"], a["coord_source"]) == (25.1188, 55.199, "vox cinema page")
    assert a["maps"] == "https://www.google.com/maps/search/?api=1&query=25.1188,55.199"
    assert data["cinemas"]["star-b"]["maps"].endswith("query=24.1,55.7")


# ---------------------------------------------------------------- coordinates for every real cinema
def _real_cinema_ids():
    ids = set()
    for p in list((ROOT / "fixtures").glob("*.json")) + [ROOT / "data" / "latest.json"]:
        if not p.exists() or p.name == "sample_latest.json":
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        cin = d.get("cinemas") or {}
        ids |= set(cin) if isinstance(cin, dict) else {c["id"] for c in cin}
    return ids


def test_every_real_cinema_has_coordinates_in_cinemas_yaml():
    meta = normalize.load_cinema_meta()
    ids = _real_cinema_ids()
    assert len(ids) >= 60
    missing = sorted(cid for cid in ids if not (meta.get(cid) or {}).get("lat") or not meta[cid].get("lng"))
    assert not missing, f"cinemas without lat/lng in cinemas.yaml: {missing}"
    for cid in ids:
        m = meta[cid]
        assert 22.0 < m["lat"] < 26.5 and 51.0 < m["lng"] < 56.6, cid
        assert m.get("coord_source"), f"{cid} has no coord_source"


# ---------------------------------------------------------------- posters
def _jpeg(w, h, color=(200, 30, 40)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "JPEG")
    return buf.getvalue()


def test_posters_pick_largest_portrait_and_write_webp(tmp_path):
    blobs = {"https://a/small.jpg": _jpeg(190, 300), "https://a/big.jpg": _jpeg(400, 630),
             "https://a/hero.jpg": _jpeg(1470, 709)}
    data = {"films": {"f1": {"title": "F", "poster_src": list(blobs)}}}
    stats = posters.mirror(data, cache_path=tmp_path / "posters.json", out_dir=tmp_path / "posters",
                           fetch=lambda url: blobs[url])
    f = data["films"]["f1"]
    assert f["poster"].startswith("/posters/f1-") and f["poster"].endswith("-342.webp")
    assert f["poster_2x"].endswith("-684.webp")
    assert f["poster_color"].startswith("#") and len(f["poster_color"]) == 7
    assert "poster_src" not in f
    name = f["poster"].rsplit("/", 1)[1]
    img = Image.open(tmp_path / "posters" / name)
    assert img.format == "WEBP" and img.width == 342
    assert Image.open(tmp_path / "posters" / f["poster_2x"].rsplit("/", 1)[1]).width == 684
    cache = json.loads((tmp_path / "posters.json").read_text(encoding="utf-8"))
    assert cache["films"]["f1"]["src"] == "https://a/big.jpg"
    assert stats["with_poster"] == 1
    # second run: nothing downloaded again
    data2 = {"films": {"f1": {"title": "F", "poster_src": list(blobs)}}}
    posters.mirror(data2, cache_path=tmp_path / "posters.json", out_dir=tmp_path / "posters",
                   fetch=lambda url: (_ for _ in ()).throw(AssertionError("downloaded twice")))
    assert data2["films"]["f1"]["poster"] == f["poster"]


def test_poster_download_failure_means_no_poster_not_a_crash(tmp_path):
    def boom(url):
        raise OSError("connection reset")
    data = {"films": {"f1": {"title": "F", "poster_src": ["https://a/x.jpg"]},
                      "f2": {"title": "G", "poster_src": ["https://a/notimage.jpg"]}}}
    posters.mirror(data, cache_path=tmp_path / "p.json", out_dir=tmp_path / "posters",
                   fetch=lambda u: boom(u) if u.endswith("x.jpg") else b"<html>nope</html>")
    for fid in ("f1", "f2"):
        assert data["films"][fid].get("poster") is None
        assert "poster_src" not in data["films"][fid]


def test_dominant_color_skips_grey():
    img = Image.new("RGB", (100, 100), (128, 128, 128))
    for x in range(30):
        for y in range(100):
            img.putpixel((x, y), (20, 90, 200))
    c = posters.dominant_color(img)
    rgb = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    assert all(abs(a - b) <= 8 for a, b in zip(rgb, (20, 90, 200))), c
    assert posters.dominant_color(Image.new("RGB", (50, 50), (120, 120, 120))) is None


def test_upload_is_a_noop_when_bucket_missing(tmp_path, capsys):
    class NoBucket:
        def head_bucket(self, **kw):
            raise posters.ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket")
    n = posters.upload(cache_path=tmp_path / "p.json", out_dir=tmp_path, bucket="nope", client=NoBucket())
    assert n == 0
    assert "does not exist" in capsys.readouterr().out


# ---------------------------------------------------------------- enrich: trailer + genres
def test_enrich_trailer_from_wikidata_only_when_chain_has_none(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({
        "a": {"ids": {"qid": "Q1", "genres": {"en": ["horror film"], "ar": []}}, "ids_status": "found"},
        "b": {"ids": {"qid": "Q2", "genres": {"en": [], "ar": []}}, "ids_status": "found"},
    }), encoding="utf-8")
    calls = []

    def fake_trailer(qid):
        calls.append(qid)
        return "dQw4w9WgXcQ"
    monkeypatch.setattr(enrich_mod, "_wikidata_trailer", fake_trailer)
    monkeypatch.setattr(enrich_mod, "_rt_ratings", lambda *a, **k: None)
    data = {"films": {"a": {"title": "A", "genres": ["thriller"]}, "b": {"title": "B", "trailer": "bdPnr4mJoIU"}}}
    enrich_mod.enrich(data, cache_path=str(cache))
    assert data["films"]["a"]["trailer"] == "dQw4w9WgXcQ"
    assert data["films"]["a"]["genres"] == ["thriller", "horror"]
    assert data["films"]["b"]["trailer"] == "bdPnr4mJoIU"
    assert calls == ["Q1"]


def test_wikidata_ids_carry_p1651(monkeypatch):
    ent = {"Q5": {"claims": {"P1651": [{"mainsnak": {"datavalue": {"value": "dQw4w9WgXcQ"}}}]},
                  "labels": {}, "sitelinks": {}}}
    monkeypatch.setattr(enrich_mod, "_wikidata_entities", lambda ids, props="labels|claims": ent if "Q5" in ids else {})
    assert enrich_mod._ids_for_qid("Q5")["trailer"] == "dQw4w9WgXcQ"


# ---------------------------------------------------------------- cards
RULES = {
    "star": {"fazaa": {"type": "percent", "value": 20, "confidence": "official", "valid_until": "2027-01-01"},
             "esaad": {"type": "percent", "value": 20, "confidence": "third-party"},
             "fab": {"type": "percent", "value": 10, "confidence": "official", "valid_until": "2026-01-01"}},
    "vox": {"homat": {"status": "none_found", "confidence": "official"},
            "enbd": {"type": "bogo", "confidence": "official"},
            "fab": {"type": "percent", "value": 5, "confidence": "unconfirmed"}},
}


def test_confirmed_cards_only_official_unexpired_offers():
    assert discounts.confirmed_cards(RULES, "2026-09-26") == ["enbd", "fazaa"]


def test_apply_ignores_non_official_rules():
    price, note = discounts.apply(50.0, "star", "Standard", "esaad", RULES, today="2026-09-26")
    assert price is None and note == discounts.NO_CARD_AR
    price, _ = discounts.apply(50.0, "star", "Standard", "fazaa", RULES, today="2026-09-26")
    assert price == 40.0


def test_real_discounts_have_confirmed_cards():
    cards = discounts.confirmed_cards(discounts.load()["rules"], "2026-09-26")
    assert "fazaa" in cards and "esaad" in cards
    assert all(c in {x["id"] for x in discounts.cards()} for c in cards)


# ---------------------------------------------------------------- readers: what each payload states
def test_star_extras_and_show_lang():
    from readers import star
    movie = {"md_thumbnail_url": "https://star-image.starcinemas.ae/https://star-image.starcinemas.ae/S3/uploads/gallery/x.jpg",
             "trailer_array": [{"mt_link": "https://www.youtube.com/watch?v=kiSL6QIqLqA&t=3s"}],
             "genre_name": "Action,Fantasy,Mystery ,Thriller"}
    ex = star.movie_extras(movie)
    assert ex["film_poster"] == "https://star-image.starcinemas.ae/S3/uploads/gallery/x.jpg"
    assert ex["film_trailer"] == "kiSL6QIqLqA"
    assert ex["film_genres"] == ["Action", "Fantasy", "Mystery", "Thriller"]
    assert star.star_image("S3/uploads/gallery/y.jpg") == "https://star-image.starcinemas.ae/S3/uploads/gallery/y.jpg"
    assert star.show_lang({"movie_lang_iso_2": "EN", "sub_lang_1_iso_2": "AR", "sub_lang_2_iso_2": None}) == {
        "lang": "en", "subs": ["ar"]}
    assert star.show_lang({}) == {}


def test_vox_movie_page_extras():
    from readers import vox
    html = """<img class="poster" src="https://assets.voxcinemas.com/posters/P_1.jpg" width="480" height="686">
    <div class="trailer"><iframe src="https://www.youtube.com/embed/KvzlWyV8d5s?rel&#x3D;0"></iframe></div>
    <aside><p><strong>Genre:</strong> Action, Comedy</p><p><strong>Language:</strong> Arabic</p>
    <p><strong>Subtitle(s):</strong> English</p></aside>"""
    assert vox.movie_extras(html) == {"film_poster": "https://assets.voxcinemas.com/posters/P_1.jpg",
                                      "film_trailer": "KvzlWyV8d5s", "film_genres": ["Action", "Comedy"],
                                      "lang": "ar", "subs": ["en"]}
    assert vox.movie_extras("<html></html>") == {}


def test_roxy_movie_page_extras():
    from readers import roxy
    html = ('<script type="application/ld+json">{"@type":"Movie","image":"https://www.theroxycinemas.com/p.jpg",'
            '"genre":"Action, Adventure"}</script><a class="trailer-btn" data-link="https://www.youtube.com/watch?v=KvzlWyV8d5s">'
            '<p>Language: English</p><p>Subtitles: Arabic</p>')
    assert roxy.movie_extras(html) == {"film_poster": "https://www.theroxycinemas.com/p.jpg",
                                       "film_genres": ["Action", "Adventure"], "film_trailer": "KvzlWyV8d5s",
                                       "lang": "en", "subs": ["ar"]}


def test_reel_novo_cineroyal_cinemacity_extras():
    from readers import cinemacity, cineroyal, novo, reel
    ex = reel.film_extras({"ID": "HO1", "TrailerUrl": "https://www.youtube.com/watch?v=Uu2QK9Z9X5E",
                           "GenreId": "01", "GenreId2": "09", "Language": " Hindi\r", "SubTitle": " Arabic | English "},
                          {"01": "Action"})
    assert ex == {"film_poster": reel.POSTER.format("HO1"), "film_trailer": "Uu2QK9Z9X5E",
                  "film_genres": ["Action"], "lang": "hi", "subs": ["ar", "en"]}
    ex = novo.movie_extras({"movie_title": "Enna Vilai (Tamil)", "movie_image_url": "https://n/p.jpg",
                            "movie_trailer_link": "", "movie_genre": [{"genre_name": "Drama"}],
                            "language": {"lang_name": "Tamil"}, "subtitle_language": {"lang_name": "Arabic & English"}})
    assert ex == {"film_poster": "https://n/p.jpg", "film_genres": ["Drama"], "lang": "ta", "subs": ["ar", "en"]}
    assert "lang" not in novo.movie_extras({"movie_title": "Sacrifice", "language": None})
    ex = cineroyal.film_extras({"poster5": "https://s3/p5.jpg", "poster2": "https://s3/p2.jpg",
                                "youTubevideoId": "bdPnr4mJoIU", "genere": "Action,Thriller"}, None)
    assert ex == {"film_poster": "https://s3/p5.jpg", "film_trailer": "bdPnr4mJoIU",
                  "film_genres": ["Action", "Thriller"]}
    ex = cinemacity.movie_extras({"poster": "https://img/p.jpg", "genres": "Action, Adventure",
                                  "locale": {"sdTrailers": [{"url": "https://m.boxoffice.media/mp4/1_high.mp4"}]}})
    assert ex == {"film_poster": "https://img/p.jpg", "film_genres": ["Action", "Adventure"]}
    assert cinemacity.show_lang({"Localization.Language.English", "Showtime.Service.VIP"}) == {"lang": "en"}
    assert cinemacity.show_lang({"Format.Projection.Digital"}) == {}
