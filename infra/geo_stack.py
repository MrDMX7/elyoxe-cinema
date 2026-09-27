"""Bring /geo under the elyoxe-cinema stack (infra/template.yaml), so a stack deploy can no longer drop it.
The function, the origin request policy and the /geo behavior already exist (made by infra/geo.py), so a plain
update would fail on the names. Two change sets, in order:
  1. IMPORT  GeoFunction (elyoxe-cinema-geo) + GeoPolicy — template.yaml with the Distribution left as the stack
     has it now (no /geo behavior in it), as an import may change nothing else
  2. UPDATE  template.yaml itself: the Distribution gains the /geo behavior — which the live distribution already
     has, identical, so the edge sees no change
  python infra/geo_stack.py             # dry run: create both change sets' previews, print them, delete them
  python infra/geo_stack.py --execute   # import, wait, update, wait (not run by the author: owner's call)
The preview of step 2 is made against today's stack, so it lists GeoFunction/GeoPolicy as Add; after step 1 they
are already the stack's and step 2 is the Distribution Modify alone. Undo after --execute: redeploy the previous
template.yaml (the two Retain resources leave the stack but stay in CloudFront; then infra/geo.py --undo).
"""
import json, os, re, subprocess, sys, tempfile, time

STACK, REGION = "elyoxe-cinema", "ap-south-1"
HERE = os.path.dirname(os.path.abspath(__file__))
EXECUTE = "--execute" in sys.argv


def aws(*a, ok_fail=False):
    r = subprocess.run(["aws", *a, "--region", REGION, "--output", "json"], capture_output=True, text=True)
    if r.returncode:
        if ok_fail:
            return None
        sys.exit(f"aws {' '.join(a[:2])} failed:\n{r.stderr}")
    return json.loads(r.stdout or "{}")


def final_template():
    return open(os.path.join(HERE, "template.yaml"), encoding="utf-8").read()


def import_template(t):
    """template.yaml without the Distribution's CacheBehaviors block: the stack's Distribution, unchanged."""
    out, n = re.subn(r"\n        CacheBehaviors:\n(?:          .*\n|            .*\n|              .*\n|                .*\n)+", "\n", t)
    assert n == 1, "CacheBehaviors block not found exactly once"
    return out


def tmp(text):
    fd, p = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return "file://" + p.replace("\\", "/"), p


def params():
    return ["ParameterKey=Domain,UsePreviousValue=true", "ParameterKey=CertificateArn,UsePreviousValue=true"]


def change_set(name, kind, body, extra=()):
    aws("cloudformation", "delete-change-set", "--stack-name", STACK, "--change-set-name", name, ok_fail=True)
    uri, p = tmp(body)
    try:
        aws("cloudformation", "create-change-set", "--stack-name", STACK, "--change-set-name", name,
            "--change-set-type", kind, "--template-body", uri, "--parameters", *params(), *extra)
    finally:
        os.remove(p)
    for _ in range(60):
        d = aws("cloudformation", "describe-change-set", "--stack-name", STACK, "--change-set-name", name)
        if d["Status"] in ("CREATE_COMPLETE", "FAILED"):
            break
        time.sleep(3)
    print(f"\n== change set {name} ({kind}): {d['Status']} {d.get('StatusReason', '')}")
    for c in d.get("Changes", []):
        rc = c["ResourceChange"]
        det = sorted({x["Target"].get("Name") or x["Target"]["Attribute"] for x in rc.get("Details", [])})
        print(f"  {rc['Action']:<7} {rc['LogicalResourceId']:<16} {rc['ResourceType']:<40} "
              f"replace={rc.get('Replacement', '-')} {det}")
    return d


def wait(what):
    r = subprocess.run(["aws", "cloudformation", "wait", what, "--region", REGION, "--stack-name", STACK])
    if r.returncode:
        sys.exit(f"wait {what} failed — see describe-stack-events")


def main():
    t = final_template()
    acct = aws("sts", "get-caller-identity")["Account"]
    pol = next(i["OriginRequestPolicy"]["Id"] for i in aws("cloudfront", "list-origin-request-policies", "--type", "custom")
               ["OriginRequestPolicyList"]["Items"] if i["OriginRequestPolicy"]["OriginRequestPolicyConfig"]["Name"] == "elyoxe-cinema-geo")
    ids = json.dumps([
        {"ResourceType": "AWS::CloudFront::Function", "LogicalResourceId": "GeoFunction",
         "ResourceIdentifier": {"FunctionARN": f"arn:aws:cloudfront::{acct}:function/elyoxe-cinema-geo"}},
        {"ResourceType": "AWS::CloudFront::OriginRequestPolicy", "LogicalResourceId": "GeoPolicy",
         "ResourceIdentifier": {"Id": pol}}])
    imp = change_set("geo-import", "IMPORT", import_template(t), ("--resources-to-import", ids))
    if not EXECUTE:
        upd = change_set("geo-update-preview", "UPDATE", t)
        for n in ("geo-import", "geo-update-preview"):
            aws("cloudformation", "delete-change-set", "--stack-name", STACK, "--change-set-name", n, ok_fail=True)
        print("\ndry run — change sets deleted, nothing executed; rerun with --execute")
        ok = imp["Status"] == "CREATE_COMPLETE" and upd["Status"] == "CREATE_COMPLETE" and all(
            c["ResourceChange"]["Action"] in ("Import", "Add", "Modify") and c["ResourceChange"].get("Replacement", "False") == "False"
            for c in imp.get("Changes", []) + upd.get("Changes", []) if c["ResourceChange"]["Action"] != "Import")
        sys.exit(0 if ok else 1)
    if imp["Status"] != "CREATE_COMPLETE":
        sys.exit("import change set failed")
    aws("cloudformation", "execute-change-set", "--stack-name", STACK, "--change-set-name", "geo-import")
    wait("stack-import-complete")
    upd = change_set("geo-update", "UPDATE", t)
    if upd["Status"] != "CREATE_COMPLETE":
        sys.exit("update change set failed")
    aws("cloudformation", "execute-change-set", "--stack-name", STACK, "--change-set-name", "geo-update")
    wait("stack-update-complete")
    print("stack now owns /geo")


if __name__ == "__main__":
    main()
