"""People (cast & directors): steps/people.py collects credits, names, free photos and Wikipedia bios from
Wikidata/Commons/Wikipedia into data["people"]; pages/people.py writes /people/<slug>/ in both languages and a
cast strip on film pages (the film.info slot)."""
import copy, importlib.util, io, json, os, re, sys

import pytest
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")

_spec = importlib.util.spec_from_file_location("steps_people", os.path.join(ROOT, "steps", "people.py"))
people = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(people)

NOW = "2026-09-27T10:00:00+04:00"


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


# ------------------------------------------------------------------ a fake Wikimedia
def claim(v, ordinal=None):
    c = {"mainsnak": {"datavalue": {"value": v}}}
    if ordinal is not None:
        c["qualifiers"] = {"P1545": [{"datavalue": {"value": str(ordinal)}}]}
    return c


def png(w=400, h=600):
    b = io.BytesIO()
    Image.new("RGB", (w, h), (120, 40, 50)).save(b, "PNG")
    return b.getvalue()


FILMS = {  # film qid -> (cast qids in claim order with ordinals, directors)
    "Q100": ([("Q1", 2), ("Q2", 1)] + [(f"Q{10 + i}", None) for i in range(10)], ["Q9"]),
}
PEOPLE = {
    "Q1": {"en": "Jane Roe", "ar": "جين رو", "img": "Jane Roe.jpg", "sex": "Q6581072", "enwiki": "Jane Roe", "arwiki": "جين رو",
           "notable": ["Q500", "Q100"]},
    "Q2": {"en": "John Doe", "ar": None, "img": "John NC.jpg", "sex": "Q6581097", "enwiki": "John Doe", "arwiki": None, "notable": []},
    "Q9": {"en": "Ann Director", "ar": "آن", "img": None, "sex": "Q6581072", "enwiki": None, "arwiki": None, "notable": []},
}
LICENCES = {"Jane Roe.jpg": ("CC BY-SA 4.0", "cc-by-sa-4.0"), "John NC.jpg": ("CC BY-NC 2.0", "cc-by-nc-2.0")}


