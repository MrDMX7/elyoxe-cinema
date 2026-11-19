"""«صوّتوا مع الربع» — the group vote (owner 2026-11-20; docs/superpowers/specs/2026-11-20-group-vote-design.md).

  POST /vote             {"options": [{city, date, cin, fid, time, hall?}, …2-4], "by": "<name>", "lang": "ar"|"en"}
                         -> {"id"}; each show is resolved against the site's own /data/<city>-<date>.json, never taken
                         from the request, so a poll can only hold real shows with the chains' own booking links
  GET  /vote/{id}        -> {"id", "by", "lang", "opts": [...], "votes": [{"p", "name", "picks", "no", "note", "at"}]}
  POST /vote/{id}        {"vk", "name", "picks": [i…], "no": bool, "note"} -> the poll as GET, plus "me": <p>
  GET  /vote/{id}/ics    the leading show as an .ics (iPhone adds it to Calendar)

A voter is a random secret kept on their phone (vk); the table and every answer hold only p = sha256(vk)[:12], so no one
can change another's vote. Caps: DAY_CAP new polls a day, VOTERS voters a poll, name ≤ 24 and note ≤ 60 characters of
plain text. Only ALLOWED_ORIGINS may write. Kill switch: the SSM parameter /elyoxe/cinema/counter/vote-off (any value).
Like the rest of this stack, no IP is read or stored. A poll expires (TTL) the day after its last show.
"""
import gzip
import hashlib
import json
import os
import re
import secrets
import time
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

DUBAI = timezone(timedelta(hours=4))
SITE = os.environ.get("SITE", "https://cinema.elyoxe.com")
ORIGINS = set(os.environ.get("ALLOWED_ORIGINS", "https://cinema.elyoxe.com").split(","))
TABLE_NAME = os.environ.get("VOTES_TABLE", "elyoxe-cinema-votes")
OFF_PARAM = os.environ.get("OFF_PARAM", "/elyoxe/cinema/counter/vote-off")
DAY_CAP = int(os.environ.get("DAY_CAP", "300"))
VOTERS = int(os.environ.get("VOTERS", "40"))
CITIES = {"dubai", "abu-dhabi", "sharjah", "al-ain", "ajman", "ras-al-khaimah", "fujairah", "umm-al-quwain"}
FID = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
DAY = re.compile(r"^\d{4}-\d\d-\d\d$")
HM = re.compile(r"^\d\d:\d\d$")
ID = re.compile(r"^[A-Za-z0-9]{10}$")
VK = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_table = None
_ssm = None
_days = {}   # (city, date) -> (fetched_at, json): this container's copy of the site's day files, 5 minutes


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _table


def switched_off():
    global _ssm
    try:
        _ssm = _ssm or boto3.client("ssm")
        _ssm.get_parameter(Name=OFF_PARAM)
        return True
    except Exception:  # noqa: BLE001 - no parameter (the normal case) or no access: on
        return False


# ------------------------------------------------------------------ plain helpers
def now_dubai():
    return datetime.now(DUBAI)


def clean(text, cap):
    """Plain text only: no control or format characters, spaces collapsed, cut at `cap` characters."""
    s = "".join(ch for ch in str(text or "") if unicodedata.category(ch)[0] != "C")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:cap].strip()


def pub(vk):
    return hashlib.sha256(vk.encode()).hexdigest()[:12]


def new_id():
    return "".join(secrets.choice(ALPHABET) for _ in range(10))


def cors(origin, methods="GET, POST, OPTIONS"):
    o = origin if origin in ORIGINS else next(iter(ORIGINS))
    return {"Access-Control-Allow-Origin": o, "Access-Control-Allow-Methods": methods,
            "Access-Control-Allow-Headers": "Content-Type", "Content-Type": "application/json", "Cache-Control": "no-store"}


def reply(status, origin, body=None):
    return {"statusCode": status, "headers": cors(origin), "body": json.dumps(body, ensure_ascii=False) if body is not None else ""}


