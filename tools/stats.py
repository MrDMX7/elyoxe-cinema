"""stats.py — the counter's numbers, for the owner and the Monday report (plan §3.2 R15).

    python tools/stats.py            a short Arabic summary: visitors and views per page, 7 and 30 days
    python tools/stats.py --json     the raw JSON the stats endpoint returns
    python tools/stats.py --url      the owner's HTML page URL (secret included — his own account, his call)

Reads the endpoint from counter.yaml and the secret from SSM /elyoxe/cinema/counter/stats-secret (ap-south-1),
then GET {api}stats?format=json&secret=… — the API's own URL, never through the site's distribution. Nothing
here writes anything.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_AR = {"home": "الرئيسية", "film": "الفيلم", "cinema": "السينما", "city": "المدينة", "coming": "قريباً", "_": "باقي الصفحات"}


def endpoint() -> str:
    import yaml
    with open(os.path.join(ROOT, "counter.yaml"), encoding="utf-8") as f:
        return (yaml.safe_load(f) or {})["api"]


def secret() -> str:
    import boto3
    ssm = boto3.client("ssm", region_name="ap-south-1")
    return ssm.get_parameter(Name="/elyoxe/cinema/counter/stats-secret", WithDecryption=True)["Parameter"]["Value"]


def fetch() -> dict:
    url = endpoint() + "stats?" + urllib.parse.urlencode({"format": "json", "secret": secret()})
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def summary(data: dict) -> str:
    out = []
    for key, label in (("last_7d", "آخر 7 أيام"), ("last_30d", "آخر 30 يوم")):
        d = data.get(key) or {}
        views = d.get("views") or {}
        total = sum(views.values())
        out.append(f"{label}: {d.get('unique_visitors_sum', 0)} زائر، {total} مشاهدة صفحة")
        by_page = sorted(((PAGES_AR.get(k.split('#')[0], k), v) for k, v in views.items()), key=lambda kv: -kv[1])
        if by_page:
            out.append("  الصفحات: " + " · ".join(f"{n} {v}" for n, v in by_page))
        bc = sum((d.get("book_click") or {}).values())
        if bc:
            out.append(f"  ضغطات «احجز»: {bc}" + (f" — سرعة الوصول: " + " · ".join(f"{k} {v}" for k, v in sorted((d.get('ttb_buckets') or {}).items())) if d.get("ttb_buckets") else ""))
        rb = d.get("return_buckets") or {}
        if rb:
            out.append("  رجعة الزوّار (أيام): " + " · ".join(f"{k}: {v}" for k, v in sorted(rb.items())))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if "--url" in argv:
        print(endpoint() + "stats?" + urllib.parse.urlencode({"secret": secret()}))
        return 0
    data = fetch()
    print(json.dumps(data, ensure_ascii=False, indent=2) if "--json" in argv else summary(data))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
