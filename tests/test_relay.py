"""readers/relay.py — the laptop's cineroyal/novo reads handed to the GitHub run (2026-10-24): a fresh read is used with
its own read time, anything else fails the chain (so normalize.merge keeps its previous shows), never an empty success."""
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

import refresh
from readers import relay

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


class FakeS3:
    def __init__(self, objs):
        self.objs, self.gets = objs, 0

    def get_object(self, Bucket, Key):
        self.gets += 1
        if Key not in self.objs:
            raise Exception("NoSuchKey")
        return {"Body": io.BytesIO(json.dumps(self.objs[Key]).encode())}


def key(chain):
    return f"{relay.RELAY_PREFIX}{chain}.json"


def read(at, **extra):
    return {"cinemas": [{"id": "c1"}], "shows": [{"cinema": "c1", "film": "f"}], "_read_at": at.isoformat(), **extra}


def test_fresh_read_is_used_with_its_own_time(monkeypatch):
    monkeypatch.setenv("CINEMA_RELAY_WAIT_S", "0")
    at = NOW - timedelta(minutes=20)
    raw = relay.fetch_relayed("cineroyal", client=FakeS3({key("cineroyal"): read(at)}), clock=lambda: NOW)
    assert raw["shows"] and raw["_relay_read_at"] == at.isoformat() and "_read_at" not in raw


def test_the_laptops_failed_read_fails_the_chain_at_once(monkeypatch):
    monkeypatch.setenv("CINEMA_RELAY_WAIT_S", "600")
    s3 = FakeS3({key("novo"): {"_read_at": NOW.isoformat(), "_error": "novo: zero shows"}})
    with pytest.raises(RuntimeError, match="zero shows"):
        relay.fetch_relayed("novo", client=s3, sleep=lambda s: pytest.fail("must not wait"), clock=lambda: NOW)


@pytest.mark.parametrize("objs", [{}, {key("cineroyal"): read(NOW - timedelta(hours=3))}])
def test_missing_or_stale_waits_then_fails(monkeypatch, objs):
    monkeypatch.setenv("CINEMA_RELAY_WAIT_S", "0")
    with pytest.raises(RuntimeError, match="previous shows kept"):
        relay.fetch_relayed("cineroyal", client=FakeS3(objs), sleep=lambda s: None, clock=lambda: NOW)


def test_an_empty_read_is_never_a_success(monkeypatch):
    monkeypatch.setenv("CINEMA_RELAY_WAIT_S", "0")
    s3 = FakeS3({key("cineroyal"): {**read(NOW), "shows": []}})
    with pytest.raises(RuntimeError, match="zero shows"):
        relay.fetch_relayed("cineroyal", client=s3, clock=lambda: NOW)


def test_refresh_reads_relayed_chains_from_the_relay_only(monkeypatch):
    monkeypatch.setenv("CINEMA_RELAY_CHAINS", "cineroyal")
    called = []
    monkeypatch.setitem(refresh.CHAIN_READERS, "cineroyal", lambda **kw: pytest.fail("the chain itself was called"))
    monkeypatch.setattr(relay, "fetch_relayed", lambda chain, **kw: called.append(chain) or {"shows": [1]})
    assert refresh._fetch_chain("cineroyal", 2, False, price_cache={}) == {"shows": [1]}
    assert called == ["cineroyal"]
    assert refresh.chain_timeout("cineroyal") == relay.wait_s() + 120.0


def test_without_the_env_nothing_changes(monkeypatch):
    monkeypatch.delenv("CINEMA_RELAY_CHAINS", raising=False)
    monkeypatch.setitem(refresh.CHAIN_READERS, "cineroyal", lambda days, cache=None: {"shows": ["direct"]})
    assert refresh._fetch_chain("cineroyal", 2, False, price_cache={}) == {"shows": ["direct"]}
    assert refresh.chain_timeout("cineroyal") == refresh.CHAIN_TIMEOUTS.get("cineroyal", refresh.DEFAULT_TIMEOUT)