# ------------------------------------------------------------------ the site's own data
def fetch_day(city, day):
    """The site's /data/<city>-<date>.json (the same file the old pages read), cached 5 minutes per container."""
    hit = _days.get((city, day))
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    req = urllib.request.Request(f"{SITE}/data/{city}-{day}.json",
                                 headers={"Accept-Encoding": "gzip", "User-Agent": "elyoxe-cinema-vote/1.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    j = json.loads(raw.decode("utf-8"))
    _days[(city, day)] = (time.time(), j)
    return j


def resolve(key, today):
    """One show key -> the show as the site publishes it, or None. S rows: [cinema, film, time, hall, prices, book, …]."""
    city, day, cin, fid, hm = (str(key.get(x) or "") for x in ("city", "date", "cin", "fid", "time"))
    if city not in CITIES or not DAY.match(day) or not FID.match(cin) or not FID.match(fid) or not HM.match(hm):
        return None
    d = date.fromisoformat(day)
    if not (today - timedelta(days=1) <= d <= today + timedelta(days=8)):
        return None
    try:
        j = fetch_day(city, day)
    except Exception:  # noqa: BLE001 - the file is missing or the site is unreachable: not a show we can vouch for
        return None
    C, F, H, P, B = (j.get(x) or [] for x in ("C", "F", "H", "P", "B"))
    hall = str(key.get("hall") or "")
    found = None
    for s in j.get("S") or []:
        try:
            c, f, h = C[s[0]], F[s[1]], H[s[3]]
        except (IndexError, TypeError):
            continue
        if c[0] != cin or f[0] != fid or s[2] != hm:
            continue
        found = (s, c, f, h)
        if not hall or hall in (h[2], h[3], h[0]):
            break
    if not found:
        return None
    s, c, f, h = found
    prices = [p[1] for p in (P[s[4]] if isinstance(s[4], int) and 0 <= s[4] < len(P) else []) if isinstance(p, list) and p[1]]
    # the day file splits a booking link into a shared base (B) and the show's own tail (s[6]), as home.js reads it
    tail = str(s[6]) if len(s) > 6 and s[6] else ""
    book = (B[s[5]] + tail) if isinstance(s[5], int) and 0 <= s[5] < len(B) else tail
    return {"city": city, "date": day, "time": hm, "fid": fid, "cin": cin,
            "title_ar": f[1], "title_en": f[2], "cin_ar": c[2], "cin_en": c[3], "hall_ar": h[2], "hall_en": h[3],
            "price": min(prices) if prices else None, "book": book if str(book).startswith("https://") else ""}


# ------------------------------------------------------------------ the table
def load(pid):
    """(poll, [voters]) or (None, [])."""
    items = table().query(KeyConditionExpression=Key("id").eq(pid)).get("Items", [])
    poll = next((i for i in items if i.get("k") == "poll"), None)
    return poll, [i for i in items if str(i.get("k", "")).startswith("v#")]


def save_poll(item):
    table().put_item(Item=item, ConditionExpression="attribute_not_exists(id)")


def save_vote(item):
    table().put_item(Item=item)


def count_today(day):
    """Today's new polls after this one (ADD 1)."""
    r = table().update_item(Key={"id": f"_day#{day}", "k": "n"}, UpdateExpression="ADD n :one SET #t = :ttl",
                            ExpressionAttributeNames={"#t": "ttl"},
                            ExpressionAttributeValues={":one": 1, ":ttl": int(time.time()) + 3 * 86400},
                            ReturnValues="UPDATED_NEW")
    return int(r["Attributes"]["n"])


def view(poll, voters, me=None):
    out = {"id": poll["id"], "by": poll.get("by") or "", "lang": poll.get("lang") or "ar", "opts": json.loads(poll["opts"]),
           "votes": sorted(({"p": v["k"][2:], "name": v.get("name") or "", "picks": [int(x) for x in v.get("picks") or []],
                             "no": bool(v.get("no")), "note": v.get("note") or "", "at": v.get("at") or ""} for v in voters),
                           key=lambda v: v["at"])}
    if me:
        out["me"] = me
    return out


def leader(opts, votes):
    """The index with the most votes; a tie goes to the earlier show. None when nobody picked anything."""
    n = [0] * len(opts)
    for v in votes:
        for i in v["picks"]:
            if 0 <= i < len(n):
                n[i] += 1
    if not any(n):
        return None
    return max(range(len(n)), key=lambda i: (n[i], -(i)))


def ics(opt, link):
    start = datetime.fromisoformat(f'{opt["date"]}T{opt["time"]}:00').replace(tzinfo=DUBAI).astimezone(timezone.utc)
    end = start + timedelta(hours=2, minutes=30)
    esc = lambda s: str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")  # noqa: E731
    what = f'{opt["title_ar"] or opt["title_en"]} — {opt["cin_ar"] or opt["cin_en"]}'
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Elyoxe//Cinema vote//AR", "METHOD:PUBLISH", "BEGIN:VEVENT",
                        f"UID:vote-{opt['fid']}-{opt['date']}-{opt['time'].replace(':', '')}@cinema.elyoxe.com",
                        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                        f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}", f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}",
                        f"SUMMARY:{esc(what)}", f"URL:{link}", f"DESCRIPTION:{esc(link)}",
                        "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(what)}", "TRIGGER:-PT1H", "END:VALARM",
                        "END:VEVENT", "END:VCALENDAR"]) + "\r\n"


