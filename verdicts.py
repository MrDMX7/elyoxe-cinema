"""Verdicts: verdicts/<fid>.json, written once per new film and never overwritten by hand.

write_missing(data, force=False) calls the Anthropic Messages API (model claude-sonnet-5) for
every film in `data["films"]` that has no verdicts/<fid>.json yet (or, with force=True, for
every claude-written one — a hand-edited file, "by" != "claude", is never touched either way)
and writes {"fid", "verdict": "yes|mixed|skip|unknown", "ar", "en", "basis", "written", "by"}.

The Arabic line is light Emirati dialect: the full rules live in the owner's memory file
`feedback_emirati_dialect.md` (mandatory lexicon, the kaf/jeem rule, no tanwin, Western digits
only) — EMIRATI_SYSTEM_NOTE below is that file's rules folded into the system prompt, and
_dialect_violation() is the automatic post-check the memory file says was skipped last time
(prog-01: 256 re-recorded lines) so this run rejects and regenerates instead of shipping it.
"anonymous" verdict: no ratings and no credible reviews found (small Indian/Filipino/Arabic
releases) — the Arabic line says so honestly instead of inventing a rating.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

VERDICTS_DIR = Path(__file__).resolve().parent / "verdicts"
VALID_VERDICTS = {"yes", "mixed", "skip", "unknown"}
MODEL = "claude-sonnet-5"
MAX_ATTEMPTS = 3

# Words the owner has explicitly banned from Emirati narration/dialogue (feedback_emirati_dialect.md),
# with the correct Emirati form noted in a comment. Word-boundary matched, not substring matched.
BANNED_WORDS = {
    "وش": "شو",
    "جوّه": "داخل",
    "جوه": "داخل",
    "مين": "منو",
    "بنزين": "بترول",
    "سيارة": "موتر / موترك",
    "جوال": "تلفون",
    "بوريك": "براويك",
    "يوريك": "يراويك",
    "امتلت": "فوّلت",
    "انبلّ": "اتخرّس",
    "انبل": "اتخرّس",
    "أشلع": "افصخ",
    "اشلع": "افصخ",
    "تبيها": "تباها",
    "تبيه": "تباه",
    "قِسها": "قيسها",
    "قسها": "قيسها",
    "رقمان": "رقمين",
    "فلمّا": "فيوم",
    "فلما": "فيوم",
    "يكذب": "يجذب",  # only the specific idiom the owner corrected; leave normal "يكذب/لا يكذب" alone in most contexts
    "وريك": "براويك",
}
ARABIC_INDIC_DIGITS = re.compile(r"[٠-٩]")
TANWIN = re.compile(r"[ًٌٍ]")  # ً ٌ ٍ


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", text, re.UNICODE)


def _dialect_violation(ar_text: str) -> str | None:
    """Returns a human-readable reason if ar_text breaks a mandatory rule, else None."""
    if ARABIC_INDIC_DIGITS.search(ar_text):
        return "Arabic-Indic digits (٠-٩) used — Western digits 0-9 only"
    if TANWIN.search(ar_text):
        return "tanwin (ً/ٌ/ٍ) in spoken text — never tanwin in the spoken register"
    toks = set(_tokens(ar_text))
    for bad in BANNED_WORDS:
        if bad in toks:
            return f'banned word "{bad}" used — say "{BANNED_WORDS[bad]}" instead'
    return None


EMIRATI_SYSTEM_NOTE = """أنت تكتب سطراً عربياً بلهجة إماراتية خفيفة لموقع سينما. اتبع هذه القواعد
بصرامة (من ملف تصحيحات المالك، ومخالفتها كلّفت إعادة تسجيل 256 مقطعاً مرة سابقة):

المعجم الإلزامي (استعمل العمود الأيمن، ولا تكتب العمود الأيسر أبداً):
شو (لا وش) · مب (أداة نفي) · موتر/موترك (لا سيارة، حين تخاطب) · بترول (لا بنزين) ·
تلفون (لا جوال) · براويك/يراويك (لا بوريك/يوريك) · فوّلت (لا امتلت) · اتخرّس (لا انبلّ) ·
افصخ (لا أشلع) · تباها (لا تبيها) · قيسها (لا قِسها) · رقمين (لا رقمان) · فيوم (لا فلمّا) ·
داخل (لا جوّه) · منو (لا مين) · يديد/الياي (فقط لو ذكرتها، لا تعمّم ج←ي على كل كلمة).

قاعدة الكاف/الجيم: لاحقة المخاطبة "ـج" للأنثى فقط. إذا خاطبت مشاهداً عاماً أو مذكراً
فاكتب دائماً بالكاف الصريحة (لك، عليك، تلفونك) ولا تكتب أبداً "لج، عليج، تلفونج" في سياق غير مؤنث.

ممنوع تماماً: أي تنوين (ً/ٌ/ٍ) في النص المنطوق — "عدد صحيح" لا "عدداً صحيحاً".
ممنوع تماماً: الأرقام الهندية العربية (٠١٢٣٤٥٦٧٨٩) — استعمل 0-9 الغربية فقط في أي رقم أو نسبة
مثل 91% لا ٩١٪.

