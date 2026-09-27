"""Every build in the suite reads no price history unless its test gives one: the runner's own
data/price_history.jsonl must never make a page test depend on the machine (pages/insights.py, questions.py)."""
import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_real_price_history(tmp_path_factory):
    if os.environ.get("CINEMA_PRICE_HISTORY"):
        yield; return
    os.environ["CINEMA_PRICE_HISTORY"] = str(tmp_path_factory.mktemp("history") / "none.jsonl")
    try:
        yield
    finally:
        os.environ.pop("CINEMA_PRICE_HISTORY", None)
