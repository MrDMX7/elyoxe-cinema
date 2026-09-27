"""Step: today's prices into the price history (price_history.py), kept on the runner and in the bucket.

  local data/price_history.jsonl missing -> fetch s3://elyoxe-cinema-574771023173/state/price_history.jsonl
  snapshot this run's data, merge (a date is replaced only by a fuller read of it), write, upload when changed

--offline (fixtures) writes nothing: fixture prices must never enter the real history. A failed download starts
a new file only when the bucket has none; any other download failure leaves the history alone this run (a
fresh local file would later overwrite the bucket's longer one). The bucket is used for the runner's own data/ only (use_bucket)."""
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
    if ctx.get("offline"):
        return {"skipped": "offline"}
    path = os.path.join(ctx.get("data_dir") or os.path.join(ROOT, "data"), "price_history.jsonl")
    bucket = use_bucket(path)
    pulled = None
    if bucket and not os.path.exists(path):
        pulled = s3_get(path)
        if pulled.startswith("failed"):
            raise RuntimeError(f"price history download {pulled} — not writing a fresh file over the bucket's")
    lines = ph.load(path)
    merged, changed = ph.merge(lines, ph.snapshot(data, _halls()))
    out = {"days": len(ph.days(merged)), "changed": changed, "pulled": pulled}
    if changed:
        ph.dump(merged, path)
        if bucket:
            out["pushed"] = s3_put(path)
            if out["pushed"] != "ok":
                raise RuntimeError(f"price history upload {out['pushed']}")
    return out
