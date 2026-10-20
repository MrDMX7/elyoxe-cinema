"""«اسأل الفيلم» — POST /ask (owner 2026-10-18): a visitor asks one film a question; Claude answers from that film's
own facts (the site's /data/ask/<fid>.json, with our own schedule: shows, halls, subtitles, cheapest seat), its whole
Wikipedia article (plot, cast, production, music, release, reception, box office — English, else Arabic) and its
Wikidata (cast with characters and citizenship; series, sequels, based on, country, crew, awards, budget), nothing else.
(2026-10-20: the plot section alone could not answer «أمتع لقطة» or «كم شخصية عربية».)

Request  {"fid": "street-fighter", "q": "شو نوع الفيلم؟", "lang": "ar"|"en", "uid": "<optional daily id>"}
Answer   {"answer": "...", "spoiler": bool, "known": bool, "source": "plot"|"article"|"facts"|"none", "cached": bool}

Honesty: the model may answer only from the context block; anything not in it is «ما عندنا هالمعلومة» (known=false),
never a guess. spoiler=true when the answer reveals events past the premise — the page hides it behind a tap.

Cost and abuse: answers are cached per (film, language, normalised question) for 30 days; a day's Claude calls are
capped (DAILY_CAP) and so is one visitor's (UID_CAP, by the client's own daily id — no IP is read or stored); the
owner's kill switch is the SSM parameter /elyoxe/cinema/ask/off (any value). Every call logs its tokens.
"""
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import anthropic
import boto3

DUBAI = timezone(timedelta(hours=4))
TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE"])
SSM = boto3.client("ssm")
ORIGINS = set(os.environ.get("ALLOWED_ORIGINS", "https://cinema.elyoxe.com").split(","))
SITE = os.environ.get("SITE", "https://cinema.elyoxe.com")
MODEL = os.environ.get("MODEL", "claude-haiku-5-5")   # the model the owner chose for the site's Claude work (2026-10-09)
DAILY_CAP = int(os.environ.get("DAILY_CAP", "1500"))
UID_CAP = int(os.environ.get("UID_CAP", "40"))
UA = {"User-Agent": "elyoxe-cinema-ask/1.0 (+https://cinema.elyoxe.com)"}
FID = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
DROP_SECTIONS = {"references", "external links", "notes", "see also", "further reading", "footnotes", "citations",
                 "bibliography", "sources", "المراجع", "وصلات خارجية", "انظر أيضا", "مصادر", "ملاحظات"}
ARTICLE_MAX = 40000
SYSTEM = open(os.path.join(os.path.dirname(__file__), "system.txt"), encoding="utf-8").read()
LEX = json.load(open(os.path.join(os.path.dirname(__file__), "lexicon.json"), encoding="utf-8"))
WORD = re.compile(r"[\u0621-\u064A\u0671-\u06D3]+")   # Arabic letters only: \u00AB\u060C\u00BB and \u00AB\u061F\u00BB sit in the same block


def dialect(text):
    """The owner's lexicon on an Arabic answer: banned phrases, then banned words as whole words (make_system.py)."""
    for bad, good in LEX["phrases"].items():
        text = text.replace(bad, good)
    return WORD.sub(lambda m: LEX["words"].get(m.group(0), m.group(0)), text)
TANWIN = re.compile("[ًٌٍ]")
INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_client = None

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer", "spoiler", "known", "source"],
          "properties": {"answer": {"type": "string"}, "spoiler": {"type": "boolean"}, "known": {"type": "boolean"},
                         "source": {"type": "string", "enum": ["plot", "article", "facts", "none"]}}}


def cors(origin):
    o = origin if origin in ORIGINS else next(iter(ORIGINS))
    return {"Access-Control-Allow-Origin": o, "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store"}


def reply(status, origin, body):
    return {"statusCode": status, "headers": cors(origin), "body": json.dumps(body, ensure_ascii=False)}


def today():
    return datetime.now(DUBAI).strftime("%Y-%m-%d")


def ttl(days):
    return int(time.time() + days * 86400)


