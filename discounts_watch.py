"""discounts_watch.py — the new-offer detector (roadmap 195, 2026-10-17): did any page discounts.yaml cites change?

discounts.yaml is maintained by hand with a `source` URL, a `checked` date and a confidence per rule; every
entry was last read on 2026-09-25/26. Nothing told the owner when Fazaa, Esaad, a bank or a chain changed
its page — a dead or changed offer stays on the site until someone happens to look. This reads every unique
source URL, keeps only the lines that talk about cinema offers (so a rotated banner or a date in the footer
is not "a change"), hashes them, and compares with the last run (data/discount_sources.json). Output: the
sources that changed or stopped answering, in one Arabic line for run.sh's note(); the baseline then moves,
so a change is reported once. `checked` dates in the yaml are the owner's: never touched here.

    python discounts_watch.py            read, compare, print the report line (empty = nothing changed), update the state
    python discounts_watch.py --dry      read and compare only (state untouched)
    python discounts_watch.py --json     the per-source result as JSON

Limit (seen on the first live read, 2026-10-17): reelcinemas.com/offers, fazaa.ae's offer pages and Novo's
promotion pages are script-rendered shells — their offer text never arrives over plain HTTP, so for those only
an outage is visible (`thin: true` in the state). A browser read (Playwright) would see them; not worth a
browser inside the 3-hourly run yet.

Fetching: curl_cffi with a browser fingerprint (VOX and Roxy sit behind Akamai, readers/vox.py's lesson) with a
polite gap; a request error is a status, never an exception. Nothing here touches the site build.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
YAML = ROOT / "discounts.yaml"
STATE = ROOT / "data" / "discount_sources.json"
GAP = 1.5
THIN_CHARS = 80   # under this much offer text the page is a script shell: its real words never reach us without a browser
UA_IMPERSONATE = "chrome120"
KEYWORDS = re.compile(r"(cinema|cinemas|movie|film|ticket|سينما|تذكر|فيلم|أفلام|فزعة|إسعاد|fazaa|esaad|homat|حماة|"
                      r"offer|discount|promo|عرض|خصم|%|aed|درهم|vox|star|novo|reel|roxy|royal)", re.I)
_TAG = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t ]+")


def sources(path: Path = YAML) -> dict[str, list[str]]:
    """{url: ["chain/card", …]} for every rule that names a source."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, list[str]] = {}
    for chain, cards in (doc.get("rules") or {}).items():
        for card, rule in (cards or {}).items():
            url = (rule or {}).get("source")
            if url:
                out.setdefault(url, []).append(f"{chain}/{card}")
    return out


def relevant_text(html: str) -> str:
    """The page's own words that talk about cinema offers, one line each, whitespace folded."""
    text = _TAG.sub(" ", html)
    text = _TAGS.sub("\n", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    lines = []
    for raw in text.splitlines():
        line = _WS.sub(" ", raw).strip()
        if len(line) < 4 or not KEYWORDS.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def digest(html: str) -> str:
    return hashlib.sha1(relevant_text(html).encode("utf-8")).hexdigest()


def fetch(url: str) -> tuple[int | None, str]:
    """(status, body) — a transport error is (None, "")."""
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, impersonate=UA_IMPERSONATE, timeout=40, allow_redirects=True)
        return r.status_code, r.text or ""
    except Exception as e:  # noqa: BLE001 - a dead page is a result here, not a crash
        return None, f"ERR {e.__class__.__name__}"


def load_state(path: Path = STATE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def compare(prev: dict, now: dict) -> dict:
    """prev/now: {url: {"status", "hash"}} → {url: "new" | "same" | "changed" | "down" | "back"}."""
    out = {}
    for url, cur in now.items():
        old = prev.get(url)
        ok = cur.get("status") == 200
        if old is None:
            out[url] = "new" if ok else "down"
        elif not ok:
            out[url] = "down" if old.get("status") == 200 else "same"
        elif old.get("status") != 200:
            out[url] = "back"
        elif old.get("hash") != cur.get("hash"):
            out[url] = "changed"
        else:
            out[url] = "same"
    return out


def report_line(verdicts: dict, who: dict[str, list[str]]) -> str:
    """One Arabic line naming what moved, "" when nothing did."""
    parts = []
    for url, v in verdicts.items():
        if v in ("changed", "down"):
            host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
            parts.append(f"{'تغيّرت' if v == 'changed' else 'ما ترد'} صفحة {host} ({'، '.join(who.get(url, []))})")
    if not parts:
        return ""
    return "مصادر الخصومات تحتاج فحص: " + " · ".join(parts) + " — راجع discounts.yaml وحدّث checked."


def run(dry: bool = False, as_json: bool = False, fetcher=fetch, state_path: Path = STATE, yaml_path: Path = YAML) -> str:
    who = sources(yaml_path)
    prev = load_state(state_path)
    now: dict[str, dict] = {}
    today = dt.date.today().isoformat()
    for i, url in enumerate(who):
        if i:
            time.sleep(GAP)
        status, body = fetcher(url)
        rec = {"status": status, "hash": digest(body) if status == 200 else None, "at": today}
        if status == 200 and len(relevant_text(body)) < THIN_CHARS:
            rec["thin"] = True   # a script-rendered shell (Reel, Fazaa, Novo's promotion pages): only an outage is visible here
        now[url] = rec
    verdicts = compare(prev, now)
    if as_json:
        print(json.dumps({u: {**now[u], "verdict": verdicts[u], "rules": who[u]} for u in now}, ensure_ascii=False, indent=2))
    line = report_line(verdicts, who)
    if not dry:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(now, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return line


def main(argv: list[str]) -> int:
    line = run(dry="--dry" in argv, as_json="--json" in argv)
    if line and "--json" not in argv:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
