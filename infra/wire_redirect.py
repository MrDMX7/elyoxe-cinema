"""Cutover (Task 5), idempotent: make the old elyoxe.com/cinema* and /en/cinema* URLs answer 301 to
https://cinema.elyoxe.com with the same path. Creates/updates + publishes the CloudFront Function
`elyoxe-cinema-moved` from infra/redirect.js, then sets it as the (only) viewer-request function of
the /cinema* and /en/cinema* behaviors on E2QY4WECG1P5WO. Nothing else in that distribution changes.
  python infra/wire_redirect.py            # dry run: prints what would change, touches nothing
  python infra/wire_redirect.py --apply
Undo: set those two behaviors' FunctionAssociations back to the shared `static-rewrite` function
(the value printed as "before" by the dry run) with update-distribution, then
`aws cloudfront delete-function --name elyoxe-cinema-moved --if-match <etag>`.
"""
import json, os, subprocess, sys, tempfile

DIST = "E2QY4WECG1P5WO"
NAME = "elyoxe-cinema-moved"
PATTERNS = ["/cinema*", "/en/cinema*"]
CODE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "redirect.js")
APPLY = "--apply" in sys.argv


def aws(*a, ok_fail=False):
    r = subprocess.run(["aws", *a, "--output", "json"], capture_output=True, text=True)
    if r.returncode:
        if ok_fail:
            return None
        sys.exit(f"aws {' '.join(a[:2])} failed:\n{r.stderr}")
    return json.loads(r.stdout or "{}")


def tmpfile(data, suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


code = open(CODE, "rb").read()
cfg_fn = json.dumps({"Comment": "301 elyoxe.com/cinema -> cinema.elyoxe.com", "Runtime": "cloudfront-js-2.0"})

# 1) the function
desc = aws("cloudfront", "describe-function", "--name", NAME, "--stage", "DEVELOPMENT", ok_fail=True)
if desc is None:
    fn_action = "create + publish"
else:
    path = tmpfile(b"", ".js")
    try:
        subprocess.run(["aws", "cloudfront", "get-function", "--name", NAME, "--stage", "DEVELOPMENT", path],
                       check=True, capture_output=True)
        dev = open(path, "rb").read()
    finally:
        os.remove(path)
    live = aws("cloudfront", "describe-function", "--name", NAME, "--stage", "LIVE", ok_fail=True)
    if dev != code:
        fn_action = "update + publish"
    elif live is None or live["FunctionSummary"]["FunctionMetadata"]["LastModifiedTime"] != \
            desc["FunctionSummary"]["FunctionMetadata"]["LastModifiedTime"]:
        fn_action = "publish"
    else:
        fn_action = None
print("function", NAME + ":", fn_action or "up to date")

acct = aws("sts", "get-caller-identity")["Account"]
arn = f"arn:aws:cloudfront::{acct}:function/{NAME}"
want = {"Quantity": 1, "Items": [{"FunctionARN": arn, "EventType": "viewer-request"}]}

# 2) the behaviors
cur = aws("cloudfront", "get-distribution-config", "--id", DIST)
etag, cfg = cur["ETag"], cur["DistributionConfig"]
items = cfg.get("CacheBehaviors", {}).get("Items", [])
changes = []
for pat in PATTERNS:
    b = next((x for x in items if x["PathPattern"] == pat), None)
    if b is None:
        sys.exit(f"behavior {pat} missing on {DIST} — nothing to attach to")
    before = b.get("FunctionAssociations", {"Quantity": 0})
    if before != want:
        changes.append((pat, before))
        b["FunctionAssociations"] = want
for pat, before in changes:
    print(f"behavior {pat}: viewer-request {json.dumps(before)}\n    -> {json.dumps(want)}")
if not changes:
    print("behaviors: already wired")
if not fn_action and not changes:
    print("nothing to do"); sys.exit(0)
if not APPLY:
    print("dry run — rerun with --apply"); sys.exit(0)

# --- apply ---
if fn_action:
    path = tmpfile(code, ".js")
    try:
        fpath = "fileb://" + path.replace("\\", "/")
        if fn_action.startswith("create"):
            r = aws("cloudfront", "create-function", "--name", NAME, "--function-config", cfg_fn, "--function-code", fpath)
        elif fn_action.startswith("update"):
            r = aws("cloudfront", "update-function", "--name", NAME, "--if-match", desc["ETag"],
                    "--function-config", cfg_fn, "--function-code", fpath)
        else:
            r = desc
    finally:
        os.remove(path)
    r = aws("cloudfront", "publish-function", "--name", NAME, "--if-match", r["ETag"])
    print("function published:", r["FunctionSummary"]["FunctionMetadata"]["FunctionARN"])
if changes:
    path = tmpfile(json.dumps(cfg).encode(), ".json")
    try:
        r = aws("cloudfront", "update-distribution", "--id", DIST, "--if-match", etag,
                "--distribution-config", "file://" + path.replace("\\", "/"))
    finally:
        os.remove(path)
    print("distribution updated, status", r["Distribution"]["Status"])
