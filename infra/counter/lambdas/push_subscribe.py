"""push_subscribe.py — POST/DELETE /push/subscribe. Called only after an explicit tap
(«ذكّرني بالخميس» — plan §3.5 "Web Push for saved films only" / owner request 2026-09-30),
never on page load. Stores the browser's PushSubscription (endpoint + keys) so push_weekly.py
can address it later; nothing else about the visitor is stored here.
"""
import json
import os
import time

import boto3

ddb = boto3.resource("dynamodb")
subs = ddb.Table(os.environ["SUBS_TABLE"])
ORIGINS = set(os.environ["ALLOWED_ORIGINS"].split(","))


def cors(origin):
    o = origin if origin in ORIGINS else next(iter(ORIGINS))
    return {"Access-Control-Allow-Origin": o, "Access-Control-Allow-Methods": "POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Content-Type": "application/json"}


def reply(status, origin, body=None):
    return {"statusCode": status, "headers": cors(origin), "body": json.dumps(body) if body is not None else ""}


def handler(event, _ctx):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin", "")
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")
    if method == "OPTIONS":
        return reply(204, origin)
    if origin not in ORIGINS:
        return reply(403, origin)

    try:
        data = json.loads((event.get("body") or "{}")[:4000])
    except ValueError:
        return reply(400, origin)

    endpoint = (data.get("endpoint") or "")[:1000]
    if not endpoint.startswith("https://"):
        return reply(400, origin)

    if method == "DELETE":
        subs.delete_item(Key={"endpoint": endpoint})
        return reply(204, origin)

    if method != "POST":
        return reply(405, origin)

    keys = data.get("keys") or {}
    p256dh = (keys.get("p256dh") or "")[:200]
    auth = (keys.get("auth") or "")[:200]
    if not p256dh or not auth:
        return reply(400, origin)
    topic = "weekly" if data.get("topic") != "weekly-off" else "weekly-off"

    subs.put_item(Item={"endpoint": endpoint, "p256dh": p256dh, "auth": auth,
                         "topic": topic, "created_at": int(time.time())})
    return reply(204, origin)