class FakeClient:
    def __init__(self):
        self.calls = []

    def json(self, url, params):
        self.calls.append((url, dict(params)))
        if "wikidata" in url:
            ents = {}
            for q in params["ids"].split("|"):
                if q in FILMS:
                    cast, dirs = FILMS[q]
                    ents[q] = {"claims": {"P161": [claim({"id": c}, o) for c, o in cast],
                                          "P57": [claim({"id": d}) for d in dirs]}}
                elif q in PEOPLE:
                    p = PEOPLE[q]
                    labels = {"en": {"value": p["en"]}}
                    if p["ar"]: labels["ar"] = {"value": p["ar"]}
                    claims = {"P21": [claim({"id": p["sex"]})], "P800": [claim({"id": n}) for n in p["notable"]]}
                    if p["img"]: claims["P18"] = [claim(p["img"])]
                    sl = {k + "wiki": {"title": p[k + "wiki"]} for k in ("en", "ar") if p[k + "wiki"]}
                    ents[q] = {"labels": labels, "claims": claims, "sitelinks": sl}
                elif q == "Q500":
                    ents[q] = {"labels": {"en": {"value": "Old Hit"}, "ar": {"value": "نجاح قديم"}}}
                else:  # the billed-late cast: a name, nothing else
                    ents[q] = {"labels": {"en": {"value": f"Actor {q}"}}, "claims": {}, "sitelinks": {}}
            return {"entities": ents}
        if "commons" in url:
            pages = {}
            for i, t in enumerate(params["titles"].split("|")):
                name = t[len("File:"):]
                short, code = LICENCES[name]
                pages[str(-i - 1)] = {"title": t, "imageinfo": [{
                    "thumburl": f"https://upload.wikimedia.org/thumb/{i}.jpg",
                    "descriptionurl": f"https://commons.wikimedia.org/wiki/{t.replace(' ', '_')}",
                    "extmetadata": {"LicenseShortName": {"value": short}, "License": {"value": code},
                                    "Artist": {"value": '<a href="//x">Pat <b>Photographer</b></a>'},
                                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"}}}]}
            return {"query": {"pages": pages}}
        if "wikipedia" in url:
            lang = url.split("//")[1][:2]
            pages = {}
            for i, t in enumerate(params["titles"].split("|")):
                text = ("جين رو ممثلة أمريكية. ولدت في 1980 في مدينة. لها أفلام كثيرة." if lang == "ar"
                        else "John Doe (born 1970) is an American actor. He was raised by J. R. R. Smith in Ohio. He has won things.")
                pages[str(i + 1)] = {"title": t, "extract": text, "fullurl": f"https://{lang}.wikipedia.org/wiki/{t.replace(' ', '_')}"}
            return {"query": {"pages": pages}}
        raise AssertionError(url)

    def blob(self, url):
        self.calls.append((url, {}))
        return png()


def film_data():
    return {"films": {"a-film": {"title": "A Film", "wikidata": {"qid": "Q100"}, "cast": ["Jane Roe"]},
                      "no-qid": {"title": "Nothing", "cast": ["Someone"]}}}


def ctx(tmp_path, client, uploaded=None, offline=False):
    calls = []

    def upload(out_dir):
        calls.append(out_dir)
        return sorted(os.listdir(out_dir)) if uploaded is None else uploaded
    return {"offline": offline, "now": NOW, "data_dir": str(tmp_path), "client": client, "upload": upload}, calls


# ------------------------------------------------------------------ pure parts
def test_licence_filter_only_free():
    ok = [("CC BY-SA 4.0", "cc-by-sa-4.0"), ("CC BY 2.0", "cc-by-2.0"), ("CC0", "cc0"), ("Public domain", "pd"),
          ("Public domain", None), ("CC BY-SA 3.0", None)]
    bad = [("CC BY-NC 2.0", "cc-by-nc-2.0"), ("CC BY-ND 4.0", "cc-by-nd-4.0"), ("CC BY-NC-SA 2.0", "cc-by-nc-sa-2.0"),
           ("GFDL", "gfdl"), ("Fair use", None), ("", None), (None, None), ("Copyrighted", "copyrighted")]
    assert all(people.free_licence(s, c) for s, c in ok)
    assert not any(people.free_licence(s, c) for s, c in bad)


def test_credits_follow_billing_and_cap():
    ent = {"claims": {"P161": [claim({"id": c}, o) for c, o in FILMS["Q100"][0]], "P57": [claim({"id": "Q9"})]}}
    cast, dirs = people.credits(ent)
    assert cast[:2] == ["Q2", "Q1"] and len(cast) == people.CAST_CAP == 8 and dirs == ["Q9"]


def test_two_sentences_keeps_initials_and_arabic():
    assert people.two_sentences("A bee. C is by J. R. R. Smith. Three. Four.") == "A bee. C is by J. R. R. Smith."
    assert people.two_sentences("جملة أولى. جملة ثانية؟ ثالثة.") == "جملة أولى. جملة ثانية؟"
    assert people.two_sentences("") == ""


def test_english_name_falls_back_to_mul_label():
    assert people._en({"mul": {"value": "Anne Hathaway"}}) == "Anne Hathaway"
    assert people._en({"en": {"value": "A"}, "mul": {"value": "B"}}) == "A"
    assert people._en({"mul": {"value": "آن"}}) is None and people._en({"mul": {"value": "Анна"}}) is None


def test_slugs_unique_and_safe():
    s = people.slugs({"Q1": {"name_en": "Zoë Saldaña"}, "Q2": {"name_en": "Zoe Saldana"}, "Q3": {"name_ar": "فقط"}})
    assert s["Q1"] == "zoe-saldana-q1" or s["Q2"] == "zoe-saldana-q2"
    assert len(set(s.values())) == 3 and s["Q3"] == "q3"
    assert all(re.match(r"^[a-z0-9][a-z0-9-]*$", v) for v in s.values())


# ------------------------------------------------------------------ the step
def test_step_collects_people_and_rewrites_credits(tmp_path):
    data = film_data()
    c, uploads = ctx(tmp_path, FakeClient())
    res = people.run(data, c)
    f = data["films"]["a-film"]
    assert f["cast"][:2] == ["Q2", "Q1"] and len(f["cast"]) == 8 and f["directors"] == ["Q9"]
    assert data["films"]["no-qid"]["cast"] == [] and data["films"]["no-qid"]["directors"] == []
    ps = data["people"]
    jane, john, ann = ps["Q1"], ps["Q2"], ps["Q9"]
    assert jane["name_ar"] == "جين رو" and jane["gender"] == "f" and jane["slug"] == "jane-roe"
    # a free photo: mirrored at two widths, licence and author recorded (HTML stripped)
    ph = jane["photo"]
    assert ph["licence"] == "CC BY-SA 4.0" and ph["author"] == "Pat Photographer"
    assert re.match(r"^/posters/people/q1-[0-9a-f]{10}-160\.webp$", ph["src"]) and ph["src2x"].endswith("-320.webp")
    assert ph["page"].startswith("https://commons.wikimedia.org/wiki/File:")
    for u in (ph["src"], ph["src2x"]):
        im = Image.open(os.path.join(tmp_path, "posters", "people", u.rsplit("/", 1)[1]))
        assert im.format == "WEBP" and im.size[0] in (160, 320) and im.size[1] == im.size[0] * 5 // 4
    assert john["photo"] is None and ann["photo"] is None            # NC licence refused; no P18
    # bios: ar first on its own, en separately; two sentences, cited
    assert jane["bio"]["ar"]["text"] == "جين رو ممثلة أمريكية. ولدت في 1980 في مدينة."
    assert jane["bio"]["ar"]["url"].startswith("https://ar.wikipedia.org/wiki/")
    assert john["bio"]["ar"] is None and john["bio"]["en"]["text"].endswith("J. R. R. Smith in Ohio.")
    # notable works: labels, and the film itself stays in (the page drops what it already lists)
    assert {"qid": "Q500", "en": "Old Hit", "ar": "نجاح قديم"} in jane["notable"]
    assert res["people"] == len(ps) and uploads


def test_step_cache_ttl_and_offline(tmp_path):
    first = FakeClient()
    people.run(film_data(), ctx(tmp_path, first)[0])
    assert first.calls
    again = FakeClient()
    data = film_data()
    people.run(data, ctx(tmp_path, again)[0])
    assert again.calls == []                                   # everything fresh in data/people_cache.json
    off = film_data()
    people.run(off, ctx(tmp_path, None, offline=True)[0])      # offline: the cache alone, no client at all
    assert off["people"] == data["people"] and off["films"]["a-film"]["cast"] == data["films"]["a-film"]["cast"]
    cache = json.load(open(tmp_path / "people_cache.json", encoding="utf-8"))
    for rec in cache["people"].values():
        rec["at"] = "2026-09-01T00:00:00+04:00"               # older than 14 days: asked again
    json.dump(cache, open(tmp_path / "people_cache.json", "w", encoding="utf-8"))
    stale = FakeClient()
    people.run(film_data(), ctx(tmp_path, stale)[0])
    assert any("wikidata" in u for u, _ in stale.calls)


def test_photo_only_once_uploaded(tmp_path):
    data = film_data()
    people.run(data, ctx(tmp_path, FakeClient(), uploaded=[])[0])   # bucket missing: nothing uploaded
    assert data["people"]["Q1"]["photo"] is None


def test_network_failure_is_not_cached(tmp_path):
    class Down(FakeClient):
        def json(self, url, params):
            raise people.Failed("down")
    data = film_data()
    people.run(data, ctx(tmp_path, Down())[0])
    assert data["people"] == {} and data["films"]["a-film"]["cast"] == []
    ok = FakeClient()
    people.run(film_data(), ctx(tmp_path, ok)[0])
    assert ok.calls


# ------------------------------------------------------------------ the pages
def site_data(tmp_path, many=0):
    d = json.load(open(DATA, encoding="utf-8"))
    fs = d["films"]
    for f in fs.values():
        f["cast"], f["directors"] = [], []
    fs["heart-of-the-beast"]["cast"] = ["Q1", "Q2"]
    fs["heart-of-the-beast"]["directors"] = ["Q9"]
    fs["weapons"]["cast"] = ["Q1", "Q7"]                       # archived
    fs["sacrifice"]["cast"] = ["Q1"] + (["Q99"] if many else [])
    ph = {"src": "/posters/people/q1-0123456789-160.webp", "src2x": "/posters/people/q1-0123456789-320.webp",
          "licence": "CC BY-SA 4.0", "licence_url": "https://creativecommons.org/licenses/by-sa/4.0",
          "author": "Pat <Photographer>", "page": "https://commons.wikimedia.org/wiki/File:Jane_Roe.jpg"}
    d["people"] = {
        "Q1": {"qid": "Q1", "slug": "jane-roe", "name_en": "Jane Roe", "name_ar": "جين رو", "gender": "f", "photo": ph,
               "bio": {"ar": {"text": "جين رو ممثلة أمريكية.", "url": "https://ar.wikipedia.org/wiki/x"},
                       "en": {"text": "Jane Roe is an American actress.", "url": "https://en.wikipedia.org/wiki/Jane_Roe"}},
               "notable": [{"qid": "Q500", "en": "Old Hit", "ar": "نجاح قديم"}]},
        "Q2": {"qid": "Q2", "slug": "john-doe", "name_en": "John Doe", "name_ar": None, "gender": "m", "photo": None,
               "bio": {"ar": None, "en": {"text": "John Doe is an actor.", "url": "https://en.wikipedia.org/wiki/John_Doe"}}, "notable": []},
        "Q9": {"qid": "Q9", "slug": "ann-director", "name_en": "Ann Director", "name_ar": "آن", "gender": "f", "photo": None,
               "bio": {"ar": None, "en": None}, "notable": []},
        "Q7": {"qid": "Q7", "slug": "q7", "name_en": None, "name_ar": None, "gender": None, "photo": None,
               "bio": {"ar": None, "en": None}, "notable": []},            # no name: no page
        "Q8": {"qid": "Q8", "slug": "lonely", "name_en": "Lonely", "name_ar": None, "gender": None, "photo": None,
               "bio": {"ar": None, "en": None}, "notable": []},            # in no film: no page
    }
    if many:   # a prolific actor: in every film, with a long notable list
        for f in fs.values():
            f["cast"].append("Q99")
        d["people"]["Q99"] = {"qid": "Q99", "slug": "busy", "name_en": "Busy Person", "name_ar": None, "gender": "m",
                              "photo": None, "bio": {"ar": None, "en": {"text": "x " * 400, "url": "https://en.wikipedia.org/wiki/B"}},
                              "notable": [{"qid": f"Q{600 + i}", "en": f"Work {i} " * 8, "ar": None} for i in range(60)]}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return str(p)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("people")
    out = str(tmp / "out")
    build.build(site_data(tmp), DISC, out, noindex=False)
    return out


def ld(html):
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))["@graph"]


def test_person_page_ar(site):
    h = read(site, "people", "jane-roe", "index.html")
    assert '<h1 class="pt">جين رو</h1>' in h and 'lang="en" dir="ltr">Jane Roe<' in h
    assert 'src="/posters/people/q1-0123456789-160.webp"' in h and "Pat &lt;Photographer&gt;" in h and "CC BY-SA 4.0" in h
    assert "جين رو ممثلة أمريكية." in h and 'href="https://ar.wikipedia.org/wiki/x"' in h
    showing = h[h.index("يعرض لها الحين"):]
    assert 'href="/film/heart-of-the-beast/"' in showing and 'href="/film/sacrifice/"' in showing
    assert 'class="p" data-aed=' in showing                      # the cheapest price, repriced after the card
    assert 'href="/film/weapons/"' in h and "نجاح قديم" in h
    person = next(n for n in ld(h) if n["@type"] == "Person")
    assert person["name"] == "جين رو" and person["url"] == "https://cinema.elyoxe.com/people/jane-roe/"
    assert person["image"].endswith("-320.webp") and "https://www.wikidata.org/wiki/Q1" in person["sameAs"]


def test_person_page_en_and_fallbacks(site):
    h = read(site, "en", "people", "jane-roe", "index.html")
    assert '<h1 class="pt">Jane Roe</h1>' in h and "Jane Roe is an American actress." in h and "Showing now" in h
    j = read(site, "people", "john-doe", "index.html")          # no Arabic name or bio: English, marked so
    assert '<h1 class="pt" lang="en" dir="ltr">John Doe</h1>' in j and 'lang="en" dir="ltr">John Doe is an actor.' in j
    assert "يعرض له الحين" in j
    a = read(site, "people", "ann-director", "index.html")
    assert "مخرجة" in a and "<figure" not in a


def test_no_page_without_name_or_film(site):
    assert not os.path.exists(os.path.join(site, "people", "q7"))
    assert not os.path.exists(os.path.join(site, "people", "lonely"))


def test_cast_strip_on_film_pages(site):
    h = read(site, "film", "heart-of-the-beast", "index.html")
    strip = re.search(r'<section class="cast".*?</section>', h, re.S).group(0)
    assert strip.index("/people/ann-director/") < strip.index("/people/jane-roe/") < strip.index("/people/john-doe/")
    arch = read(site, "en", "film", "weapons", "index.html")    # archived pages link to people too
    assert 'href="/en/people/jane-roe/"' in arch and "/people/q7/" not in arch
    assert '<section class="cast"' not in read(site, "film", "resident-evil", "index.html")


def test_sitemap_and_css(site):
    sm = read(site, "sitemap.xml")
    assert "<loc>https://cinema.elyoxe.com/people/jane-roe/</loc>" in sm and "/people/lonely/" not in sm
    assert ".pp-ph" in read(site, "assets", "cinema.css")


def test_budget_prolific_person(tmp_path):
    out = str(tmp_path / "out")
    build.build(site_data(tmp_path, many=1), DISC, out, noindex=False)
    for parts in (("people", "busy"), ("en", "people", "busy")):
        assert os.path.getsize(os.path.join(out, *parts, "index.html")) <= 150_000
    h = read(out, "people", "busy", "index.html")
    assert len(re.findall(r'<li class="nw">', h)) <= 12


def test_no_people_data_no_output(tmp_path):
    out = str(tmp_path / "out")
    d = json.load(open(DATA, encoding="utf-8"))
    d.pop("people", None)
    p = tmp_path / "l.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    build.build(str(p), DISC, out, noindex=False)
    assert not os.path.exists(os.path.join(out, "people"))
    assert '<section class="cast"' not in read(out, "film", "heart-of-the-beast", "index.html")
