"""tools/relay.py — the laptop's share of «سينما» since the refresh moved to GitHub Actions (2026-10-24).

The cinema-probe found three things a GitHub runner cannot read: Cine Royal (its load balancer 403s datacenter
addresses), Novo (a Cloudflare challenge) and YouTube (yt-dlp: «Sign in to confirm you're not a bot»). Everything else —
the other five chains, the merge, enrich, verdicts, the build and the deploy — runs on GitHub (cinema-refresh.yml).
This is what the laptop still does, from the clean checkout C:/Users/requi/cinema-runner, by Task Scheduler
«Elyoxe Cinema Relay» at the refresh's own 7 times:

    python tools/relay.py fetch cineroyal,novo   each chain's reader, as refresh.py calls it (days=2, today's price
                                                 samples in data/relay_price_cache.json) -> s3://…/cinema-ci/relay/<chain>.json
                                                 (a failed read uploads {"_read_at", "_error"}, so the GitHub run does
                                                 not wait for it); readers/relay.py takes it from there
    python tools/relay.py backdrops              the backdrops step (steps/backdrops.py: yt-dlp + ffmpeg) on the GitHub
                                                 run's last data (cinema-ci/relay/latest.json.gz), in this checkout's
                                                 data/; new bd-*.webp go to the site bucket's posters/ (posters.upload),
                                                 data/backdrops.json to cinema-ci/relay/backdrops.json, which the next
                                                 GitHub run attaches from (it never runs yt-dlp itself)

Nothing here builds or deploys. Exit 0 unless every requested chain failed (fetch) or the step crashed (backdrops).
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import refresh  # noqa: E402
from readers import relay  # noqa: E402
from statefile import load_state_json, write_state_json  # noqa: E402

DATA = ROOT / "data"
PRICE_CACHE = DATA / "relay_price_cache.json"
PRICE_CACHE_BAK = DATA / "relay_price_cache.prev.json"


def s3():
    import boto3
    return boto3.client("s3", region_name=relay.REGION)


def put_json(key: str, obj) -> None:
    s3().put_object(Bucket=relay.RELAY_BUCKET, Key=relay.RELAY_PREFIX + key,
                    Body=json.dumps(obj, ensure_ascii=False).encode("utf-8"), ContentType="application/json")


def fetch(chains: list[str]) -> int:
    today = refresh.now_iso()[:10]
    disk, _ = load_state_json(PRICE_CACHE, PRICE_CACHE_BAK)
    disk = disk or {}
    keep = {}
    ok_any = False
    for chain in chains:
        cache = dict((disk.get(chain) or {}).get(today) or {})
        res = refresh._run_chain(chain, 2, False, refresh.CHAIN_TIMEOUTS.get(chain, refresh.DEFAULT_TIMEOUT), price_cache=cache)
        at = refresh.now_iso()
        if res["ok"] and (res["result"] or {}).get("shows"):
            raw = res["result"]
            put_json(f"{chain}.json", {**raw, "_read_at": at})
            keep[chain] = {today: cache}
            ok_any = True
            print(f"relay: {chain} ok  cinemas={len(raw.get('cinemas') or [])}  shows={len(raw['shows'])}  {res['seconds']:.0f}s")
        else:
            why = res["error"] or "zero shows"
            put_json(f"{chain}.json", {"_read_at": at, "_error": str(why)[:500]})
            print(f"relay: {chain} FAILED  {why}  {res['seconds']:.0f}s")
            if (disk.get(chain) or {}).get(today):
                keep[chain] = {today: disk[chain][today]}
    write_state_json(PRICE_CACHE, PRICE_CACHE_BAK, keep)
    return 0 if ok_any else 1


def backdrops() -> int:
    import posters
    from steps import backdrops as bd

    body = s3().get_object(Bucket=relay.RELAY_BUCKET, Key=relay.RELAY_PREFIX + "latest.json.gz")["Body"].read()
    data = json.loads(gzip.decompress(body))
    DATA.mkdir(exist_ok=True)
    out = bd.run(data, {"offline": False, "now": refresh.now_iso(), "data_dir": str(DATA)})
    print("relay: backdrops", json.dumps({k: v for k, v in out.items() if k != "why"}), file=sys.stderr)
    for fid, why in (out.get("why") or {}).items():
        print(f"relay: backdrops {fid}: {why}", file=sys.stderr)
    posters.upload(cache_path=DATA / "posters.json", out_dir=DATA / "posters")   # new bd-*.webp before the json names them
    cache = json.loads((DATA / "backdrops.json").read_text(encoding="utf-8"))
    put_json("backdrops.json", cache)
    print(f"relay: backdrops.json up ({len(cache)} entries)")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "fetch":
        return fetch([c for c in argv[1].split(",") if c])
    if argv[:1] == ["backdrops"]:
        return backdrops()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
