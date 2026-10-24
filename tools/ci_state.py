"""tools/ci_state.py — the GitHub run's side of its state outside actions/cache (cinema-refresh.yml, 2026-10-24).

    python tools/ci_state.py backdrops-in   before run.sh: the laptop's data/backdrops.json (tools/relay.py backdrops)
                                            and any bd-*.webp it names that data/posters/ lacks (from the site bucket's
                                            posters/, where the laptop uploaded them), so the backdrops step attaches them
    python tools/ci_state.py out            after run.sh: data/latest.json -> cinema-ci/relay/latest.json.gz (what the
                                            laptop's backdrops work on); this run's Claude usage lines -> Tifo's
                                            ci/usage/ (the laptop folds them into ~/.elyoxe/usage.jsonl for the cost email)
    python tools/ci_state.py seed-if-old    data/ + out/ -> cinema-ci/seed/state.tar.gz when the seed is over 20 h old (a
                                            run with no actions/cache left starts from it)

Never fails the run on its own: each command prints what it did, and a failure is a printed line and exit 1.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REGION = "ap-south-1"
MEDIA = "elyoxe-media-574771023173"
RELAY = "cinema-ci/relay/"
SEED_KEY = "cinema-ci/seed/state.tar.gz"
SITE = "elyoxe-cinema-574771023173"
USAGE_BUCKET = "elyoxe-football-574771023173-ap-south-1"
SEED_EVERY_H = 20
SEED_SKIP = {".pytest-tmp", "backdrops_work", ".run.lock.d", "raw"}


def s3():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", region_name=REGION, config=Config(retries={"max_attempts": 6, "mode": "standard"}))


def names(entry: dict) -> set[str]:
    out = set()
    for k in ("w1280", "w640", "p"):
        if entry.get(k):
            out.add(os.path.basename(str(entry[k])))
    for kept in entry.get("kept") or []:
        if isinstance(kept, dict):
            for k in ("w1280", "w640"):
                if kept.get(k):
                    out.add(os.path.basename(str(kept[k])))
    return out


def backdrops_in() -> int:
    c = s3()
    try:
        cache = json.loads(c.get_object(Bucket=MEDIA, Key=RELAY + "backdrops.json")["Body"].read())
    except Exception as e:  # noqa: BLE001
        print(f"backdrops-in: no relay backdrops.json ({type(e).__name__}) — data/backdrops.json stays as it is")
        return 0
    posters = DATA / "posters"
    posters.mkdir(parents=True, exist_ok=True)
    want = set().union(*(names(e) for e in cache.values() if isinstance(e, dict)))
    got = 0
    for n in sorted(want):
        p = posters / n
        if p.is_file():
            continue
        try:
            c.download_file(SITE, f"posters/{n}", str(p))
            got += 1
        except Exception as e:  # noqa: BLE001 - that film's frame waits; the step skips an entry whose file is missing
            print(f"backdrops-in: {n}: {type(e).__name__}")
    (DATA / "backdrops.json").write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    # already in the bucket: posters.py --upload need not send them again
    pj = DATA / "posters.json"
    try:
        pc = json.loads(pj.read_text(encoding="utf-8"))
        if isinstance(pc.get("uploaded"), list):
            pc["uploaded"] = sorted(set(pc["uploaded"]) | want)
            pj.write_text(json.dumps(pc, ensure_ascii=False, indent=1), encoding="utf-8")
    except (OSError, ValueError):
        pass
    print(f"backdrops-in: {len(cache)} entries, {len(want)} files named, {got} fetched")
    return 0


def out() -> int:
    c = s3()
    rc = 0
    latest = DATA / "latest.json"
    if latest.is_file():
        c.put_object(Bucket=MEDIA, Key=RELAY + "latest.json.gz", Body=gzip.compress(latest.read_bytes()),
                     ContentType="application/json", ContentEncoding="gzip")
        print(f"out: latest.json up ({latest.stat().st_size // 1024} KB)")
    usage = Path(os.environ.get("ELYOXE_USAGE_LOG") or "")
    if usage.is_file() and usage.stat().st_size:
        key = f"ci/usage/cinema-{os.environ.get('GITHUB_RUN_ID', int(time.time()))}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}.jsonl"
        try:
            c.upload_file(str(usage), USAGE_BUCKET, key)
            print(f"out: {sum(1 for _ in open(usage, encoding='utf-8'))} usage line(s) -> s3://{USAGE_BUCKET}/{key}")
        except Exception as e:  # noqa: BLE001
            print(f"out: usage upload failed: {e}")
            rc = 1
    return rc


def seed_if_old(force: bool = False) -> int:
    c = s3()
    try:
        age_h = (datetime.now(timezone.utc) - c.head_object(Bucket=MEDIA, Key=SEED_KEY)["LastModified"]).total_seconds() / 3600
    except Exception:  # noqa: BLE001 - no seed yet
        age_h = 1e9
    if age_h < SEED_EVERY_H and not force:
        print(f"seed: {age_h:.1f} h old — kept")
        return 0
    tmp = Path(os.environ.get("RUNNER_TEMP") or "/tmp") / "seed.tgz"

    def skip(ti):
        parts = Path(ti.name).parts
        return None if len(parts) > 1 and parts[0] == "data" and parts[1] in SEED_SKIP else ti

    with tarfile.open(tmp, "w:gz", compresslevel=3) as t:
        for d in ("data", "out"):
            if (ROOT / d).is_dir():
                t.add(ROOT / d, arcname=d, filter=skip)
    c.upload_file(str(tmp), MEDIA, SEED_KEY)
    print(f"seed: s3://{MEDIA}/{SEED_KEY} ({tmp.stat().st_size // (1024 * 1024)} MB)")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    try:
        if cmd == "backdrops-in":
            return backdrops_in()
        if cmd == "out":
            return out()
        if cmd == "seed-if-old":
            return seed_if_old("--force" in argv)
    except Exception as e:  # noqa: BLE001
        print(f"ci_state {cmd}: {type(e).__name__}: {e}")
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
