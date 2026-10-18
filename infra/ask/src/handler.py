"""«اسأل الفيلم» — POST /ask (owner 2026-10-18): a visitor asks one film a question; Claude answers from that film's
own facts (the site's /data/ask/<fid>.json) and its English Wikipedia plot, nothing else.

Request  {"fid": "street-fighter", "q": "شو نوع الفيلم؟", "lang": "ar"|"en", "uid": "<optional daily id>"}
Answer   {"answer": "...", "spoiler": bool, "known": bool, "source": "plot"|"facts"|"none", "cached": bool}

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
PLOT_HEADINGS = {"plot", "plot summary", "synopsis"}
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
                         "source": {"type": "string", "enum": ["plot", "facts", "none"]}}}


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


def plot_of(fid, title):
    """The English Wikipedia «Plot» section as plain text (cached 7 days, "" when there is none)."""
    if not title:
        return ""
    k = f"plot#{fid}"
    hit = TABLE.get_item(Key={"k": k}).get("Item")
    if hit:
        return hit.get("v", "")
    text = ""
    try:
        api = "https://en.wikipedia.org/w/api.php"
        secs = (get_json(api, {"action": "parse", "page": title, "prop": "sections", "format": "json", "redirects": 1})
                .get("parse") or {}).get("sections") or []
        idx = next((s.get("index") for s in secs if re.sub(r"\s+", " ", s.get("line") or "").strip().lower() in PLOT_HEADINGS), None)
        if idx:
            html = ((get_json(api, {"action": "parse", "page": title, "prop": "text", "section": idx, "format": "json",
                                    "redirects": 1}).get("parse") or {}).get("text") or {}).get("*") or ""
            html = re.sub(r"<sup[^>]*>.*?</sup>", "", html, flags=re.S)
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
            text = re.sub(r"^\S+\s*\[\s*edit\s*\]\s*", "", text)
    except Exception as e:  # noqa: BLE001 - no plot is an answer too («ما عندنا هالمعلومة»)
        print(json.dumps({"plot_error": str(e)[:200], "fid": fid}))
        return ""
    TABLE.put_item(Item={"k": k, "v": text[:24000], "ttl": ttl(7)})
    return text[:24000]


def enwiki_title(qid):
    """The English Wikipedia page title for a Wikidata id, or None."""
    if not qid or not re.match(r"^Q\d+$", str(qid)):
        return None
    try:
        ent = (get_json("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": qid, "props": "sitelinks",
                                                              "format": "json"}).get("entities") or {}).get(qid) or {}
        return ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title")
    except Exception:
        return None


def bump(k, field="n", by=1, days=3):
    r = TABLE.update_item(Key={"k": k}, UpdateExpression="ADD #f :b SET #t = if_not_exists(#t, :t)",
                          ExpressionAttributeNames={"#f": field, "#t": "ttl"},
                          ExpressionAttributeValues={":b": by, ":t": ttl(days)}, ReturnValues="UPDATED_NEW")
    return int(r["Attributes"][field])


def context_block(facts, plot):
    lines = ["<facts>", json.dumps(facts, ensure_ascii=False), "</facts>"]
    lines += ["<plot source=\"English Wikipedia\">", plot or "(no plot available yet)", "</plot>"]
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
    key = f"ans#{fid}#{lang}#" + hashlib.sha1(nq.encode()).hexdigest()[:20]
    hit = TABLE.get_item(Key={"k": key}).get("Item")
    if hit:
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
    plot = plot_of(fid, enwiki_title(facts.pop("qid", None)))

    t0 = time.time()
    try:
        resp = client().messages.create(
            model=MODEL, max_tokens=2048,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=[{"type": "text", "text": SYSTEM}],
            messages=[{"role": "user", "content": context_block(facts, plot)
                       + f"\n\n<lang>{lang}</lang>\n<question>{q}</question>"}],
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
    TABLE.put_item(Item={"k": key, "v": json.dumps(out, ensure_ascii=False), "q": q[:240], "ttl": ttl(30)})
    out["cached"] = False
    return reply(200, origin, out)