الأسلوب: جملتان قصيرتان كحد أقصى، كل جملة تحمل حقيقة واحدة (رقم أو حكم)، بلا حشو ولا مبالغة
("وايد" تُستخدم باعتدال لا في كل جملة). إذا لم تتوفر تقييمات كافية (أفلام هندية/فلبينية/عربية
صغيرة بلا نقاد) فقل ذلك بصراحة بدل اختلاق رقم، مثلاً: «ما لقينا تقييمات كافية لهالفيلم للحين."""


def _client():
    """Anthropic client: ANTHROPIC_API_KEY env var, else AWS SSM /elyoxe/anthropic/key."""
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        import boto3

        ssm = boto3.client("ssm", region_name="ap-south-1")
        key = ssm.get_parameter(Name="/elyoxe/anthropic/key", WithDecryption=True)["Parameter"]["Value"]
    return anthropic.Anthropic(api_key=key)


def _film_prompt(fid: str, film: dict, extra_notes: str | None) -> str:
    rt = film.get("rt") or {}
    lines = [
        f"الفيلم: {film.get('title')} ({film.get('title_ar') or 'بلا عنوان عربي'})",
        f"السنة: {film.get('year')}",
        f"المخرج: {film.get('director')}",
        f"الأنواع: {', '.join(film.get('genres', {}).get('ar') or film.get('genres', {}).get('en') or [])}",
    ]
    if rt.get("critics") is not None:
        lines.append(f"Rotten Tomatoes (النقاد): {rt['critics']}% من {rt.get('critics_count')} نقد")
    if rt.get("audience") is not None:
        lines.append(f"Rotten Tomatoes (الجمهور): {rt['audience']}%")
    if rt.get("consensus"):
        lines.append(f"إجماع النقاد (إنجليزي): {rt['consensus']}")
    if film.get("synopsis_en"):
        lines.append(f"الملخص (إنجليزي): {film['synopsis_en']}")
    if extra_notes:
        lines.append("ملاحظات بحث إضافية:\n" + extra_notes)
    lines.append(
        "\nرد بـJSON فقط بهذا الشكل بلا أي نص آخر: "
        '{"verdict": "yes|mixed|skip|unknown", "ar": "جملة أو جملتان بالإماراتية", '
        '"en": "one or two sentences in English", '
        '"basis": "SHORT citation under 15 words, e.g. \'RT 91% (37 نقد) · الجمهور 88%\'"}'
    )
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON object in model output: {text!r}")
    return json.loads(m.group(0))


def _generate_one(client, fid: str, film: dict, extra_notes: str | None) -> dict:
    prompt = _film_prompt(fid, film, extra_notes)
    last_reason = None
    for attempt in range(MAX_ATTEMPTS):
        sys_note = EMIRATI_SYSTEM_NOTE
        if last_reason:
            sys_note += f"\n\nمحاولتك السابقة رُفضت لأن: {last_reason}. أعد الصياغة بلا هذه المخالفة."
        resp = client.messages.create(
            model=MODEL,
            max_tokens=700,
            system=sys_note,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        try:
            parsed = _extract_json(text)
        except (ValueError, json.JSONDecodeError) as e:
            last_reason = f"invalid JSON ({e})"
            continue

        ar = parsed.get("ar", "")
        verdict = parsed.get("verdict")
        reason = _dialect_violation(ar)
        if reason:
            last_reason = reason
            continue
        if verdict not in VALID_VERDICTS:
            last_reason = f'verdict "{verdict}" is not one of {sorted(VALID_VERDICTS)}'
            continue

        return {
            "fid": fid,
            "verdict": verdict,
            "ar": ar,
            "en": parsed.get("en", ""),
            "basis": parsed.get("basis", ""),
            "written": date.today().isoformat(),
            "by": "claude",
        }

    raise RuntimeError(f"{fid}: could not produce a compliant verdict after {MAX_ATTEMPTS} attempts "
                        f"(last reason: {last_reason})")


def write_missing(data: dict, force: bool = False, notes: dict[str, str] | None = None) -> dict:
    """Writes verdicts/<fid>.json for films that don't have one yet.

    force=True also regenerates films whose verdict was written by "claude" (still never a
    hand-edited file — "by" != "claude" is always left alone). `notes` is an optional
    {fid: extra research text} map (e.g. lines pulled from reviews.md) folded into the prompt.
    """
    VERDICTS_DIR.mkdir(exist_ok=True)
    notes = notes or {}
    client = None
    results = {}

    for fid, film in data.get("films", {}).items():
        path = VERDICTS_DIR / f"{fid}.json"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
            if existing.get("by") != "claude":
                continue  # hand-edited — never overwritten
            if not force:
                continue  # already have a claude verdict and force wasn't asked for

        if client is None:
            client = _client()

        verdict = _generate_one(client, fid, film, notes.get(fid))
        path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        results[fid] = verdict

    return results