def norm(q):
    q = unicodedata.normalize("NFKC", q).lower()
    q = re.sub(r"[ً-ْـ]", "", q)            # harakat and tatweel
    q = re.sub(r"[أإآ]", "ا", q).replace("ى", "ي").replace("ة", "ه")
    q = re.sub(r"[^\w\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def off():
    try:
        SSM.get_parameter(Name="/elyoxe/cinema/ask/off")
        return True
    except SSM.exceptions.ParameterNotFound:
        return False
    except Exception:
        return False


def client():
    global _client
    if _client is None:
        key = SSM.get_parameter(Name="/elyoxe/anthropic/key", WithDecryption=True)["Parameter"]["Value"]
        _client = anthropic.Anthropic(api_key=key, max_retries=1, timeout=25.0)
    return _client


def get_json(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def wiki_title(qid):
    """(lang, page title) of the film's Wikipedia article — English first, else Arabic — from its Wikidata sitelinks."""
    if not qid or not re.match(r"^Q\d+$", str(qid)):
        return None, None
    try:
        ent = (get_json("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": qid, "props": "sitelinks",
                                                              "format": "json"}).get("entities") or {}).get(qid) or {}
        links = ent.get("sitelinks") or {}
        for lang in ("en", "ar"):
            t = (links.get(lang + "wiki") or {}).get("title")
            if t:
                return lang, t
    except Exception:  # noqa: BLE001
        pass
    return None, None


def find_qid(fid, title, year):
    """A film the site has no Wikidata id for (Wikidata may hold it without a release date, which enrich.py refuses):
    English Wikipedia's search for «<title> <year> film»; a hit counts only when its title starts with the film's own
    title and its text names the year (or the year before), so an older film of the same name never answers. Cached
    7 days ("" = none)."""
    k = f"qid#{fid}"
    hit = TABLE.get_item(Key={"k": k}).get("Item")
    if hit:
        return hit.get("v") or None
    qid = None
    if title and year:
        try:
            api = "https://en.wikipedia.org/w/api.php"
            res = (get_json(api, {"action": "query", "list": "search", "srsearch": f"{title} {year} film", "srlimit": 5,
                                  "format": "json"}).get("query") or {}).get("search") or []
            norm_t = re.sub(r"[^a-z0-9]+", "", title.lower())
            for r in res:
                if not re.sub(r"[^a-z0-9]+", "", r.get("title", "").lower()).startswith(norm_t):
                    continue
                pages = (get_json(api, {"action": "query", "prop": "pageprops|extracts", "explaintext": 1, "exintro": 1,
                                        "titles": r["title"], "redirects": 1, "format": "json"}).get("query") or {}).get("pages") or {}
                pg = next(iter(pages.values()), {})
                intro = pg.get("extract") or ""
                if "film" in intro.lower() and (str(year) in intro or str(int(year) - 1) in intro):
                    qid = (pg.get("pageprops") or {}).get("wikibase_item")
                    break
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"find_qid_error": str(e)[:200], "fid": fid}))
            return None
    TABLE.put_item(Item={"k": k, "v": qid or "", "ttl": ttl(7)})
    return qid


def article_of(fid, qid):
    """The film's whole Wikipedia article as plain text with its == headings == (references and links dropped), cached
    7 days; "" when there is none."""
    k = f"art#{fid}"
    hit = TABLE.get_item(Key={"k": k}).get("Item")
    if hit:
        return hit.get("v", "")
    text = ""
    lang, title = wiki_title(qid)
    if title:
        try:
            pages = (get_json(f"https://{lang}.wikipedia.org/w/api.php", {
                "action": "query", "prop": "extracts", "explaintext": 1, "titles": title, "redirects": 1,
                "format": "json"}).get("query") or {}).get("pages") or {}
            raw = next(iter(pages.values()), {}).get("extract") or ""
            keep, out = True, []
            for line in raw.split("\n"):
                m = re.match(r"^(=+)\s*(.*?)\s*\1\s*$", line)
                if m and len(m.group(1)) == 2:
                    keep = m.group(2).strip().lower() not in DROP_SECTIONS
                if keep and line.strip():
                    out.append(line.strip())
            text = (f"[{lang} Wikipedia: {title}]\n" + "\n".join(out))[:ARTICLE_MAX]
        except Exception as e:  # noqa: BLE001 - no article is an answer too («ما عندنا هالمعلومة»)
            print(json.dumps({"article_error": str(e)[:200], "fid": fid}))
            return ""
    TABLE.put_item(Item={"k": k, "v": text, "ttl": ttl(7)})
    return text


def _labels(ids):
    """{Qid: {"label", "claims"}} for the given ids, 50 a call (English label, else Arabic, else any)."""
    out = {}
    ids = [i for i in dict.fromkeys(ids) if i and re.match(r"^Q\d+$", str(i))]
    for n in range(0, len(ids), 50):
        ents = get_json("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": "|".join(ids[n:n + 50]),
                                                               "props": "labels|claims", "languages": "en|ar",
                                                               "format": "json"}).get("entities") or {}
        for q, e in ents.items():
            lb = e.get("labels") or {}
            out[q] = {"label": (lb.get("en") or lb.get("ar") or next(iter(lb.values()), {})).get("value"),
                      "claims": e.get("claims") or {}}
    return out


