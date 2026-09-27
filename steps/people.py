"""Cast & directors (phase 2, A. People): who is in the films we list, for /people/<slug>/.

For every film in data["films"] (showing and archived) with a Wikidata qid (enrich.py's match):
  - credits: P161 cast (billing order: the P1545 ordinal when Wikidata has one, else claim order), capped at
    CAST_CAP; P57 directors, capped at DIRECTOR_CAP.
  - per person: labels ar/en, sex (P21, only for the Arabic له/لها), notable works (P800, capped, labelled),
    photo P18 through the Commons API — kept ONLY under a free licence (CC0, CC BY, CC BY-SA, public domain;
    NC/ND/GFDL-only/fair use refused) with its licence, licence URL, author and file page —, and the lead of
    its Wikipedia article in Arabic and in English (each its own sitelink, never a title search), trimmed to
    two sentences, with the article URL.
  - photos are mirrored like posters: cropped 4:5, WebP at 160 and 320 px wide, into data/posters/people/
    (git-ignored with data/posters/), uploaded to s3://<bucket>/posters/people/ (deploy.sh keeps posters/*),
    served at /posters/people/<qid>-<hash>-<w>.webp. A photo appears only once uploaded.

Writes data["people"] = {qid: {qid, slug, name_en, name_ar, gender, photo|None, bio{ar,en}, notable[]}} for the
people credited on some film, and film["cast"] / film["directors"] = [qid, …] (enrich's names list is replaced;
a film without a Wikidata match gets empty lists, so the field has one type).

Cache data/people_cache.json, TTL 14 days per record. A network failure is never cached (retried next run).
Polite: ≤ 1 request/s across Wikidata, Commons, Wikipedia and upload.wikimedia.org, with enrich's User-Agent;
entities in batches, a time budget per run (the rest waits in the cache for the next run). offline: the cache
alone.
"""
from __future__ import annotations

import hashlib
import html as html_mod
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CAST_CAP = 8
DIRECTOR_CAP = 4
NOTABLE_CAP = 12
TTL = timedelta(days=14)
GAP = 1.0                 # seconds between any two requests
BUDGET_S = 300            # per run; what is left is fetched next run
BATCH = 25                # wbgetentities ids per call (people entities are large)
TITLES = 20               # Wikipedia extracts / Commons files per call
WIDTHS = (160, 320)
QUALITY = 78
VERSION = 1
URL_PREFIX = "/posters/people/"
S3_PREFIX = "posters/people/"
FEMALE = {"Q6581072", "Q1052281"}   # female, trans woman
MALE = {"Q6581097", "Q2449503"}     # male, trans man


class Failed(Exception):
    """A request failed (network, HTTP, JSON): nothing is cached for it."""


class OutOfTime(Exception):
    pass


# ------------------------------------------------------------------ pure helpers
def free_licence(short, code=None) -> bool:
    """CC0, CC BY, CC BY-SA and public domain only. Anything NC/ND, GFDL-only, fair use or unknown: False."""
    for v in (code, short):
        s = re.sub(r"[\s_]+", "-", str(v or "").strip().lower())
        if not s:
            continue
        if re.search(r"(^|-)(nc|nd)(-|$)", s):
            return False
        if re.match(r"^(cc0|cc-zero|pd|public-domain)(\b|-|$)", s) or re.match(r"^cc-by(-sa)?(-\d|$)", s):
            return True
    return False


