"""Suite-wide guards.

1. Every build in the suite reads no price history unless its test gives one: the runner's own
   data/price_history.jsonl must never make a page test depend on the machine (pages/insights.py, questions.py).
2. No test ever reaches the network. Python sockets (requests, urllib), curl_cffi (libcurl, below Python's
   sockets) and the aws CLI (steps/history.py) are all refused. A refused call raises NetworkBlocked — and,
   because a step or reader may swallow it with `except Exception`, the test that made it fails anyway at
   teardown, naming the host. Loopback stays open (none of the code under test serves anything; kept so a
   future local fixture server is not refused).

   The one deliberate exception: the `live_network` fixture (round 3 QA, OMDb real-call test) opts a single
   test IN to real sockets for its duration only — every other test in the suite is unaffected.
"""
import os
import socket
import subprocess

import pytest

# The GitHub refresh (cinema-refresh.yml) sets these for its run, and run.sh runs this suite inside that same
# environment when test.yml has not passed the commit yet: the tests describe the code's defaults, never the runner's
# (CINEMA_BACKDROPS_MAX=0 turned a backdrops test red on 2026-10-24). Dropped before any test module imports.
for _k in ("CINEMA_RELAY_CHAINS", "CINEMA_RELAY_WAIT_S", "CINEMA_RELAY_FRESH_MIN", "CINEMA_BACKDROPS_MAX",
           "CINEMA_BACKDROPS_BUDGET_S", "CINEMA_CLAUDE_VIA", "ELYOXE_USAGE_LOG"):
    os.environ.pop(_k, None)

LOOPBACK = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
ATTEMPTS: list[str] = []
_LIVE_NETWORK = False   # flipped true only inside the `live_network` fixture, for that one test


class NetworkBlocked(RuntimeError):
    pass


def _refuse(what):
    if _LIVE_NETWORK:
        return None
    ATTEMPTS.append(what)
    raise NetworkBlocked(f"network call in a test: {what}")


def _host(address):
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


@pytest.fixture(autouse=True, scope="session")
def _no_network():
    mp = pytest.MonkeyPatch()
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_gai = socket.getaddrinfo

    def connect(self, address):
        if _LIVE_NETWORK or self.family == getattr(socket, "AF_UNIX", None) or _host(address) in LOOPBACK:
            return real_connect(self, address)
        _refuse(f"socket {_host(address)}")

    def connect_ex(self, address):
        if _LIVE_NETWORK or self.family == getattr(socket, "AF_UNIX", None) or _host(address) in LOOPBACK:
            return real_connect_ex(self, address)
        _refuse(f"socket {_host(address)}")

    def getaddrinfo(host, *a, **kw):
        if _LIVE_NETWORK or host is None or str(host) in LOOPBACK:
            return real_gai(host, *a, **kw)
        _refuse(f"dns {host}")

    mp.setattr(socket.socket, "connect", connect)
    mp.setattr(socket.socket, "connect_ex", connect_ex)
    mp.setattr(socket, "getaddrinfo", getaddrinfo)
    try:
        from curl_cffi import curl as _curl
        mp.setattr(_curl.Curl, "perform", lambda self, *a, **kw: _refuse("curl_cffi perform"))
    except ImportError:
        pass

    real_run, real_popen = subprocess.run, subprocess.Popen

    def _is_aws(args):
        first = args[0] if isinstance(args, (list, tuple)) and args else args
        return os.path.basename(str(first)).lower() in ("aws", "aws.exe", "aws.cmd")

    class Popen(real_popen):
        def __init__(self, args, *a, **kw):
            if _is_aws(args):
                _refuse(f"aws cli {' '.join(map(str, args[1:3]))}")
            super().__init__(args, *a, **kw)

    mp.setattr(subprocess, "Popen", Popen)
    os.environ.setdefault("CINEMA_HISTORY_S3", "0")
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(autouse=True)
def _network_attempts_fail_the_test(_no_network):
    before = len(ATTEMPTS)
    yield
    new = ATTEMPTS[before:]
    if new:
        pytest.fail(f"this test tried the network {len(new)}x (refused): {sorted(set(new))[:8]}", pytrace=False)


@pytest.fixture
def live_network(_no_network):
    """Opt a single test IN to real sockets (round 3 QA: the OMDb real-call test). Every other test keeps
    the network refused — this only flips the module-level switch for the duration of the test that asks
    for it, then flips it back in `finally` even if the test raises."""
    global _LIVE_NETWORK
    _LIVE_NETWORK = True
    try:
        yield
    finally:
        _LIVE_NETWORK = False


@pytest.fixture(autouse=True, scope="session")
def _no_real_price_history(tmp_path_factory):
    if os.environ.get("CINEMA_PRICE_HISTORY"):
        yield; return
    os.environ["CINEMA_PRICE_HISTORY"] = str(tmp_path_factory.mktemp("history") / "none.jsonl")
    try:
        yield
    finally:
        os.environ.pop("CINEMA_PRICE_HISTORY", None)


@pytest.fixture
def offline_steps(monkeypatch):
    """The refresh orchestration tests fake the chains' readers but run in live mode (offline=False); the
    phase-2 steps then run as they do in a fixture run (ctx["offline"]). Each step's live path is tested in its
    own file, against injected clients — never the network."""
    import refresh
    real = refresh.run_steps
    monkeypatch.setattr(refresh, "run_steps",
                        lambda data, ctx, steps_dir=None: real(data, {**ctx, "offline": True}, steps_dir))
