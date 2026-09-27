"""The suite's network guard (conftest.py) refuses every way the code reaches out — and remembers it."""
import subprocess

import pytest
import requests

import conftest


def _swallowed(fn):
    """Call fn like a step would (except Exception), then take the recorded attempt back so this test passes."""
    before = len(conftest.ATTEMPTS)
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        assert isinstance(e, conftest.NetworkBlocked) or isinstance(e.__context__, conftest.NetworkBlocked) \
            or "network call in a test" in str(e), repr(e)
    got = conftest.ATTEMPTS[before:]
    del conftest.ATTEMPTS[before:]
    return got


def test_requests_is_refused_and_recorded():
    got = _swallowed(lambda: requests.get("https://example.com/", timeout=5))
    assert got and ("example.com" in got[0])


def test_curl_cffi_is_refused_and_recorded():
    cr = pytest.importorskip("curl_cffi.requests")
    assert _swallowed(lambda: cr.get("https://example.com/", timeout=5)) == ["curl_cffi perform"]


def test_aws_cli_is_refused_and_recorded():
    got = _swallowed(lambda: subprocess.run(["aws", "s3", "ls"], capture_output=True))
    assert got and got[0].startswith("aws cli s3")
