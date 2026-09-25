"""Tests for discounts.load()/apply()/cards() — run with `python -m pytest` from the repo root
(saas/cinema) so discounts.py is importable without a conftest.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import discounts  # noqa: E402

DATA = discounts.load()
RULES = DATA["rules"]


def test_star_fazaa_20_percent_on_52_50():
    price, note = discounts.apply(52.50, "star", "Standard", "fazaa", RULES)
    assert price == 42.0
    assert isinstance(note, str) and note


def test_vox_fazaa_gives_nothing():
    price, note = discounts.apply(46.0, "vox", "Standard", "fazaa", RULES)
    assert price is None
    assert isinstance(note, str) and note


def test_bogo_bank_halves_the_price():
    # VOX + Emirates NBD is BOGO per discounts.yaml.
    price, note = discounts.apply(46.0, "vox", "Standard", "enbd", RULES)
    assert price == 23.0
    assert "مجاناً" in note


def test_excluded_hall_gives_nothing():
    # Novo + Esaad excludes IMAX.
    price, note = discounts.apply(52.0, "novo", "IMAX", "esaad", RULES)
    assert price is None
    assert isinstance(note, str) and note


def test_included_halls_restricts_to_that_hall():
    # Reel + Fazaa is box-office only on SUITES.
    price_in, _ = discounts.apply(100.0, "reel", "SUITES", "fazaa", RULES)
    price_out, note_out = discounts.apply(50.0, "reel", "Standard", "fazaa", RULES)
    assert price_in == 75.0
    assert price_out is None
    assert isinstance(note_out, str) and note_out


def test_unknown_chain_or_card_gives_nothing():
    price, note = discounts.apply(50.0, "no-such-chain", "Standard", "fazaa", RULES)
    assert price is None and note
    price, note = discounts.apply(50.0, "vox", "Standard", "no-such-card", RULES)
    assert price is None and note


def test_every_rule_has_source_checked_confidence():
    for chain, chain_rules in RULES.items():
        for card, entry in chain_rules.items():
            assert "source" in entry, f"{chain}.{card} missing source"
            assert entry["source"].startswith("http"), f"{chain}.{card} source is not a URL"
            assert "checked" in entry, f"{chain}.{card} missing checked"
            assert entry.get("confidence") in ("official", "third-party", "unconfirmed"), (
                f"{chain}.{card} has no valid confidence"
            )


def test_cards_lists_the_three_government_cards_plus_banks():
    ids = {c["id"] for c in discounts.cards()}
    kinds = {c["id"]: c["kind"] for c in discounts.cards()}
    assert {"fazaa", "esaad", "homat"} <= ids
    assert kinds["fazaa"] == "gov"
    assert any(k == "bank" for k in kinds.values())
