"""ci_probe.py — can a GitHub runner read the seven chains (and YouTube) the way refresh.py does? (2026-10-24)

Run by .github/workflows/cinema-probe.yml (workflow_dispatch only). Nothing is deployed, nothing is written outside
$PROBE_OUT, and no request differs from what the readers already send from the laptop: each chain's own reader is
called exactly as refresh.py calls it (fetch(days=1, cache=<today's price slice>)), so its price path is exercised
only for the cinema x hall x date keys the laptop has NOT sampled today, plus at most DROP keys per chain removed from
that slice on purpose so the seat/price endpoint is touched at least once. No bot check is worked around here: a
challenge page is recorded as «blocked» and that chain stays on the laptop.

    python tools/ci_probe.py --cache price_cache.json --out probe/     (exit 0 always; the verdicts are the output)

Per chain: a preflight GET of its landing endpoint with the same HTTP client its reader uses (status, server, and
whether the body is a challenge page), then the reader itself. Verdict: works (shows, and prices where it samples),
partial (shows but the price/seat path failed or was challenged), blocked (no shows: a status, a challenge, a
timeout). YouTube: `yt-dlp --simulate` and one real download of the backdrops format for a showing trailer.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import refresh  # noqa: E402  (the readers, _run_chain, chain timeouts)

DROP = 2
# challenge markers: Cloudflare, Akamai Bot Manager, PerimeterX, Imperva, DataDome, generic captcha
CHALLENGE = re.compile(r"just a moment|attention required|cf-chl|challenge-platform|verify you are human|"
                       r"access denied|sec-if-cpt|_abck|px-captcha|incapsula|datadome|captcha|are you a robot",
                       re.I)
PREFLIGHT = {
    "vox": ("cffi", "https://uae.voxcinemas.com/cinemas"),
    "roxy": ("cffi", "https://www.theroxycinemas.com/"),
    "reel": ("cffi", "https://apiuae.reelcinemas.com/webapi/api"),
    "star": ("requests", "https://web-api.starcinemas.ae/api/v3/external/cinemas"),
    "novo": ("requests", "https://uae-api.novocinemas.com/api/home"),
    "cineroyal": ("requests", "https://cineroyal.ae/home/nowShowing"),
    "cinemacity": ("requests", "https://www.cinemacity.ae/our-locations/"),
}


def preflight(chain: str) -> dict:
    kind, url = PREFLIGHT[chain]
    t0 = time.monotonic()
    try:
        if kind == "cffi":
            from curl_cffi import requests as cr
            r = cr.get(url, impersonate="chrome", timeout=30)
        else:
            import requests
            from readers.common import UA
            r = requests.get(url, timeout=30, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,ar;q=0.8"})
        body = r.text[:20000] if isinstance(r.text, str) else ""
        title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        hit = CHALLENGE.search(body)
        return {"url": url, "status": r.status_code, "server": r.headers.get("server"),
                "cf_mitigated": r.headers.get("cf-mitigated"), "title": (title.group(1).strip()[:80] if title else None),
                "challenge": hit.group(0) if hit else None, "bytes": len(r.content or b""),
                "sec": round(time.monotonic() - t0, 1)}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "error": f"{type(e).__name__}: {e}"[:300], "sec": round(time.monotonic() - t0, 1)}


def probe_chain(chain: str, today_cache: dict, out: Path) -> dict:
    pre = preflight(chain)
    cache = dict(today_cache)
    dropped = sorted(cache)[:DROP]
    for k in dropped:
        cache.pop(k, None)
    res = refresh._run_chain(chain, 1, False, refresh.chain_timeout(chain), price_cache=cache)
    raw = res.get("result") or {}
    shows = raw.get("shows") or []
    ph = raw.get("price_health") or {}
    priced_shows = sum(1 for s in shows if s.get("prices"))
    row = {"chain": chain, "preflight": pre, "ok": res["ok"], "error": res["error"], "sec": round(res["seconds"], 1),
           "cinemas": len(raw.get("cinemas") or []), "shows": len(shows), "priced_shows": priced_shows,
           "price_health": ph, "cache_keys_given": len(cache), "cache_keys_dropped": len(dropped)}
    err = f"{res.get('error') or ''} {ph.get('error') or ''} {pre.get('challenge') or ''}"
    if not res["ok"] or not shows:
        row["verdict"] = "blocked"
    elif CHALLENGE.search(err) or (ph.get("attempted") and not ph.get("priced")):
        row["verdict"] = "partial"
    else:
        row["verdict"] = "works"
    (out / f"{chain}.json").write_text(json.dumps({**row, "sample_show": shows[:2]}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return row


def probe_youtube(trailer: str) -> dict:
    from steps import backdrops as bd
    url = f"https://www.youtube.com/watch?v={trailer}"
    out = {"trailer": trailer, "yt_dlp": shutil.which("yt-dlp")}
    r = subprocess.run(["yt-dlp", "--simulate", "--no-warnings", "-f", bd.FORMAT, "--print", "%(format_id)s %(height)s",
                        url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    out["simulate"] = {"rc": r.returncode, "out": r.stdout.strip()[-200:], "err": r.stderr.strip()[-400:]}
    with tempfile.TemporaryDirectory() as d:
        t0 = time.monotonic()
        video, why = bd._yt_dlp_download(trailer, Path(d), "probe")
        out["download"] = {"ok": video is not None, "why": why, "sec": round(time.monotonic() - t0, 1),
                           "mb": round(video.stat().st_size / 1e6, 1) if video else None}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", help="the laptop's data/price_cache.json (today's slice is used)")
    ap.add_argument("--out", default="probe")
    ap.add_argument("--chains", default=",".join(refresh.ALL_CHAINS))
    ap.add_argument("--trailer", default="")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    today = refresh.now_iso()[:10]
    pc = {}
    if a.cache and Path(a.cache).is_file():
        pc = json.loads(Path(a.cache).read_text(encoding="utf-8"))
    rows = []
    for chain in a.chains.split(","):
        row = probe_chain(chain, (pc.get(chain) or {}).get(today) or {}, out)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    yt = probe_youtube(a.trailer) if a.trailer else None
    if yt:
        print(json.dumps(yt, ensure_ascii=False), flush=True)
    summary = ["| chain | verdict | preflight | cinemas | shows | priced shows | price calls (ok/tried, cached) | sec | error |",
               "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        p = r["preflight"]
        pf = p.get("error") or f"{p.get('status')} {p.get('server') or ''}{' CHALLENGE:' + p['challenge'] if p.get('challenge') else ''}"
        ph = r["price_health"]
        summary.append(f"| {r['chain']} | **{r['verdict']}** | {pf} | {r['cinemas']} | {r['shows']} | {r['priced_shows']} | "
                       f"{ph.get('priced', '-')}/{ph.get('attempted', '-')}, {ph.get('cached', '-')} | {r['sec']} | "
                       f"{(r['error'] or ph.get('error') or '')[:120]} |")
    if yt:
        summary.append("")
        summary.append(f"YouTube {yt['trailer']}: simulate rc={yt['simulate']['rc']} {yt['simulate']['out'] or yt['simulate']['err'][-160:]}"
                       f" · download ok={yt['download']['ok']} {yt['download']['mb']} MB in {yt['download']['sec']} s"
                       f"{' · ' + yt['download']['why'] if yt['download']['why'] else ''}")
    text = "\n".join(summary)
    (out / "summary.md").write_text(text + "\n", encoding="utf-8")
    (out / "probe.json").write_text(json.dumps({"rows": rows, "youtube": yt}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
