"""stats.py — GET /stats?secret=…, the owner's own small numbers page (plan §3.2 R15: "a weekly
numbers line in the Monday report"). No auth system — a long random secret in the URL, per the
owner's own call on this account (feedback_aws_root_access.md: secrets in the URL/chat are
accepted here). `?format=json` returns the same numbers as JSON for the Monday report script.
noindex, no client-side JS, nothing cached (CloudFront never sees this path — it is called
directly against the API's own URL, never through the site's distribution).
"""
import json
import os
from datetime import datetime, timedelta, timezone

import boto3

DUBAI = timezone(timedelta(hours=4))
ddb = boto3.resource("dynamodb")
metrics = ddb.Table(os.environ["METRICS_TABLE"])
uniques = ddb.Table(os.environ["UNIQUES_TABLE"])
ssm = boto3.client("ssm")

PAGE_LABELS_AR = {"home": "الرئيسية", "film": "الفيلم", "cinema": "السينما", "city": "المدينة", "coming": "قريباً", "_": "عام"}


def dates_back(n):
    today = datetime.now(DUBAI).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n)]


def day_metrics(date):
    r = metrics.query(KeyConditionExpression="d = :d", ExpressionAttributeValues={":d": date})
    return {i["k"]: int(i["n"]) for i in r.get("Items", [])}


def day_uniques(date):
    r = uniques.query(KeyConditionExpression="d = :d", ExpressionAttributeValues={":d": date}, Select="COUNT")
    return int(r.get("Count", 0))


def aggregate(n_days):
    totals = {}
    unique_by_day = {}
    for date in dates_back(n_days):
        for k, n in day_metrics(date).items():
            totals[k] = totals.get(k, 0) + n
        unique_by_day[date] = day_uniques(date)
    return totals, unique_by_day


def check_secret(qs):
    try:
        want = ssm.get_parameter(Name=os.environ["SECRET_PARAM"], WithDecryption=True)["Parameter"]["Value"]
    except Exception:
        return False
    got = (qs or {}).get("secret", "")
    return bool(got) and got == want


def render_json(totals7, uniq7, totals30, uniq30):
    def shape(totals, uniq):
        views = {k: v for k, v in totals.items() if k.endswith("#view")}
        ticket_open = {k: v for k, v in totals.items() if k.endswith("#ticket_open")}
        book_click = {k: v for k, v in totals.items() if k.endswith("#book_click")}
        returns = {k.split("#")[-1]: v for k, v in totals.items() if k.startswith("_#return#")}
        ttb = {k.split("#", 2)[-1]: v for k, v in totals.items() if k.startswith("_#ttb#")}
        return {"views": views, "ticket_open": ticket_open, "book_click": book_click,
                "return_buckets": returns, "ttb_buckets": ttb, "unique_visitors_sum": sum(uniq.values()),
                "unique_visitors_by_day": uniq}
    return {"last_7d": shape(totals7, uniq7), "last_30d": shape(totals30, uniq30)}


def render_html(data):
    def rows(d):
        return "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in sorted(d.items()))
    j = data
    body = f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow"><title>أرقام سينما — للمالك فقط</title>
<style>body{{font-family:system-ui;background:#141A17;color:#F4F2ED;padding:24px}}
table{{border-collapse:collapse;margin:12px 0}}td{{padding:4px 12px;border-bottom:1px solid #333}}
h2{{color:#F0BC5A}}</style></head><body>
<h1>أرقام سينما</h1>
<p>آخر 7 أيام مقابل آخر 30 — ولا كوكيز ولا آي بي محفوظ.</p>
<h2>آخر 7 أيام — زوّار فريدون: {j['last_7d']['unique_visitors_sum']}</h2>
<table>{rows(j['last_7d']['views'])}</table>
<h3>حجز «احجز»</h3><table>{rows(j['last_7d']['book_click'])}</table>
<h3>رجعة الزوّار (return bucket)</h3><table>{rows(j['last_7d']['return_buckets'])}</table>
<h3>سرعة الوصول لـ«احجز» (TTB)</h3><table>{rows(j['last_7d']['ttb_buckets'])}</table>
<h2>آخر 30 يوم — زوّار فريدون: {j['last_30d']['unique_visitors_sum']}</h2>
<table>{rows(j['last_30d']['views'])}</table>
</body></html>"""
    return body


def handler(event, _ctx):
    qs = event.get("queryStringParameters") or {}
    if not check_secret(qs):
        return {"statusCode": 403, "headers": {"Content-Type": "text/plain; charset=utf-8"}, "body": "forbidden"}

    totals7, uniq7 = aggregate(7)
    totals30, uniq30 = aggregate(30)
    data = render_json(totals7, uniq7, totals30, uniq30)

    if qs.get("format") == "json":
        return {"statusCode": 200, "headers": {"Content-Type": "application/json; charset=utf-8"},
                "body": json.dumps(data, ensure_ascii=False)}

    return {"statusCode": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8", "X-Robots-Tag": "noindex, nofollow"},
            "body": render_html(data)}