def _ids(claims, prop):
    return [(((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("id") for c in claims.get(prop) or []]


WD_ITEMS = {"P179": "series", "P155": "follows", "P156": "followed_by", "P144": "based_on", "P495": "country_of_origin",
            "P364": "original_language", "P57": "director", "P58": "screenwriter", "P86": "composer",
            "P272": "production_company", "P915": "filming_location", "P166": "awards"}
WD_AMOUNTS = {"P2130": "budget", "P2142": "box_office"}


def wikidata_of(fid, qid):
    """The film's Wikidata: its cast ([{"actor", "character", "citizenship"}]) and its film facts — series, what it
    follows and what follows it, what it is based on, country and original language, director, writers, composer,
    production companies, filming locations, awards, budget and box office (owner 2026-10-20: «جزء ثاني؟ لازم أشوف
    الأول؟», «مأخوذ عن رواية؟»). Cached 7 days; {} when none."""
    k = f"wd#{fid}"
    hit = TABLE.get_item(Key={"k": k}).get("Item")
    if hit:
        return json.loads(hit.get("v") or "{}")
    out = {}
    if qid and re.match(r"^Q\d+$", str(qid)):
        try:
            film = _labels([qid]).get(qid) or {}
            claims = film.get("claims") or {}
            members = []
            for c in claims.get("P161") or []:
                actor = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("id")
                role = None
                for qv in (c.get("qualifiers") or {}).get("P453") or []:
                    role = ((qv.get("datavalue") or {}).get("value") or {}).get("id") or role
                if actor:
                    members.append((actor, role))
            members = members[:40]
            item_ids = {p: [i for i in _ids(claims, p) if i][:12] for p in WD_ITEMS}
            units = []
            for p in WD_AMOUNTS:
                for c in claims.get(p) or []:
                    u = str((((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("unit") or "")
                    if "/Q" in u:
                        units.append(u.rsplit("/", 1)[1])
            people = _labels([a for a, _ in members] + [r for _, r in members if r]
                             + [i for ids in item_ids.values() for i in ids] + units)
            countries = _labels([c for a, _ in members for c in _ids((people.get(a) or {}).get("claims") or {}, "P27")])
            cast = []
            for a, r in members:
                pa = people.get(a) or {}
                cast.append({"actor": pa.get("label"), "character": (people.get(r) or {}).get("label") if r else None,
                             "citizenship": [(countries.get(c) or {}).get("label") for c in _ids(pa.get("claims") or {}, "P27") if c] or None})
            if cast:
                out["cast"] = cast
            for p, name in WD_ITEMS.items():
                vals = [(people.get(i) or {}).get("label") for i in item_ids[p]]
                vals = [v for v in vals if v]
                if vals:
                    out[name] = vals
            for p, name in WD_AMOUNTS.items():
                vals = []
                for c in claims.get(p) or []:
                    v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
                    u = str(v.get("unit") or "")
                    unit = (people.get(u.rsplit("/", 1)[1]) or {}).get("label") if "/Q" in u else None
                    if v.get("amount"):
                        vals.append(f'{v["amount"].lstrip("+")} {unit or ""}'.strip())
                if vals:
                    out[name] = vals
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"wikidata_error": str(e)[:200], "fid": fid}))
            return {}
    TABLE.put_item(Item={"k": k, "v": json.dumps(out, ensure_ascii=False), "ttl": ttl(7)})
    return out


def until_4am():
    """Seconds-since-epoch of the next 04:00 in Dubai: the end of a cinema day."""
    now = datetime.now(DUBAI)
    end = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if end <= now:
        end += timedelta(days=1)
    return int(end.timestamp())


def bump(k, field="n", by=1, days=3):
    r = TABLE.update_item(Key={"k": k}, UpdateExpression="ADD #f :b SET #t = if_not_exists(#t, :t)",
                          ExpressionAttributeNames={"#f": field, "#t": "ttl"},
                          ExpressionAttributeValues={":b": by, ":t": ttl(days)}, ReturnValues="UPDATED_NEW")
    return int(r["Attributes"][field])


def context_block(facts, wd, article):
    lines = ["<facts>", json.dumps(facts, ensure_ascii=False), "</facts>"]
    lines += ["<wikidata>", json.dumps(wd, ensure_ascii=False) if wd else "(nothing)", "</wikidata>"]
    lines += ["<article>", article or "(no article available yet)", "</article>"]
    return "\n".join(lines)


def handler(event, _ctx):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin", "")
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method", "")
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": cors(origin), "body": ""}
    if method != "POST":
        return reply(405, origin, {"error": "method"})
    if origin not in ORIGINS:
        return reply(403, origin, {"error": "origin"})
    try:
        data = json.loads((event.get("body") or "")[:3000])
    except ValueError:
        return reply(400, origin, {"error": "json"})
    fid, q = str(data.get("fid") or ""), str(data.get("q") or "").strip()
    lang = "en" if data.get("lang") == "en" else "ar"
    uid = str(data.get("uid") or "")[:128]
    if not FID.match(fid) or not (2 <= len(q) <= 240):
        return reply(400, origin, {"error": "fields"})
    if off():
        return reply(503, origin, {"error": "off"})

    nq = norm(q)
    if len(re.sub(r"[\W_]", "", nq)) < 2:   # no readable letters (a mis-encoded «????»): never one shared cache key
        return reply(400, origin, {"error": "fields"})
    key = f"ans2#{fid}#{lang}#" + hashlib.sha1(nq.encode()).hexdigest()[:20]   # ans2: answered from the whole article
    hit = TABLE.get_item(Key={"k": key}).get("Item")
    if hit and int(hit.get("ttl") or 0) > time.time():   # DynamoDB removes expired items up to two days late
        out = json.loads(hit["v"])
        out["cached"] = True
        return reply(200, origin, out)

    day = today()
    if uid and bump(f"uid#{day}#{hashlib.sha1(uid.encode()).hexdigest()[:16]}") > UID_CAP:
        return reply(429, origin, {"error": "uid_cap"})
    if bump(f"day#{day}") > DAILY_CAP:
        return reply(429, origin, {"error": "day_cap"})

    try:
        facts = get_json(f"{SITE}/data/ask/{fid}.json")
    except Exception:
        return reply(404, origin, {"error": "film"})
    qid = facts.pop("qid", None) or find_qid(fid, facts.get("title"), str(facts.get("uae_release_date") or facts.get("year") or "")[:4])
    article, wd = article_of(fid, qid), wikidata_of(fid, qid)

    t0 = time.time()
    try:
        resp = client().messages.create(
            model=MODEL, max_tokens=2048,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            # the film's context is its own cached block: a second question on the same film within minutes reads it
            # from the cache (it is long: the whole article)
            system=[{"type": "text", "text": SYSTEM},
                    {"type": "text", "text": context_block(facts, wd, article), "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"<lang>{lang}</lang>\n<question>{q}</question>"}],
        )
    except anthropic.RateLimitError:
        return reply(429, origin, {"error": "busy"})
    except anthropic.APIStatusError as e:
        print(json.dumps({"api_error": e.status_code, "msg": str(e)[:200]}))
        return reply(502, origin, {"error": "model"})
    except anthropic.APIConnectionError:
        return reply(502, origin, {"error": "model"})
    if resp.stop_reason == "refusal":
        out = {"answer": "ما أقدر أجاوب على هالسؤال." if lang == "ar" else "I can't answer that one.",
               "spoiler": False, "known": False, "source": "none"}
    else:
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        try:
            out = json.loads(text)
        except ValueError:
            return reply(502, origin, {"error": "format"})
    if lang == "ar":
        out["answer"] = dialect(TANWIN.sub("", out.get("answer", "")).translate(INDIC))
    u = resp.usage
    print(json.dumps({"fid": fid, "lang": lang, "in": u.input_tokens, "out": u.output_tokens,
                      "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0, "secs": round(time.time() - t0, 2),
                      "known": out.get("known"), "spoiler": out.get("spoiler")}))
    bump(f"tok#{day}", "in", u.input_tokens, days=40)
    bump(f"tok#{day}", "out", u.output_tokens, days=40)
    # «ما عندنا» is kept a day only: the film's article may arrive (a new link, a new section) and the question deserves
    # a fresh try; a real answer is kept a month
    # an answer from our showing facts (times, halls, prices) holds only for this cinema day
    exp = ttl(30) if out.get("known") and out.get("source") in ("plot", "article") else (until_4am() if out.get("known") else ttl(1))
    TABLE.put_item(Item={"k": key, "v": json.dumps(out, ensure_ascii=False), "q": q[:240], "ttl": exp})
    out["cached"] = False
    return reply(200, origin, out)
