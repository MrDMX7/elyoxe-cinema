"""City from the network (roadmap 237), idempotent: https://cinema.elyoxe.com/geo answers
{"city": "<slug>"|null} from CloudFront's geolocation of the viewer (infra/geo.js), same origin, private, no-store.
Touches the cinema distribution E1200YJEC3LL6I only (never E2QY4WECG1P5WO):
  1. CloudFront Function `elyoxe-cinema-geo` from infra/geo.js (create/update + publish)
  2. origin request policy `elyoxe-cinema-geo`: forwards only CloudFront-Viewer-Country, -City, -Country-Region,
     -Country-Region-Name — without it a viewer-request function never sees those headers
  3. a `/geo` cache behavior: CachingDisabled, that policy, that function (it answers; the bucket is never asked)
  python infra/geo.py            # dry run: prints what would change, touches nothing
  python infra/geo.py --apply    # apply, wait for the deployment, then GET /geo once
  python infra/geo.py --undo     # remove the /geo behavior (add --apply to do it); the function and policy stay
Undo in full: `--undo --apply`, then `aws cloudfront delete-function --name elyoxe-cinema-geo --if-match <etag>`
and `aws cloudfront delete-origin-request-policy --id <id> --if-match <etag>`.
infra/template.yaml now carries the same function, policy and behavior; infra/geo_stack.py imports the two
resources into the elyoxe-cinema stack and then lets it own the behavior. Until that has run, a stack update that
replaces DistributionConfig from an older template drops /geo — rerun this script after one.
Nothing here logs a request; the distribution's standard logging is off.
"""
import json, os, subprocess, sys, tempfile, time, urllib.request

DIST = "E1200YJEC3LL6I"
NEVER = "E2QY4WECG1P5WO"
NAME = "elyoxe-cinema-geo"
PATTERN = "/geo"
HEADERS = ["CloudFront-Viewer-City", "CloudFront-Viewer-Country", "CloudFront-Viewer-Country-Region",
           "CloudFront-Viewer-Country-Region-Name"]
CACHING_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"   # Managed-CachingDisabled
CODE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo.js")
URL = "https://cinema.elyoxe.com/geo"
APPLY, UNDO = "--apply" in sys.argv, "--undo" in sys.argv
assert DIST != NEVER


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


def fileuri(path, scheme="file"):
    return f"{scheme}://" + path.replace("\\", "/")


def policy_config():
    return {"Name": NAME, "Comment": "viewer geolocation for /geo (city from the network)",
            "HeadersConfig": {"HeaderBehavior": "whitelist", "Headers": {"Quantity": len(HEADERS), "Items": sorted(HEADERS)}},
            "CookiesConfig": {"CookieBehavior": "none"}, "QueryStringsConfig": {"QueryStringBehavior": "none"}}


def find_policy():
    items = (aws("cloudfront", "list-origin-request-policies", "--type", "custom")
             .get("OriginRequestPolicyList", {}).get("Items") or [])
    for it in items:
        p = it["OriginRequestPolicy"]
        if p["OriginRequestPolicyConfig"]["Name"] == NAME:
            return p
    return None


def same_policy(cfg):
    h = cfg.get("HeadersConfig", {})
    return (h.get("HeaderBehavior") == "whitelist" and sorted(h.get("Headers", {}).get("Items") or []) == sorted(HEADERS)
            and cfg.get("CookiesConfig", {}).get("CookieBehavior") == "none"
            and cfg.get("QueryStringsConfig", {}).get("QueryStringBehavior") == "none")


def stage_code(stage):
    path = tmpfile(b"", ".js")
    try:
        r = subprocess.run(["aws", "cloudfront", "get-function", "--name", NAME, "--stage", stage, path], capture_output=True)
        return open(path, "rb").read() if r.returncode == 0 else None
    finally:
        os.remove(path)


def function_state(code):
    desc = aws("cloudfront", "describe-function", "--name", NAME, "--stage", "DEVELOPMENT", ok_fail=True)
    if desc is None:
        return "create + publish", None
    if stage_code("DEVELOPMENT") != code:
        return "update + publish", desc
    if stage_code("LIVE") != code:
        return "publish", desc
    return None, desc


def behavior(default, fn_arn, policy_id):
    b = json.loads(json.dumps(default))      # the default behavior's shape (origin, protocol, methods), then ours
    b.update({"PathPattern": PATTERN, "Compress": False, "CachePolicyId": CACHING_DISABLED, "OriginRequestPolicyId": policy_id,
              "FunctionAssociations": {"Quantity": 1, "Items": [{"FunctionARN": fn_arn, "EventType": "viewer-request"}]},
              "LambdaFunctionAssociations": {"Quantity": 0},
              "AllowedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"], "CachedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"]}}})
    for k in ("ResponseHeadersPolicyId", "RealtimeLogConfigArn", "ForwardedValues", "MinTTL", "DefaultTTL", "MaxTTL"):
        b.pop(k, None)
    return b


