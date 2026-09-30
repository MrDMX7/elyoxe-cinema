"""push_weekly.py — EventBridge Schedule, Thursday 08:00 UTC = 12:00 Asia/Dubai. The only
scheduled sender in this stack: ≤ 1 push a day, ≤ 1 a week (well inside the plan's ≤1/day, ≤3/week
cap), never a price drop [feedback rejected item #38]. Reads the new-release list from the site's
own already-public `data/coming.json` (pages/coming.py already publishes it — nothing new is
added to the site build) and pushes only to subscriptions with topic "weekly". Idempotent: a
retry or a second EventBridge fire the same week is a no-op (MetricsTable "_meta" row remembers
the last Thursday sent).
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3

DUBAI = timezone(timedelta(hours=4))
ddb = boto3.resource("dynamodb")
subs_table = ddb.Table(os.environ["SUBS_TABLE"])
metrics = ddb.Table(os.environ["METRICS_TABLE"])
ssm = boto3.client("ssm")

COMING_URL = os.environ["COMING_URL"]
VAPID_SUBJECT = os.environ["VAPID_SUBJECT"]


def this_thursday_dubai():
    today = datetime.now(DUBAI).date()
    days_ahead = (3 - today.weekday()) % 7  # Monday=0 … Thursday=3
    return today + timedelta(days=days_ahead)


def already_sent(thursday_iso):
    r = metrics.get_item(Key={"d": "_meta", "k": "push-last-thursday"})
    return r.get("Item", {}).get("n_s") == thursday_iso


def mark_sent(thursday_iso):
    metrics.put_item(Item={"d": "_meta", "k": "push-last-thursday", "n_s": thursday_iso})


def fetch_coming():
    try:
        with urllib.request.urlopen(COMING_URL, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"push_weekly: coming.json fetch failed: {type(e).__name__}")
        return {}


def build_payload(thursday_iso, coming):
    titles = []
    for film in coming.values():
        if film.get("release_date") == thursday_iso:
            titles.append(film.get("title_ar") or film.get("title") or "")
    titles = [t for t in titles if t]
    # "وغيرها" counts this Thursday's own matches, not the whole (116-entry) coming.json —
    # otherwise a Thursday with a single release still claims "and others" (review r3-backend,
    # Important #5).
    shown, rest = titles[:3], titles[3:]
    if shown:
        body = "الخميس: " + "، ".join(shown) + (" وغيرها" if rest else "")
    else:
        body = "أفلام جديدة هالخميس — شوف القائمة"
    return {"title": "سينما", "body": body, "url": "https://cinema.elyoxe.com/coming/"}


def vapid_private_key():
    return ssm.get_parameter(Name=os.environ["VAPID_PRIVATE_PARAM"], WithDecryption=True)["Parameter"]["Value"]


def send_all(payload, private_key):
    from pywebpush import WebPushException, webpush  # only the scheduled sender needs the layer
    sent = failed = pruned = 0
    scan_kwargs = {"FilterExpression": "#t = :w", "ExpressionAttributeNames": {"#t": "topic"},
                    "ExpressionAttributeValues": {":w": "weekly"}}
    last_key = None
    claims = {"sub": VAPID_SUBJECT}
    while True:
        if last_key:
            scan_kwargs["ExclusiveStartKey"] = last_key
        page = subs_table.scan(**scan_kwargs)
        for item in page.get("Items", []):
            sub_info = {"endpoint": item["endpoint"], "keys": {"p256dh": item["p256dh"], "auth": item["auth"]}}
            try:
                webpush(subscription_info=sub_info, data=json.dumps(payload),
                        vapid_private_key=private_key, vapid_claims=dict(claims), ttl=86400)
                sent += 1
            except WebPushException as e:
                code = getattr(e.response, "status_code", None)
                if code in (404, 410):
                    subs_table.delete_item(Key={"endpoint": item["endpoint"]})
                    pruned += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            time.sleep(0.05)  # a courteous pace; subscriber counts are small (free-tier scale)
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            break
    return sent, failed, pruned


def handler(_event, _ctx):
    thursday_iso = this_thursday_dubai().isoformat()
    if already_sent(thursday_iso):
        print(f"push_weekly: already sent for {thursday_iso}, skipping")
        return {"ok": True, "skipped": True}

    coming = fetch_coming()
    payload = build_payload(thursday_iso, coming)
    private_key = vapid_private_key()
    sent, failed, pruned = send_all(payload, private_key)
    # Only mark this Thursday "sent" if at least one push went out (or there was simply nothing
    # to send to). A week where every send failed retries on the next EventBridge fire instead of
    # being silently skipped for the rest of the week (review r3-backend, Minor).
    if failed == 0 or sent > 0:
        mark_sent(thursday_iso)
    try:
        metrics.update_item(Key={"d": thursday_iso, "k": "_#push#sent"},
                             UpdateExpression="ADD n :n", ExpressionAttributeValues={":n": sent})
    except Exception:
        pass
    print(f"push_weekly: {thursday_iso} sent={sent} failed={failed} pruned={pruned}")
    return {"ok": True, "sent": sent, "failed": failed, "pruned": pruned}
