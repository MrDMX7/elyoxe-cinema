"""steps/events.py — recovers chain-labelled events (K-Fest, Immersive Dining, ...) from each
chain's own raw title text.

Fix round 1 (review: .superpowers/sdd/2026-09-27-phase2/task-2-review.md, Critical). The
raw title a chain publishes sometimes carries its own event label as a bracketed/parenthesised
suffix ("Exhuma (K-Fest)", "Revolver [K-Fest]") or a leading "<Label> - " prefix ("Immersive
Dining - IV Elements of Hoshena"). normalize.py's own clean_title()/film_fid() (imported here,
never reimplemented) strips a trailing (...)/[...] as chain "decoration" while matching films
across chains, so the suffix form is gone by the time data["films"] exists -- verified live
2026-09-27: data/raw/roxy.json's `film_title` values include exactly the K-Fest examples above,
and normalize.film_fid("Exhuma (K-Fest)") == "exhuma", the same fid data["films"] already uses.

This step reads data/raw/<chain>.json directly (written by refresh.py before merge(), so it
still has the chain's own untouched title text) instead of re-deriving anything normalize.py
already owns.

events.yaml: only labels actually seen in a chain's raw title text are recognised (a small,
curated list -- see the file's own header). A candidate extracted from a title that ISN'T in
that list -- a language tag like "[Arabic]"/"[Malayalam]", a premium-format note like
"(Infinity Vision)", or plain junk -- is silently ignored: nothing here invents an event from an
unrecognised bracket.

`normalize.film_fid(raw_title)` (the ORIGINAL raw title, not a locally re-cleaned copy) computes
each fid, so it always matches whatever normalize.merge_duplicates would produce for that exact
raw title -- this step never risks disagreeing with the real merge over what a film's fid is.

data["events"] = [{"label", "name_ar", "name_en", "kind", "fids": [...], "chains": [...],
                    "cities": [...]}], one entry per recognised label with >= 1 match, sorted by
label. Offline / no raw files / no yaml: data["events"] = [] (never invented, never stale from a
previous run since a step's data/raw/ inputs are the same ones the current run just wrote).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

import normalize

_ROOT = Path(__file__).resolve().parent.parent
_EVENTS_YAML = _ROOT / "events.yaml"

_PAREN = re.compile(r"\(([^)]*)\)\s*$")
_BRACKET = re.compile(r"\[([^\]]*)\]\s*$")
_PREFIX = re.compile(r"^(.+?)\s*-\s*.+$")


def _load_labels(path: Path = _EVENTS_YAML) -> dict:
    """{lowercased match text: {"name_ar","name_en","kind"}}."""
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    out = {}
    for row in cfg.get("labels") or []:
        m = str(row.get("match") or "").strip().lower()
        if m:
            out[m] = {"name_ar": row.get("name_ar"), "name_en": row.get("name_en"), "kind": row.get("kind")}
    return out


def _candidates(raw_title: str) -> list[str]:
    """Every trailing (...)/[...] suffix's inner text, plus a possible leading "<x> - " prefix --
    candidates only, never used to compute a fid (see module docstring)."""
    t = raw_title.strip()
    out = []
    prev = None
    while prev != t:
        prev = t
        m = _PAREN.search(t)
        if m:
            out.append(m.group(1).strip())
            t = _PAREN.sub("", t).strip()
            continue
        m = _BRACKET.search(t)
        if m:
            out.append(m.group(1).strip())
            t = _BRACKET.sub("", t).strip()
            continue
    m = _PREFIX.match(t)
    if m:
        out.append(m.group(1).strip())
    return out


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run(data: dict, ctx: dict) -> dict | None:
    labels_cfg = _load_labels()
    raw_dir = Path(ctx.get("data_dir") or "data") / "raw"
    events: dict[str, dict] = {}

    if labels_cfg and raw_dir.is_dir():
        for raw_path in sorted(raw_dir.glob("*.json")):
            if raw_path.name.startswith("."):
                continue  # data/raw/.run.json -- the resume marker, not a chain's fetch
            raw = _load_json(raw_path)
            if not isinstance(raw, dict):
                continue
            chain = raw_path.stem
            city_of = {c.get("id"): c.get("city") for c in (raw.get("cinemas") or []) if c.get("id")}
            for s in raw.get("shows") or []:
                title = s.get("film_title")
                if not title:
                    continue
                for cand in _candidates(title):
                    cfg = labels_cfg.get(cand.strip().lower())
                    if not cfg:
                        continue
                    fid = normalize.film_fid(title)
                    key = cand.strip().lower()
                    rec = events.setdefault(key, {**cfg, "fids": set(), "chains": set(), "cities": set()})
                    rec["fids"].add(fid)
                    rec["chains"].add(chain)
                    city = city_of.get(s.get("cinema"))
                    if city:
                        rec["cities"].add(city)

    data["events"] = [
        {"label": key, "name_ar": r["name_ar"], "name_en": r["name_en"], "kind": r["kind"],
         "fids": sorted(r["fids"]), "chains": sorted(r["chains"]), "cities": sorted(r["cities"])}
        for key, r in sorted(events.items())
    ]
    return {"labels": len(data["events"])}