# ------------------------------------------------------------------ the handler
def handler(event, _ctx):
    http = (event.get("requestContext") or {}).get("http") or {}
    method, path = http.get("method", ""), http.get("path") or event.get("rawPath") or ""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin", "")
    if method == "OPTIONS":
        return reply(204, origin)
    pid = ((event.get("pathParameters") or {}).get("id") or "")
    m = re.match(r"^/vote(?:/([A-Za-z0-9]+))?(/ics)?/?$", path)
    if m and not pid:
        pid = m.group(1) or ""
    is_ics = bool(m and m.group(2)) or path.endswith("/ics")

    if method == "GET":
        if not ID.match(pid):
            return reply(404, origin, {"error": "not found"})
        poll, voters = load(pid)
        if not poll:
            return reply(404, origin, {"error": "not found"})
        v = view(poll, voters)
        if is_ics:
            i = leader(v["opts"], v["votes"])
            opt = v["opts"][0 if i is None else i]
            link = f"{SITE}{'/en' if v['lang'] == 'en' else ''}/v/?p={pid}"
            return {"statusCode": 200, "body": ics(opt, link),
                    "headers": {"Content-Type": "text/calendar; charset=utf-8", "Cache-Control": "no-store",
                                "Content-Disposition": f'attachment; filename="cinema-{pid}.ics"'}}
        return reply(200, origin, v)

    if method != "POST":
        return reply(405, origin, {"error": "method"})
    if origin not in ORIGINS:
        return reply(403, origin, {"error": "origin"})
    try:
        data = json.loads((event.get("body") or "")[:6000] or "{}")
    except ValueError:
        return reply(400, origin, {"error": "json"})
    if not isinstance(data, dict):
        return reply(400, origin, {"error": "json"})
    if switched_off():
        return reply(503, origin, {"error": "off"})
    today = now_dubai().date()

    if not pid:   # a new poll
        keys = data.get("options")
        if not isinstance(keys, list) or not 2 <= len(keys) <= 4:
            return reply(400, origin, {"error": "options"})
        opts, seen = [], set()
        for k in keys:
            o = resolve(k if isinstance(k, dict) else {}, today)
            if not o:
                return reply(422, origin, {"error": "show", "key": k})
            sig = (o["fid"], o["cin"], o["date"], o["time"])
            if sig not in seen:
                seen.add(sig)
                opts.append(o)
        if len(opts) < 2:
            return reply(400, origin, {"error": "options"})
        if count_today(today.isoformat()) > DAY_CAP:
            return reply(429, origin, {"error": "cap"})
        last = max(date.fromisoformat(o["date"]) for o in opts)
        ttl = int(datetime.combine(last + timedelta(days=2), datetime.min.time(), DUBAI).timestamp())
        for _ in range(3):
            item = {"id": new_id(), "k": "poll", "opts": json.dumps(opts, ensure_ascii=False), "by": clean(data.get("by"), 24),
                    "lang": "en" if data.get("lang") == "en" else "ar", "created": now_dubai().isoformat(timespec="seconds"),
                    "ttl": ttl}
            try:
                save_poll(item)
                return reply(201, origin, {"id": item["id"]})
            except Exception as e:  # noqa: BLE001 - an id collision (ConditionalCheckFailed): draw again
                if "ConditionalCheckFailed" not in type(e).__name__ + str(e):
                    raise
        return reply(500, origin, {"error": "id"})

    # a vote
    if not ID.match(pid):
        return reply(404, origin, {"error": "not found"})
    vk = str(data.get("vk") or "")
    name = clean(data.get("name"), 24)
    if not VK.match(vk) or not name:
        return reply(400, origin, {"error": "who"})
    poll, voters = load(pid)
    if not poll:
        return reply(404, origin, {"error": "not found"})
    n = len(json.loads(poll["opts"]))
    picks = data.get("picks") or []
    if not isinstance(picks, list) or any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < n for i in picks):
        return reply(400, origin, {"error": "picks"})
    picks = sorted(set(picks))
    no = bool(data.get("no")) and not picks
    me = pub(vk)
    if f"v#{me}" not in {v["k"] for v in voters} and len(voters) >= VOTERS:
        return reply(429, origin, {"error": "full"})
    item = {"id": pid, "k": f"v#{me}", "name": name, "picks": picks, "no": no, "note": clean(data.get("note"), 60),
            "at": now_dubai().isoformat(timespec="seconds"), "ttl": int(poll["ttl"])}
    save_vote(item)
    voters = [v for v in voters if v["k"] != item["k"]] + [item]
    return reply(200, origin, view(poll, voters, me=me))
