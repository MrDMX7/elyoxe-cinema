"""Step: today's prices into the price history (price_history.py), kept on the runner and in the bucket.

  fetch s3://elyoxe-cinema-574771023173/state/price_history.jsonl (every run), union it with the local file and
  this run's snapshot (per date the better read wins), write locally, upload when the bucket lacks anything

--offline (fixtures) writes nothing: fixture prices must never enter the real history. A failed download skips
the upload (the step reports the failure; today waits in the local file for the next run's union). An absent
object with local history is flagged in health and re-uploaded; deploy.sh never deletes state/. The bucket is used for the runner's own data/ only (use_bucket)."""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
import price_history as ph  # noqa: E402

URI = f"s3://{ph.BUCKET}/{ph.KEY}"
REGION = "ap-south-1"


def _aws(*args, timeout=60):
    aws = shutil.which("aws")
    if not aws: return 127, "aws cli not found"
    r = subprocess.run([aws, *args, "--region", REGION], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stderr or r.stdout or "").strip()


def s3_get(path):
    """'ok' | 'absent' (the bucket has no history yet) | 'failed: …'."""
    rc, msg = _aws("s3api", "head-object", "--bucket", ph.BUCKET, "--key", ph.KEY)
    if rc != 0:
        return "absent" if ("404" in msg or "Not Found" in msg or "NoSuchKey" in msg) else f"failed: {msg[-200:]}"
    rc, msg = _aws("s3", "cp", URI, path, "--only-show-errors", timeout=120)
    return "ok" if rc == 0 else f"failed: {msg[-200:]}"


def s3_put(path):
    rc, msg = _aws("s3", "cp", path, URI, "--only-show-errors", "--content-type", "application/x-ndjson",
                   "--cache-control", "no-store", timeout=120)
    return "ok" if rc == 0 else f"failed: {msg[-200:]}"


def _halls():
    try:
        from site_kit import Halls
        return Halls(os.path.join(ROOT, "halls.yaml"))
    except Exception:  # noqa: BLE001 - without halls.yaml the reader's hall code is the key
        return None


def use_bucket(path):
    """CINEMA_HISTORY_S3=1 always, =0 never; unset: only for the runner's own data/ (a sandboxed data_dir,
    as in the test suite, never reaches the bucket)."""
    v = os.environ.get("CINEMA_HISTORY_S3", "")
    if v in ("0", "1"): return v == "1"
    return os.path.normcase(os.path.abspath(os.path.dirname(path))) == os.path.normcase(os.path.join(ROOT, "data"))


def run(data, ctx):
    """Every non-offline run: fetch the bucket copy, union it with the local file and this run's snapshot (per
    date the better read wins, price_history.merge), write locally, upload when the bucket lacks anything.
    So a lost runner file comes back from the bucket and a stale local file can never shrink the bucket's."""
    if ctx.get("offline"):
        return {"skipped": "offline"}
    path = os.path.join(ctx.get("data_dir") or os.path.join(ROOT, "data"), "price_history.jsonl")
    bucket = use_bucket(path)
    local = ph.load(path)
    remote, got = {}, None
    if bucket:
        tmp = f"{path}.bucket.{os.getpid()}"
        try:
            got = s3_get(tmp)
            if got == "ok": remote = ph.load(tmp)
        finally:
            if os.path.exists(tmp): os.remove(tmp)
    merged, _ = ph.merge(local, remote)
    merged, changed = ph.merge(merged, ph.snapshot(data, _halls()))
    out = {"days": len(ph.days(merged)), "changed": changed}
    if bucket: out["bucket"] = got
    if merged != local:
        ph.dump(merged, path)
    if not bucket:
        return out
    if got.startswith("failed"):   # today stays in the local file; the next run merges it with the bucket's
        print(f"history: bucket download {got} — upload skipped this run", file=sys.stderr)
        raise RuntimeError(f"price history download {got}: kept locally, upload skipped")
    if got == "absent":
        if local: out["warning"] = f"bucket had no history but the local file had {len(local)} days — re-uploaded"
        else: out["new"] = True
    if merged != remote:
        out["pushed"] = s3_put(path)
        if out["pushed"] != "ok":
            raise RuntimeError(f"price history upload {out['pushed']}")
    return out
