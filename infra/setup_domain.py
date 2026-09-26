"""Idempotent: stand up https://cinema.elyoxe.com. Safe to rerun; each step skips what exists.
  1. ACM certificate for the domain in us-east-1, DNS-validated (validation CNAME UPSERTed into
     Route53), waits until ISSUED.
  2. CloudFormation stack elyoxe-cinema (ap-south-1) from infra/template.yaml: private bucket,
     OAC, rewrite function, distribution (alias + cert).
  3. Route53 A + AAAA alias records → the distribution (UPSERT).
  Prints the distribution id last.
    python infra/setup_domain.py
Undo (in this order): delete the two alias records, empty the bucket, delete the stack
(`aws cloudformation delete-stack --region ap-south-1 --stack-name elyoxe-cinema`), then delete the
certificate (`aws acm delete-certificate --region us-east-1 --certificate-arn …`) and its CNAME.
"""
import json, os, subprocess, sys, tempfile, time

DOMAIN = "cinema.elyoxe.com"
ZONE = "Z092471334IO8THU6C3A9"
STACK, REGION = "elyoxe-cinema", "ap-south-1"
CF_ZONE = "Z2FDTNDATAQYW2"  # fixed hosted zone id of every CloudFront distribution
HERE = os.path.dirname(os.path.abspath(__file__))


def run(*a):
    r = subprocess.run(["aws", *a], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"aws {' '.join(a[:3])} failed:\n{r.stderr}")
    return r.stdout


def aws(*a):
    return json.loads(run(*a, "--output", "json") or "{}")


def change_records(changes, comment):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"Comment": comment, "Changes": changes}, f)
    try:
        r = aws("route53", "change-resource-record-sets", "--hosted-zone-id", ZONE,
                "--change-batch", "file://" + path.replace("\\", "/"))
    finally:
        os.remove(path)
    return r["ChangeInfo"]["Id"]


def certificate():
    certs = aws("acm", "list-certificates", "--region", "us-east-1",
                "--certificate-statuses", "ISSUED", "PENDING_VALIDATION")["CertificateSummaryList"]
    arn = next((c["CertificateArn"] for c in certs if c["DomainName"] == DOMAIN), None)
    if arn is None:
        arn = aws("acm", "request-certificate", "--region", "us-east-1", "--domain-name", DOMAIN,
                  "--validation-method", "DNS", "--idempotency-token", "elyoxecinema")["CertificateArn"]
        print("cert requested:", arn)
    for _ in range(30):  # the validation record appears a few seconds after the request
        c = aws("acm", "describe-certificate", "--region", "us-east-1", "--certificate-arn", arn)["Certificate"]
        if c["Status"] == "ISSUED":
            print("cert ISSUED:", arn); return arn
        opts = c.get("DomainValidationOptions") or []
        if opts and "ResourceRecord" in opts[0]:
            break
        time.sleep(4)
    else:
        sys.exit("no validation record on the certificate after 2 min")
    rr = opts[0]["ResourceRecord"]
    change_records([{"Action": "UPSERT", "ResourceRecordSet": {
        "Name": rr["Name"], "Type": rr["Type"], "TTL": 300, "ResourceRecords": [{"Value": rr["Value"]}]}}],
        f"ACM validation {DOMAIN}")
    print("validation CNAME upserted:", rr["Name"], "->", rr["Value"])
    print("waiting for ISSUED …", flush=True)
    run("acm", "wait", "certificate-validated", "--region", "us-east-1", "--certificate-arn", arn)
    print("cert ISSUED:", arn)
    return arn


def stack(cert):
    print("deploying stack", STACK, "(a new distribution takes a few minutes) …", flush=True)
    r = subprocess.run(["aws", "cloudformation", "deploy", "--region", REGION, "--stack-name", STACK,
                        "--template-file", os.path.join(HERE, "template.yaml").replace("\\", "/"),
                        "--parameter-overrides", f"CertificateArn={cert}", f"Domain={DOMAIN}",
                        "--no-fail-on-empty-changeset"], text=True)
    if r.returncode:
        sys.exit(f"stack deploy failed ({r.returncode}) — see `aws cloudformation describe-stack-events "
                 f"--region {REGION} --stack-name {STACK}`")
    out = aws("cloudformation", "describe-stacks", "--region", REGION, "--stack-name", STACK)["Stacks"][0]["Outputs"]
    return {o["OutputKey"]: o["OutputValue"] for o in out}


def alias(dist_domain):
    target = {"HostedZoneId": CF_ZONE, "DNSName": dist_domain, "EvaluateTargetHealth": False}
    cid = change_records([{"Action": "UPSERT", "ResourceRecordSet": {"Name": DOMAIN, "Type": t, "AliasTarget": target}}
                          for t in ("A", "AAAA")], f"{DOMAIN} -> CloudFront")
    print("A + AAAA alias upserted ->", dist_domain, cid)


if __name__ == "__main__":
    cert = certificate()
    out = stack(cert)
    alias(out["DistributionDomain"])
    print("bucket:", out["Bucket"])
    print("distribution:", out["DistributionId"])
