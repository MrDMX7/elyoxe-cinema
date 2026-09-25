"""One-time, idempotent: route /cinema* and /en/cinema* on the production distribution to the
existing "tools" origin (the elyoxe-tools bucket, where deploy.sh publishes cinema/ and en/cinema/).
Each new behavior is a copy of the live /tools* behavior (same cache policy, viewer-request
function, protocol policy) with only PathPattern changed. Nothing else in the distribution is touched.
  python wire_cloudfront.py            # dry run: prints the diff
  python wire_cloudfront.py --apply
Undo: delete the two behaviors (remove them from the config and update-distribution with the ETag).
"""
import json, os, subprocess, sys, tempfile

DIST = "E2QY4WECG1P5WO"
ORIGIN_ID = "tools"
TEMPLATE = "/tools*"
PATTERNS = ["/cinema*", "/en/cinema*"]


def aws(*a):
    return json.loads(subprocess.run(["aws", *a, "--output", "json"], check=True, capture_output=True, text=True).stdout or "{}")


cur = aws("cloudfront", "get-distribution-config", "--id", DIST)
etag, cfg = cur["ETag"], cur["DistributionConfig"]
before = json.dumps(cfg, sort_keys=True)
if not any(o["Id"] == ORIGIN_ID for o in cfg["Origins"]["Items"]):
    sys.exit(f"origin {ORIGIN_ID!r} missing — run saas/tools/wire_cloudfront.py first")
beh = cfg["CacheBehaviors"]
items = beh.setdefault("Items", [])
tmpl = next((b for b in items if b["PathPattern"] == TEMPLATE), None)
if tmpl is None:
    sys.exit(f"behavior {TEMPLATE} missing — nothing to copy")
have = {b["PathPattern"] for b in items}
added = []
for pat in PATTERNS:
    if pat in have:
        continue
    b = json.loads(json.dumps(tmpl))
    b["PathPattern"] = pat
    b["TargetOriginId"] = ORIGIN_ID
    items.append(b); added.append(pat)
beh["Quantity"] = len(items)
if json.dumps(cfg, sort_keys=True) == before:
    print("already wired — nothing to do"); sys.exit(0)
print("adding:", added, "(copies of", TEMPLATE + ")")
print("behaviors after:", [b["PathPattern"] + " -> " + b["TargetOriginId"] for b in items])
if "--apply" not in sys.argv:
    print("dry run — rerun with --apply"); sys.exit(0)
fd, path = tempfile.mkstemp(suffix=".json")
with os.fdopen(fd, "w") as f:
    json.dump(cfg, f)
try:
    r = aws("cloudfront", "update-distribution", "--id", DIST, "--if-match", etag,
            "--distribution-config", "file://" + path.replace("\\", "/"))
finally:
    os.remove(path)
print("updated, status", r["Distribution"]["Status"])
