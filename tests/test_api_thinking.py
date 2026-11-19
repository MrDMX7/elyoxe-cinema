"""The API road sends thinking «disabled» unless a caller asks for it (found 2026-11-19): Haiku 5.5 thinks by default
on the API, and a verdict's 700 output tokens all went to thinking — a thinking block, stop_reason max_tokens, no text —
so every verdict on the GitHub runner (CINEMA_CLAUDE_VIA=api) failed «invalid JSON» from 10-28 on."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verdicts  # noqa: E402


class _Fake:
    def __init__(self):
        self.messages = self
        self.kw = None

    def create(self, **kw):
        self.kw = kw
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1, output_tokens=1), content=[])


def test_thinking_is_off_by_default_on_the_api_road():
    fake = _Fake()
    verdicts._UsageLogged(fake).messages.create(model=verdicts.MODEL, max_tokens=700, messages=[])
    assert fake.kw["thinking"] == {"type": "disabled"}


def test_a_caller_that_asks_for_thinking_keeps_it():
    fake = _Fake()
    verdicts._UsageLogged(fake).messages.create(model=verdicts.MODEL, max_tokens=4000, messages=[],
                                                thinking={"type": "adaptive"})
    assert fake.kw["thinking"] == {"type": "adaptive"}
