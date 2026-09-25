"""Card discounts for UAE cinema tickets: load discounts.yaml, compute price-after-discount.

Shapes and the discount rules themselves live in discounts.yaml (hand-maintained; every rule
carries a source URL, a checked date and a confidence level — see the comment at its top).
"""
from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "discounts.yaml"

NO_CHAIN_AR = "ما لقينا خصم لهذه السينما"
NO_CARD_AR = "ما لقينا خصم لهذه البطاقة"
NO_DISCOUNT_AR = "ما لقينا خصم"
EXCLUDED_HALL_AR = "هذه القاعة مستثناة من الخصم"
BOGO_AR = "اشترِ تذكرة وخذ الثانية مجاناً — السعر للشخص"


def load(path: str | Path | None = None) -> dict:
    """Parse discounts.yaml (or `path`) and return its {"cards": [...], "rules": {...}} dict."""
    p = Path(path) if path else _DEFAULT_PATH
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {"cards": [], "rules": {}}


def cards() -> list[dict]:
    """[{id, name_ar, name_en, kind: gov|bank}, ...] from discounts.yaml."""
    return load().get("cards", [])


def apply(
    price: float,
    chain: str,
    hall: str,
    card: str,
    rules: dict | None = None,
) -> tuple[float | None, str]:
    """Price after `card`'s discount at `chain` for a ticket in `hall`, and an Arabic note.

    Returns (None, note) when the card gives nothing at that chain/hall — either because no
    offer was ever found (status: none_found in the yaml) or because the hall is excluded.
    `rules` lets a caller pass an already-loaded `load()["rules"]` to skip re-reading the file.
    """
    if rules is None:
        rules = load().get("rules", {})

    chain_rules = rules.get((chain or "").lower())
    if not chain_rules:
        return None, NO_CHAIN_AR

    entry = chain_rules.get((card or "").lower())
    if not entry:
        return None, NO_CARD_AR

    if entry.get("status") == "none_found":
        return None, entry.get("note_ar") or NO_DISCOUNT_AR

    excluded_halls = entry.get("excluded_halls") or []
    included_halls = entry.get("included_halls")
    if hall in excluded_halls or (included_halls is not None and hall not in included_halls):
        return None, entry.get("excluded_note_ar") or EXCLUDED_HALL_AR

    kind = entry.get("type")
    if kind == "bogo":
        return round(price / 2, 2), entry.get("note_ar") or BOGO_AR

    if kind == "percent":
        value = entry.get("value", 0)
        new_price = round(price * (1 - value / 100), 2)
        note = entry.get("note_ar") or f"خصم {value:g}%"
        return new_price, note

    return None, NO_DISCOUNT_AR
