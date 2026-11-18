"""verdicts.repair_dialect / repair_json (owner 2026-11-18): the slips with exactly one right fix are fixed before the
dialect check, so a film is no longer left without a verdict or intel after every attempt for a tanwin, a leading «فيلم»
or a banned word the lexicon itself gives the replacement for. Everything else still goes back to the model."""
import json

import filmintel
import verdicts as vd


class _Msg:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class _Client:
    def __init__(self, texts):
        self.texts, self.calls = list(texts), 0
        outer = self

        class _M:
            def create(self, **kw):
                outer.calls += 1
                return _Msg(outer.texts[min(outer.calls - 1, len(outer.texts) - 1)])
        self.messages = _M()


def test_the_certain_fixes():
    assert vd.repair_dialect("فيلمٌ أكشن جداً") == "أكشن جدا"                 # tanwin first, then the opener
    assert vd.repair_dialect("فيلم Rocky يرجعك للثمانينات") == "Rocky يرجعك للثمانينات"
    assert vd.repair_dialect("وش القصة؟ شي جديد؟") == "شو القصة؟ شي يديد؟"    # whole words, ؟ is not part of one
    assert vd.repair_dialect("مين يحب الأكشن") == "منو يحب الأكشن"
    for s in ["الجديد هنا", "الفيلم فيه فيلم ثاني"]:                         # inside a longer word / not at the start
        assert vd.repair_dialect(s) == s
    for s in ["english only", "", None, 7]:
        assert vd.repair_dialect(s) == s
    assert vd.repair_dialect("الفيلم يجيك بقوة") == "الفيلم ييك بقوة"          # the lexicon's own word: يجيك←ييك
    for s in ["سيارة البطل", "ما نقدر نحكم عليه"]:                           # no single certain fix: the retry's
        assert vd.repair_dialect(s) == s and vd._dialect_violation(s)


def test_every_repaired_line_passes_the_check_it_was_failing():
    for s in ["قصة قويةٌ وتمثيلٌ حلو", "فيلم يشدّك من البداية", "وش يميّزه؟ إخراج جديد"]:
        assert vd._dialect_violation(s) and vd._dialect_violation(vd.repair_dialect(s)) is None


def test_repair_json_walks_every_string_and_keeps_keys():
    out = vd.repair_json({"reasons": [{"text": "قصةٌ حلوة", "pos": True}], "ar": "فيلم جميل", "n": 3, "en": "Good."})
    assert out == {"reasons": [{"text": "قصة حلوة", "pos": True}], "ar": "جميل", "n": 3, "en": "Good."}


OPEN_FIXABLE = json.dumps({
    "reasons": [{"text": "فيلم يشدّك، والقصة جديدة نوعاً ما.", "pos": True},
                {"text": "مدته طويلةٌ على وايد ناس.", "pos": False}],
    "audience": [], "fun_fact": None, "consensus_ar": None,
})
FILM ={"title": "Interstellar", "title_ar": "بين النجوم", "year": 2014, "genres": ["drama"], "runtime": 169}


def test_filmintel_takes_a_fixable_answer_on_the_first_call():
    client = _Client([OPEN_FIXABLE])
    out = filmintel._generate_one(client, "interstellar", FILM, None, [])
    assert client.calls == 1 and out["by"] == "claude"
    texts = [r["text"] for r in out["reasons"]]
    assert texts[0].startswith("يشدّك") and "ً" not in "".join(texts) and "ٌ" not in "".join(texts)


def test_the_imax_line_takes_a_fixable_answer_on_the_first_call(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "VERDICTS_DIR", tmp_path)
    fake = _Client([json.dumps({"ar": "فيلم ضخمٌ، يستاهل تشوفه بصيغة IMAX.", "en": "Worth the IMAX screen."})])
    monkeypatch.setattr(vd, "_client", lambda: fake)
    data = {"films": {"big-one": {"title": "Big One", "runtime": 150, "genres": {"en": ["drama"]}}}}
    res = vd.write_imax(data, {"big-one": {"Standard", "IMAX"}})
    assert fake.calls == 1 and res["big-one"]["ar"] == "ضخم، يستاهل تشوفه بصيغة IMAX."
