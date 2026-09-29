"""ingest.py — POST /events. The only write path into the counter. Stores no cookie, no id and no
IP: `event["requestContext"]["http"]["sourceIp"]` is never read, and nothing here logs the raw
`event` (which would carry the caller's IP in that same field) — only the small derived values
below ever reach `print()`. The client sends one JSON body per beacon:

    {"page": "home"|"film"|"cinema"|"city"|"coming",
     "event": "view"|"ticket_open"|"book_click"|"return",
     "return_bucket": "0"|"1"|"2-7"|"8-30"|"30+",   # only with event == "return", computed on the device
     "ttb_bucket": "0-3s"|"3-10s"|"10-30s"|"30s+",  # optional, only on a "book_click" (landing -> tapped «احجز»)
     "uid": "<opaque daily-rotating salted hash, client-computed, <=128 chars>"}  # optional

`uid` is never a cookie and never persists across days — it is an opaque, client-generated id
(date + a random value, no server-side salt or hash) that the client itself re-rolls every day
(plan §3.2 R15), stored here only long enough (2-day TTL, UniquesTable) to answer "how many
distinct ids did we see today", never "who is this".
"""
import json
import os
from datetime import datetime, timedelta, timezone

import boto3

DUBAI = timezone(timedelta(hours=4))
ddb = boto3.resource("dynamodb")
metrics = ddb.Table(os.environ["METRICS_TABLE"])
uniques = ddb.Table(os.environ["UNIQUES_TABLE"])
ORIGINS = set(os.environ["ALLOWED_ORIGINS"].split(","))

PAGES = {"home", "film", "cinema", "city", "coming", "_"}
EVENTS = {"view", "ticket_open", "book_click", "return"}
RETURN_BUCKETS = {"0", "1", "2-7", "8-30", "30+"}
TTB_BUCKETS = {"0-3s", "3-10s", "10-30s", "30s+"}


def cors(origin):
    o = origin if origin in ORIGINS else next(iter(ORIGINS))
    return {"Access-Control-Allow-Origin": o, "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Content-Type": "application/json"}


def reply(status, origin, body=""):
    return {"statusCode": status, "headers": cors(origin), "body": body}


def today_dubai():
    return datetime.now(DUBAI).strftime("%Y-%m-%d")


def bump(date, key, n=1):
    metrics.update_item(Key={"d": date, "k": key},
                         UpdateExpression="ADD n :n", ExpressionAttributeValues={":n": n})


def handler(event, _ctx):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin", "")
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")
    if method == "OPTIONS":
        return reply(204, origin)
    if method != "POST":
        return reply(405, origin)
    if origin not in ORIGINS:
        return reply(403, origin)

    raw = (event.get("body") or "")[:2000]
    try:
        data = json.loads(raw)
    except ValueError:
        return reply(400, origin)
    if not isinstance(data, dict):
        return reply(400, origin)

    page = data.get("page") if data.get("page") in PAGES else "_"
    ev = data.get("event")
    if ev not in EVENTS:
        return reply(400, origin)

    date = today_dubai()
    bump(date, f"{page}#{ev}")

    if ev == "return":
        rb = data.get("return_bucket")
        if rb in RETURN_BUCKETS:
            bump(date, f"_#return#{rb}")

    ttb = data.get("ttb_bucket")
    if ev == "book_click" and ttb in TTB_BUCKETS:
        bump(date, f"_#ttb#{ttb}")

    uid = data.get("uid")
    if isinstance(uid, str) and 0 < len(uid) <= 128:
        ttl = int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp())
        try:
            uniques.put_item(Item={"d": date, "h": uid, "ttl": ttl})
        except Exception:
            pass  # a beacon never fails the visitor's page over a missed unique count

    return reply(204, origin)