def _ordinal(c):
    try:
        return int(c["qualifiers"]["P1545"][0]["datavalue"]["value"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _ids(ent, prop):
    out = []
    for i, c in enumerate((ent or {}).get("claims", {}).get(prop, [])):
        try:
            out.append((c["mainsnak"]["datavalue"]["value"]["id"], _ordinal(c), i))
        except (KeyError, TypeError):
            continue
    return out


def credits(ent):
    """(cast qids by billing, capped; director qids, capped)."""
    cast = sorted(_ids(ent, "P161"), key=lambda t: (t[1] is None, t[1] or 0, t[2]))
    cast = list(dict.fromkeys(q for q, _, _ in cast))[:CAST_CAP]
    dirs = list(dict.fromkeys(q for q, _, _ in _ids(ent, "P57")))[:DIRECTOR_CAP]
    return cast, dirs


_END = re.compile(r"[.!?؟։।]")


def two_sentences(text: str) -> str:
    """The first two sentences. A period after a single letter (J. R. R.) or a common abbreviation is no end."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    out, n, i = [], 0, 0
    for m in _END.finditer(text):
        j = m.end()
        if j < len(text) and not text[j].isspace():
            continue
        before = text[:m.start()].rsplit(" ", 1)[-1]
        if m.group() == "." and (len(before) == 1 or before.lower() in ("mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "no")):
            continue
        n += 1
        if n == 2:
            return text[:j]
    return text


def _strip_html(s):
    s = re.sub(r"<[^>]+>", "", str(s or ""))
    return re.sub(r"\s+", " ", html_mod.unescape(s)).strip()[:160] or None


def _en(labels):
    """The English label, else the multilingual default ("mul", which Wikidata now uses instead of repeating a
    name in every Latin-script language) when it is in Latin script."""
    v = (labels.get("en") or {}).get("value")
    if v:
        return v
    m = (labels.get("mul") or {}).get("value")
    return m if m and re.search(r"[A-Za-z]", m) and all(ord(ch) < 0x250 or 0x1E00 <= ord(ch) < 0x1F00 or ch == chr(0x2019) for ch in m) else None


def _slug(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:80].strip("-")


def slugs(ppl: dict) -> dict:
    """qid -> URL slug from the English name (else the qid); a clash keeps the lower qid plain, the other gets -qid."""
    out, used = {}, set()
    for q in sorted(ppl, key=lambda q: (len(q), q)):
        s = _slug(ppl[q].get("name_en")) or q.lower()
        if s in used:
            s = f"{s}-{q.lower()}"
        used.add(s)
        out[q] = s
    return out


def _fresh(rec, now):
    try:
        at = datetime.fromisoformat(rec.get("at") or "")
    except (ValueError, AttributeError):
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return now - at < TTL


# ------------------------------------------------------------------ the network
class Client:
    """≤ 1 request/s, enrich.py's User-Agent, errors raised as Failed."""

    def __init__(self, gap=GAP):
        import requests

        from enrich import UA
        self.s, self.ua, self.gap, self.last = requests.Session(), UA, gap, 0.0

    def _get(self, url, params=None):
        wait = self.gap - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        try:
            r = self.s.get(url, params=params, headers={"User-Agent": self.ua}, timeout=25)
        except Exception as e:  # noqa: BLE001
            raise Failed(f"{url}: {e}") from e
        if r.status_code != 200:
            raise Failed(f"{url}: HTTP {r.status_code}")
        return r

    def json(self, url, params):
        try:
            return self._get(url, params).json()
        except ValueError as e:
            raise Failed(f"{url}: bad JSON") from e

    def blob(self, url):
        import posters
        posters.check_url(url)
        r = self._get(url)
        posters.check_headers(r.headers)
        return r.content


WD = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"


def _wiki(lang):
    return f"https://{lang}.wikipedia.org/w/api.php"


def _chunks(xs, n):
    xs = list(xs)
    return [xs[i:i + n] for i in range(0, len(xs), n)]


class Collector:
    def __init__(self, cache, client, now, out_dir, budget_s=BUDGET_S):
        self.c, self.cl, self.now, self.out = cache, client, now, Path(out_dir)
        self.iso = now.isoformat()
        self.deadline = time.monotonic() + budget_s
        self.stats = {"requests": 0, "failed": 0, "photos": 0}

    def call(self, fn, *a):
        if time.monotonic() > self.deadline:
            raise OutOfTime()
        self.stats["requests"] += 1
        return fn(*a)

    def entities(self, ids, props):
        out = {}
        for part in _chunks(ids, BATCH):
            j = self.call(self.cl.json, WD, {"action": "wbgetentities", "ids": "|".join(part), "format": "json",
                                            "languages": "ar|en|mul", "props": props, "sitefilter": "arwiki|enwiki"})
            out.update(j.get("entities") or {})
        return out

    def step(self, name, fn):
        try:
            fn()
        except OutOfTime:
            self.stats["out_of_time"] = name
            return False
        except Failed as e:
            self.stats["failed"] += 1
            print(f"people: {name}: {e}", file=sys.stderr)
        return True

    # films -> credits
    def films(self, qids):
        todo = [q for q in qids if not _fresh(self.c["films"].get(q), self.now)]
        for part in _chunks(todo, BATCH):
            ents = self.entities(part, "claims")
            for q in part:
                if q in ents:
                    cast, dirs = credits(ents[q])
                    self.c["films"][q] = {"cast": cast, "directors": dirs, "at": self.iso}

    # people -> names, sex, image file, sitelinks, notable works
    def people(self, qids):
        todo = [q for q in qids if not _fresh(self.c["people"].get(q), self.now)]
        for part in _chunks(todo, BATCH):
            ents = self.entities(part, "labels|claims|sitelinks")
            for q in part:
                e = ents.get(q)
                if e is None or "missing" in e:
                    continue
                lab = e.get("labels") or {}
                ar = (lab.get("ar") or {}).get("value")
                claims = e.get("claims") or {}
                img = None
                for c in claims.get("P18", []):
                    try:
                        img = c["mainsnak"]["datavalue"]["value"]; break
                    except (KeyError, TypeError):
                        continue
                sex = {q2 for q2, _, _ in _ids(e, "P21")}
                sl = e.get("sitelinks") or {}
                self.c["people"][q] = {
                    "name_en": _en(lab),
                    "name_ar": ar if ar and re.search(r"[؀-ۿ]", ar) else None,
                    "gender": "f" if sex & FEMALE else "m" if sex & MALE else None,
                    "image": img,
                    "arwiki": (sl.get("arwiki") or {}).get("title"), "enwiki": (sl.get("enwiki") or {}).get("title"),
                    "notable": list(dict.fromkeys(q2 for q2, _, _ in _ids(e, "P800")))[:NOTABLE_CAP],
                    "at": self.iso}

    def works(self, qids):
        todo = [q for q in qids if not _fresh(self.c["works"].get(q), self.now)]
        for part in _chunks(todo, BATCH * 2):
            ents = self.entities(part, "labels")
            for q in part:
                lab = (ents.get(q) or {}).get("labels") or {}
                ar = (lab.get("ar") or {}).get("value")
                self.c["works"][q] = {"en": _en(lab),
                                      "ar": ar if ar and re.search(r"[؀-ۿ]", ar) else None, "at": self.iso}

    # bios: the lead of each person's own article, per language
    def bios(self, qids):
        for lang in ("ar", "en"):
            key = lang + "wiki"
            todo = {}
            for q in qids:
                p = self.c["people"].get(q) or {}
                rec = self.c["bios"].get(q, {}).get(lang)
                if p.get(key) and not (rec and _fresh(rec, self.now) and rec.get("title") == p[key]):
                    todo[p[key]] = q
            for part in _chunks(todo, TITLES):
                j = self.call(self.cl.json, _wiki(lang), {
                    "action": "query", "format": "json", "prop": "extracts|info", "inprop": "url", "exintro": 1,
                    "explaintext": 1, "exlimit": TITLES, "redirects": 1, "titles": "|".join(part)})
                qd = j.get("query") or {}
                alias = {n["to"]: n["from"] for n in (qd.get("normalized") or []) + (qd.get("redirects") or [])}
                for pg in (qd.get("pages") or {}).values():
                    t = pg.get("title")
                    src = alias.get(t, t)
                    src = alias.get(src, src)
                    q = todo.get(src) or todo.get(t)
                    if not q:
                        continue
                    text = two_sentences(pg.get("extract") or "")
                    self.c["bios"].setdefault(q, {})[lang] = {
                        "title": self.c["people"][q][key], "at": self.iso,
                        "text": text or None, "url": pg.get("fullurl") if str(pg.get("fullurl", "")).startswith("https://") else None}

    # photos: licence first, then the file
    def photos(self, qids):
        todo = {}
        for q in qids:
            f = (self.c["people"].get(q) or {}).get("image")
            rec = self.c["photos"].get(q)
            if f and not (rec and _fresh(rec, self.now) and rec.get("file") == f):
                todo["File:" + f] = q
        for part in _chunks(todo, TITLES):
            j = self.call(self.cl.json, COMMONS, {
                "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata",
                "iiurlwidth": 330, "titles": "|".join(part),
                "iiextmetadatafilter": "LicenseShortName|License|LicenseUrl|Artist"})
            qd = j.get("query") or {}
            alias = {n["to"]: n["from"] for n in qd.get("normalized") or []}
            for pg in (qd.get("pages") or {}).values():
                t = pg.get("title")
                q = todo.get(alias.get(t, t)) or todo.get(t)
                if not q:
                    continue
                ii = (pg.get("imageinfo") or [{}])[0]
                md = ii.get("extmetadata") or {}
                val = lambda k: (md.get(k) or {}).get("value")
                rec = {"file": self.c["people"][q]["image"], "at": self.iso, "ok": False}
                short, code = _strip_html(val("LicenseShortName")), val("License")
                if free_licence(short, code) and ii.get("thumburl"):
                    rec.update({"licence": short or str(code).upper(), "licence_url": val("LicenseUrl"),
                                "author": _strip_html(val("Artist")), "page": ii.get("descriptionurl"),
                                "thumb": ii["thumburl"], "ok": True})
                else:
                    rec["why"] = f"licence {short or code or 'unknown'}"
                self.c["photos"][q] = rec
        for q in qids:
            rec = self.c["photos"].get(q)
            if rec and rec.get("ok") and not rec.get("files"):
                try:
                    rec["files"] = self.mirror(q, rec)
                    self.stats["photos"] += 1
                except OutOfTime:
                    raise
                except Exception as e:  # noqa: BLE001 - a bad photo is no photo
                    rec.update(ok=False, why=str(e)[:160])
                    print(f"people: photo {q}: {e}", file=sys.stderr)

    def mirror(self, q, rec):
        import posters
        from PIL import Image
        blob = self.call(self.cl.blob, rec["thumb"])
        img = posters._open(blob)          # size / pixel ceilings, RGB
        w, h = img.size
        if h * 4 >= w * 5:                  # taller than 4:5: keep the top (faces), trim the bottom
            ch = w * 5 // 4
            top = min((h - ch) // 5, h - ch)
            img = img.crop((0, top, w, top + ch))
        else:                               # wider: centre
            cw = h * 4 // 5
            left = (w - cw) // 2
            img = img.crop((left, 0, left + cw, h))
        base = f"{q.lower()}-{hashlib.sha1(f'{VERSION}:{rec['file']}:{hashlib.sha1(blob).hexdigest()}'.encode()).hexdigest()[:10]}"
        self.out.mkdir(parents=True, exist_ok=True)
        names = []
        for width in WIDTHS:
            n = f"{base}-{width}.webp"
            img.resize((width, width * 5 // 4), Image.LANCZOS).save(self.out / n, "WEBP", quality=QUALITY, method=6)
            names.append(n)
        return names


def _load(path):
    try:
        c = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    for k in ("films", "people", "works", "bios", "photos"):
        c.setdefault(k, {})
    c.setdefault("uploaded", [])
    return c


def _save(path, c):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def assemble(data, cache):
    """data["people"] and each film's cast/directors, from the cache alone."""
    wanted = []
    for f in (data.get("films") or {}).values():
        q = (f.get("wikidata") or {}).get("qid")
        cr = cache["films"].get(q) if q else None
        f["cast"] = list(cr["cast"]) if cr else []
        f["directors"] = list(cr["directors"]) if cr else []
        wanted += f["directors"] + f["cast"]
    uploaded = set(cache.get("uploaded") or [])
    ppl = {}
    for q in dict.fromkeys(wanted):
        p = cache["people"].get(q)
        if not p:
            continue
        ph, photo = cache["photos"].get(q) or {}, None
        files = ph.get("files") or []
        if ph.get("ok") and ph.get("file") == p.get("image") and len(files) == 2 and set(files) <= uploaded:
            photo = {"src": URL_PREFIX + files[0], "src2x": URL_PREFIX + files[1], "licence": ph.get("licence"),
                     "licence_url": ph.get("licence_url"), "author": ph.get("author"), "page": ph.get("page")}
        bio = {}
        for lang in ("ar", "en"):
            b = (cache["bios"].get(q) or {}).get(lang)
            ok = b and b.get("text") and b.get("title") == p.get(lang + "wiki")
            bio[lang] = {"text": b["text"], "url": b.get("url")} if ok else None
        notable = []
        for w in p.get("notable") or []:
            lab = cache["works"].get(w) or {}
            if lab.get("en") or lab.get("ar"):
                notable.append({"qid": w, "en": lab.get("en"), "ar": lab.get("ar")})
        ppl[q] = {"qid": q, "name_en": p.get("name_en"), "name_ar": p.get("name_ar"), "gender": p.get("gender"),
                  "photo": photo, "bio": bio, "notable": notable}
    for q, s in slugs(ppl).items():
        ppl[q]["slug"] = s
    data["people"] = ppl
    return ppl


def _upload(out_dir):
    """posters.upload() with our own ledger and prefix; -> the file names now in the bucket."""
    import posters
    ledger = Path(out_dir).parent.parent / "people_uploads.json"
    posters.upload(cache_path=ledger, out_dir=out_dir, prefix=S3_PREFIX)
    return posters._load(ledger)["uploaded"]


def run(data, ctx):
    ctx = ctx or {}
    ddir = Path(ctx.get("data_dir") or ROOT / "data")
    cache_path, out_dir = ddir / "people_cache.json", ddir / "posters" / "people"
    cache = _load(cache_path)
    now = ctx.get("now")
    now = datetime.fromisoformat(now) if isinstance(now, str) else (now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    stats = {}
    if not ctx.get("offline"):
        col = Collector(cache, ctx.get("client") or Client(), now, out_dir, ctx.get("budget_s", BUDGET_S))
        fq = [q for q in dict.fromkeys((f.get("wikidata") or {}).get("qid") for f in (data.get("films") or {}).values()) if q]
        people_q = lambda: list(dict.fromkeys(p for q in fq for p in (cache["films"].get(q) or {}).get("directors", [])
                                              + (cache["films"].get(q) or {}).get("cast", [])))
        for name, fn in (("films", lambda: col.films(fq)), ("people", lambda: col.people(people_q())),
                         ("works", lambda: col.works(list(dict.fromkeys(w for p in people_q() for w in (cache["people"].get(p) or {}).get("notable", []))))),
                         ("bios", lambda: col.bios(people_q())), ("photos", lambda: col.photos(people_q()))):
            if not col.step(name, fn):
                break
            _save(cache_path, cache)
        _save(cache_path, cache)
        stats = col.stats
        if out_dir.is_dir() and any(out_dir.glob("*.webp")):
            try:
                cache["uploaded"] = sorted(set(cache["uploaded"]) | set((ctx.get("upload") or _upload)(out_dir)))
            except Exception as e:  # noqa: BLE001 - photos wait for the next run, pages go without them
                stats["upload_error"] = str(e)[:200]
                print(f"people: upload failed: {e}", file=sys.stderr)
            _save(cache_path, cache)
    ppl = assemble(data, cache)
    return {**stats, "people": len(ppl), "with_photo": sum(1 for p in ppl.values() if p["photo"])}
