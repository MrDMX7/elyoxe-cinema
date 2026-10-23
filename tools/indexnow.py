"""tools/indexnow.py — tell the search engines that share IndexNow (Bing, Yandex, Naver, Seznam, DuckDuckGo via Bing)
which pages changed today, right after a deploy (2026-10-23: the site had 8 visitors in 30 days; the showtimes
change daily and a crawl that waits for the sitemap misses them).

    python tools/indexnow.py --out out            submit the home, every film page and every cinema page (ar + en)
    python tools/indexnow.py --out out --dry      print the list, send nothing

The key: static/<key>.txt (its content is the key), copied to the site root by build.py like the Search Console
file; IndexNow verifies it at https://cinema.elyoxe.com/<key>.txt. One POST, up to 10,000 URLs. Google does not take
IndexNow — it reads the sitemap. Never raises: a failure prints and exits 1, and deploy.sh ignores it."""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://cinema.elyoxe.com"
HOST = "cinema.elyoxe.com"
ENDPOINT = "https://api.indexnow.org/indexnow"
CITIES = ("dubai", "abu-dhabi", "sharjah", "al-ain", "ajman", "ras-al-khaimah", "fujairah", "umm-al-quwain")


def key() -> str | None:
    for f in glob.glob(os.path.join(ROOT, "static", "*.txt")):
        name = os.path.basename(f)[:-4]
        if re.fullmatch(r"[0-9a-f]{32}", name) and open(f, encoding="utf-8").read().strip() == name:
            return name
    return None


def urls(out: str) -> list[str]:
    found = [SITE + "/", SITE + "/en/"]
    for lang in ("", "/en"):
        base = os.path.join(out, "en") if lang else out
        for fid in sorted(os.listdir(os.path.join(base, "film"))) if os.path.isdir(os.path.join(base, "film")) else []:
            if os.path.exists(os.path.join(base, "film", fid, "index.html")):
                found.append(f"{SITE}{lang}/film/{fid}/")
        for city in CITIES:
            cdir = os.path.join(base, city)
            for cid in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
                if os.path.exists(os.path.join(cdir, cid, "index.html")):
                    found.append(f"{SITE}{lang}/{city}/{cid}/")
    return found[:10000]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    k = key()
    if not k:
        print("indexnow: no key in static/ (a 32-hex <key>.txt whose content is the key)")
        return 1
    lst = urls(a.out)
    if a.dry:
        print("\n".join(lst)); print(f"indexnow: {len(lst)} urls (dry)")
        return 0
    body = json.dumps({"host": HOST, "key": k, "keyLocation": f"{SITE}/{k}.txt", "urlList": lst}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "elyoxe-cinema/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"indexnow: {r.status} for {len(lst)} urls")
            return 0
    except urllib.error.HTTPError as e:
        print(f"indexnow: HTTP {e.code} {e.read()[:200]!r}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"indexnow: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