def update_distribution(cfg, etag):
    path = tmpfile(json.dumps(cfg).encode(), ".json")
    try:
        r = aws("cloudfront", "update-distribution", "--id", DIST, "--if-match", etag, "--distribution-config", fileuri(path))
    finally:
        os.remove(path)
    print("distribution updated, status", r["Distribution"]["Status"], flush=True)
    print("waiting for the deployment (a few minutes) …", flush=True)
    w = subprocess.run(["aws", "cloudfront", "wait", "distribution-deployed", "--id", DIST])
    if w.returncode:
        sys.exit("wait distribution-deployed failed")
    print("deployed")


def main():
    code = open(CODE, "rb").read()
    cur = aws("cloudfront", "get-distribution-config", "--id", DIST)
    etag, cfg = cur["ETag"], cur["DistributionConfig"]
    cbs = cfg.setdefault("CacheBehaviors", {"Quantity": 0})
    items = cbs.get("Items") or []
    have = next((x for x in items if x["PathPattern"] == PATTERN), None)

    if UNDO:
        if have is None:
            print("behavior", PATTERN, "absent — nothing to undo"); return
        print("behavior", PATTERN, "-> remove")
        if not APPLY:
            print("dry run — rerun with --undo --apply"); return
        items = [x for x in items if x["PathPattern"] != PATTERN]
        cfg["CacheBehaviors"] = {"Quantity": len(items), **({"Items": items} if items else {})}
        update_distribution(cfg, etag)
        return

    fn_action, desc = function_state(code)
    print("function", NAME + ":", fn_action or "up to date")
    pol = find_policy()
    pol_action = "create" if pol is None else (None if same_policy(pol["OriginRequestPolicyConfig"]) else "update")
    print("origin request policy", NAME + ":", pol_action or "up to date")

    acct = aws("sts", "get-caller-identity")["Account"]
    fn_arn = f"arn:aws:cloudfront::{acct}:function/{NAME}"
    want = behavior(cfg["DefaultCacheBehavior"], fn_arn, pol["Id"] if pol else "<new policy id>")
    if have is None:
        b_action = "add"
    else:
        diff = {k: (have.get(k), v) for k, v in want.items() if have.get(k) != v}
        b_action = "update" if diff else None
        if diff:
            for k, (a, b) in diff.items():
                print(f"  {k}: {json.dumps(a)} -> {json.dumps(b)}")
    print("behavior", PATTERN, "on", DIST + ":", b_action or "up to date")
    if not (fn_action or pol_action or b_action):
        print("nothing to do")
    elif not APPLY:
        print("dry run — rerun with --apply"); return
    else:
        if fn_action:
            path = tmpfile(code, ".js")
            fcfg = json.dumps({"Comment": "cinema /geo: city from the network", "Runtime": "cloudfront-js-2.0"})
            try:
                if fn_action.startswith("create"):
                    r = aws("cloudfront", "create-function", "--name", NAME, "--function-config", fcfg,
                            "--function-code", fileuri(path, "fileb"))
                elif fn_action.startswith("update"):
                    r = aws("cloudfront", "update-function", "--name", NAME, "--if-match", desc["ETag"],
                            "--function-config", fcfg, "--function-code", fileuri(path, "fileb"))
                else:
                    r = desc
            finally:
                os.remove(path)
            r = aws("cloudfront", "publish-function", "--name", NAME, "--if-match", r["ETag"])
            print("function published:", r["FunctionSummary"]["FunctionMetadata"]["FunctionARN"])
        if pol_action:
            path = tmpfile(json.dumps(policy_config()).encode(), ".json")
            try:
                if pol_action == "create":
                    pol = aws("cloudfront", "create-origin-request-policy", "--origin-request-policy-config", fileuri(path))["OriginRequestPolicy"]
                else:
                    e = aws("cloudfront", "get-origin-request-policy", "--id", pol["Id"])["ETag"]
                    pol = aws("cloudfront", "update-origin-request-policy", "--id", pol["Id"], "--if-match", e,
                              "--origin-request-policy-config", fileuri(path))["OriginRequestPolicy"]
            finally:
                os.remove(path)
            print("origin request policy:", pol["Id"])
        if b_action:
            want = behavior(cfg["DefaultCacheBehavior"], fn_arn, pol["Id"])
            items = [x for x in items if x["PathPattern"] != PATTERN] + [want]
            cfg["CacheBehaviors"] = {"Quantity": len(items), "Items": items}
            update_distribution(cfg, etag)
    if APPLY:
        verify()


def verify():
    for i in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "cinema-geo-check"}), timeout=20) as r:
                body, cc, ct = r.read().decode(), r.headers.get("cache-control"), r.headers.get("content-type")
            j = json.loads(body)
            print("GET", URL, "->", body, "| cache-control:", cc, "| content-type:", ct)
            if "city" in j and cc == "private, no-store":
                return
        except Exception as e:  # a fresh behavior can take a minute at every edge
            print("GET", URL, "failed:", e)
        time.sleep(20)
    sys.exit("verify failed: /geo did not answer {city} with private, no-store")


if __name__ == "__main__":
    main()
