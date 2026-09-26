"""Card discounts for UAE cinema tickets: load discounts.yaml, compute price-after-discount.

Shapes and the discount rules themselves live in discounts.yaml (hand-maintained; every rule
carries a source URL, a checked date and a confidence level — see the comment at its top).

This module is THE discount semantics. src/cinema.js carries a line-for-line mirror (the block
between `disc:begin` and `disc:end`), and tests/test_parity.py runs both on one matrix and
requires identical answers. Change one, change the other.

  state order: unchecked (no rule) -> none_found -> expired (valid_until < today) -> excluded -> ok
  excluded:    a hall is out when excluded_halls (alias halls_excluded) names its hall CODE or its
               hall KEY (halls.yaml key, e.g. Novo «SKY», whose code is VIP), or included_halls is set
               and names neither; a cinema is out when included_cinemas is set and does not name it
  types:       percent -> price×(1-value/100) · bogo -> price/2 (per person, with 2 tickets)
               fixed   -> the offer's own ticket price `value` (never above the real price)
  rounding:    half-up to 2 decimals (JS Math.round semantics), identical on both sides
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "discounts.yaml"

NO_CHAIN_AR = "ما لقينا خصم لهذه السينما"
NO_CARD_AR = "ما لقينا خصم لهذه البطاقة"
NO_DISCOUNT_AR = "ما لقينا خصم"
EXCLUDED_HALL_AR = "هذه القاعة مستثناة من الخصم"
EXPIRED_AR = "العرض انتهى"
BOGO_AR = "اشترِ تذكرة وخذ الثانية مجاناً — السعر للشخص"
TYPES = ("percent", "bogo", "fixed")


def load(path: str | Path | None = None) -> dict:
    """Parse discounts.yaml (or `path`) and return its {"cards": [...], "rules": {...}} dict."""
    p = Path(path) if path else _DEFAULT_PATH
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {"cards": [], "rules": {}}


def cards() -> list[dict]:
    """[{id, name_ar, name_en, kind: gov|bank}, ...] from discounts.yaml."""
    return load().get("cards", [])


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Dubai")).date().isoformat()


def _round2(x: float) -> float:
    """Half-up to 2 decimals — the same answer as JS Math.round(x * 100) / 100."""
    return math.floor(x * 100 + 0.5) / 100


def rule(rules: dict | None, chain: str, card: str) -> dict | None:
    return ((rules or {}).get((chain or "").lower()) or {}).get((card or "").lower())


def state(entry: dict | None, today: str) -> str:
    """unchecked | none_found | expired | ok — before any hall/cinema check."""
    if not entry:
        return "unchecked"
    if entry.get("status") == "none_found":
        return "none_found"
    if entry.get("valid_until") and str(entry["valid_until"]) < today:
        return "expired"
    return "ok" if entry.get("type") in TYPES else "none_found"


def covers(entry: dict, hall: str | None, hall_key: str | None = None, cinema: str | None = None) -> bool:
    """Does the rule cover this hall (by code or halls.yaml key) and this cinema?"""
    names = {h for h in (hall, hall_key) if h}
    excluded = entry.get("excluded_halls") or entry.get("halls_excluded") or []
    included = entry.get("included_halls")
    if names & set(excluded):
        return False
    if included is not None and not names & set(included):
        return False
    cinemas = entry.get("included_cinemas")
    if cinemas is not None and cinema not in cinemas:
        return False
    return True


def price_after(entry: dict, price: float) -> float:
    kind = entry.get("type")
    if kind == "bogo":
        return _round2(price / 2)
    if kind == "fixed":
        return _round2(min(price, float(entry.get("value") or 0)))
    return _round2(price * (1 - float(entry.get("value") or 0) / 100))


def compute(price: float, chain: str, hall: str | None, card: str, rules: dict | None = None, *,
            hall_key: str | None = None, cinema: str | None = None, today: str | None = None
            ) -> tuple[float | None, str, dict | None]:
    """(price after the card or None, state, rule). state: unchecked|none_found|expired|excluded|ok."""
    if rules is None:
        rules = load().get("rules", {})
    entry = rule(rules, chain, card)
    st = state(entry, today or _today())
    if st != "ok":
        return None, st, entry
    if not covers(entry, hall, hall_key, cinema):
        return None, "excluded", entry
    return price_after(entry, price), "ok", entry


def is_official(entry: dict | None) -> bool:
    return bool(entry) and entry.get("confidence") == "official"


def confirmed_cards(rules: dict | None, today: str | None = None) -> list[str]:
    """Card ids (sorted) with at least one official, not-expired, real discount at any chain —
    the only cards the site shows (phase 1: third-party and unconfirmed rules are hidden)."""
    today = today or _today()
    out = set()
    for chain_rules in (rules or {}).values():
        for card, entry in (chain_rules or {}).items():
            if is_official(entry) and state(entry, today) == "ok":
                out.add(card)
    return sorted(out)


def apply(
    price: float,
    chain: str,
    hall: str,
    card: str,
    rules: dict | None = None,
    *,
    hall_key: str | None = None,
    cinema: str | None = None,
    today: str | None = None,
) -> tuple[float | None, str]:
    """Price after `card`'s discount at `chain` for a ticket in `hall`, and an Arabic note.

    Only official rules count: a third-party or unconfirmed rule answers like no rule at all.
    Returns (None, note) when the card gives nothing at that chain/hall/cinema — no offer was ever
    found (status: none_found), the offer ended (valid_until before `today`, default today in
    Dubai), or the hall/cinema is outside the offer. `rules` lets a caller pass an already-loaded
    `load()["rules"]` to skip re-reading the file.
    """
    if rules is None:
        rules = load().get("rules", {})
    if not (rules or {}).get((chain or "").lower()):
        return None, NO_CHAIN_AR
    if not is_official(rule(rules, chain, card)):
        return None, NO_CARD_AR  # third-party / unconfirmed rules are never applied (phase 1)
    new, st, entry = compute(price, chain, hall, card, rules, hall_key=hall_key, cinema=cinema, today=today)
    if st == "unchecked":
        return None, NO_CARD_AR
    if st == "none_found":
        return None, (entry or {}).get("note_ar") or NO_DISCOUNT_AR
    if st == "expired":
        return None, EXPIRED_AR
    if st == "excluded":
        return None, entry.get("excluded_note_ar") or EXCLUDED_HALL_AR
    kind = entry.get("type")
    if kind == "bogo":
        return new, entry.get("note_ar") or BOGO_AR
    if kind == "fixed":
        return new, entry.get("note_ar") or f"التذكرة بـ{float(entry.get('value') or 0):g} درهم"
    return new, entry.get("note_ar") or f"خصم {float(entry.get('value') or 0):g}%"
