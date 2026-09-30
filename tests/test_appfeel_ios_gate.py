"""The iOS «ثبّت سينما» install hint (src/js/appfeel.js) must only ever show on real iOS Safari — never
Chrome on iOS (CriOS), never Android, never desktop, and never a Chromium browser spoofing an iPhone Safari
UA (exactly what the QA screenshot rig's Playwright `userAgent` override does, which is what made the hint
show on every QA still, 2026-09-30). iosSafariEligible() is the pure gate appfeel.js calls before building the
bar; this runs it standalone in node, the same pattern tests/test_js.py uses for src/js/pure.js."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")

IOS_SAFARI_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
IOS_CHROME_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/128.0 Mobile/15E148 Safari/604.1"
ANDROID_CHROME_UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
IPAD_SAFARI_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
DESKTOP_CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def _extract_fn():
    src = open(os.path.join(ROOT, "src", "js", "appfeel.js"), encoding="utf-8").read()
    m = re.search(r"function iosSafariEligible\([^)]*\)\s*\{.*?\n\}\n", src, re.S)
    assert m, "iosSafariEligible() not found in appfeel.js"
    return m.group(0)


def run(tmp_path, ua, platform, touch, has_chrome, vendor):
    fn = _extract_fn()
    call = "iosSafariEligible(%s,%s,%s,%s,%s)" % (
        json.dumps(ua), json.dumps(platform), touch, json.dumps(has_chrome), json.dumps(vendor)
    )
    (tmp_path / "t.js").write_text(fn + "\nprocess.stdout.write(JSON.stringify(" + call + "));\n", encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_real_ios_safari_and_ipados_safari_are_eligible(tmp_path):
    assert run(tmp_path, IOS_SAFARI_UA, "iPhone", 5, False, "Apple Computer, Inc.") is True
    # iPadOS 13+ Safari reports as a MacIntel desktop UA, distinguished only by touch points
    assert run(tmp_path, IPAD_SAFARI_UA, "MacIntel", 5, False, "Apple Computer, Inc.") is True


def test_chrome_on_ios_is_excluded(tmp_path):
    assert run(tmp_path, IOS_CHROME_UA, "iPhone", 5, True, "Google Inc.") is False


def test_android_chrome_is_excluded(tmp_path):
    assert run(tmp_path, ANDROID_CHROME_UA, "Linux armv8l", 5, True, "Google Inc.") is False


def test_desktop_is_excluded(tmp_path):
    assert run(tmp_path, DESKTOP_CHROME_UA, "Win32", 0, True, "Google Inc.") is False
    # a Mac laptop's trackpad is not a touchscreen: MacIntel alone (0-1 touch points) must not pass
    assert run(tmp_path, DESKTOP_CHROME_UA, "MacIntel", 0, True, "Google Inc.") is False


def test_a_chromium_browser_spoofing_the_iphone_safari_ua_is_excluded(tmp_path):
    # exactly the QA screenshot rig's setup: real Chrome, Playwright's `userAgent` context option set to an
    # iPhone Safari string. window.chrome and navigator.vendor are not touched by that override, so they are
    # the only signal left that this is not really Safari.
    assert run(tmp_path, IOS_SAFARI_UA, "iPhone", 5, True, "Google Inc.") is False
