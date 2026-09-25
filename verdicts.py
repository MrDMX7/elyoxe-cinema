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
MAX_ATTEMPTS = 5

# The owner's canonical, actively-maintained Emirati lexicon (content/video/_system/EMIRATI-LEXICON.json,
# a sibling repo under the shared workspace). Loaded at call time, not vendored, so edits there apply
# here automatically; falls back to the curated list below if the file isn't reachable (e.g. a checkout
# of just this repo) rather than hard-failing.
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_LEXICON_PATH = _WORKSPACE_ROOT / "content" / "video" / "_system" / "EMIRATI-LEXICON.json"


def _load_lexicon() -> dict:
    try:
        return json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


_LEXICON = _load_lexicon()

# Words/phrases the owner has explicitly banned from Emirati narration/dialogue, with the correct
# Emirati form noted alongside — this repo's own curated list (feedback_emirati_dialect.md,
# round-1 controller review) plus whatever content/video/_system/EMIRATI-LEXICON.json adds. Word
# entries are word-boundary matched; phrase entries are substring matched (order matters — a phrase
# must be checked before a word it contains, e.g. "زي أي نص" before "زي").
BANNED_WORDS = {
    "وش": "شو", "ويش": "شو",
    "جوّه": "داخل", "جوه": "داخل", "جوا": "داخل", "جوّا": "داخل",
    "مين": "منو",
    "بنزين": "بترول",
    "سيارة": "موتر / موترك",
    "جوال": "تلفون",
    "بوريك": "براويك", "يوريك": "يراويك", "وريك": "براويك", "توريك": "تراويك", "ورّتك": "راوتك",
    "امتلت": "فوّلت",
    "انبلّ": "اتخرّس", "انبل": "اتخرّس",
    "أشلع": "افصخ", "اشلع": "افصخ",
    "تبيها": "تباها", "تبيه": "تباه", "تبي": "تبغي",
    "قِسها": "قيسها", "قسها": "قيسها",
    "رقمان": "رقمين",
    "فلمّا": "فيوم", "فلما": "فيوم",
    "يكذب": "يجذب",  # only the specific idiom the owner corrected; leave normal "يكذب/لا يكذب" alone in most contexts
    "يجي": "إيي", "يجيك": "ييك", "تجيك": "تييك",
    "زي": "شرات",
    "طيب": "انزين",
    "لحاله": "بروحه", "لحالها": "بروحها",
    "انسكب": "إنجب",
    "الجاي": "الياي",
    "جديد": "يديد", "جديدة": "يديدة",
    "خوّفتك": "ربشتك", "خوفتك": "ربشتك",
    "حاطه": "حاطنه",
    "كذا": "جذيه",
    # round-2 controller review, 2026-09-26 — caught in avengers-endgame-encore/mutiny/
    # toy-story-5/the-odyssey/insidious and generalized so the ~50-film live job doesn't
    # repeat them:
    "لسا": "بعد / بعدهم",           # "لسا" alone, not just inside "لين لسا"
    "والي": "واللي",                 # plain typo for the relative pronoun, not dialect
    "شاهده": "شوفه",                 # MSA register creeping into the Emirati line
    "ستاذم": "ستاثام",               # garbled transliteration of "Statham"
}
BANNED_WORDS.update(_LEXICON.get("words", {}))

BANNED_PHRASES = {
    "لين لسا": "استعمل صياغة مباشرة، مثلاً: وودي وباز بعدهم يشدّون",
    "فرح فيه": "حبّه",
}
BANNED_PHRASES.update(_LEXICON.get("phrases", {}))

# Verb roots whose common inflected forms (attached subject/object pronouns: يجيك، تجيك،
# بيجي، يجينا...) must be caught even though they aren't a literal dict key — a plain
# word-boundary/equality match on "يجي" alone lets "يجيك" through, which is exactly how it
# shipped in the very first heart-of-the-beast draft (round-2 controller review). Matched as
# a substring of the *token*, not a raw substring of the sentence, so it still respects word
# boundaries (won't fire on an unrelated word that happens to contain "يجي" across a boundary).
BANNED_ROOTS = {
    "يجي": "إيي (أو تصريفها: تييك، إيينا... حسب المخاطَب)",
    "تجي": "تصريف إيي المناسب للمخاطَب",
}

# A line that opens with "فيلم <title>" repeats a dull template the controller flagged twice
# (pradhama-drishtya-kuttakkar, pressure, sacrifice, the-paradise all did it independently) —
# checked structurally (start-of-string), not as a banned word, since "فيلم" mid-sentence is fine.
_FILM_OPENER = re.compile(r"^\s*فيلم\b")

ARABIC_INDIC_DIGITS = re.compile(r"[٠-٩]")
TANWIN = re.compile(r"[ًٌٍ]")  # ً ٌ ٍ
# Arabic diacritics (tashkeel, incl. shadda ّ and sukun ْ) — Python's re \w does NOT include
# combining marks (category Mn), so "جوّا" tokenizes as "جو"+"ا" and would never match the
# banned-word dict's "جوّا" key unless both sides are stripped of diacritics before comparing.
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ]")


def _strip_diacritics(text: str) -> str:
    return _DIACRITICS.sub("", text)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", _strip_diacritics(text), re.UNICODE)


_BANNED_WORDS_BARE = {_strip_diacritics(k): (k, v) for k, v in BANNED_WORDS.items()}


def _dialect_violation(ar_text: str) -> str | None:
    """Returns a human-readable reason if ar_text breaks a mandatory rule, else None."""
    if ARABIC_INDIC_DIGITS.search(ar_text):
        return "Arabic-Indic digits (٠-٩) used — Western digits 0-9 only"
    if TANWIN.search(ar_text):
        return "tanwin (ً/ٌ/ٍ) in spoken text — never tanwin in the spoken register"
    if _FILM_OPENER.match(ar_text):
        return 'opens with "فيلم <title>" — a repeated, dull template; vary the opening'
    bare_text = _strip_diacritics(ar_text)
    for phrase in BANNED_PHRASES:
        if _strip_diacritics(phrase) in bare_text:
            return f'banned phrase "{phrase}" used — say "{BANNED_PHRASES[phrase]}" instead'
    toks = _tokens(ar_text)
    tok_set = set(toks)
    for bad_bare, (bad, good) in _BANNED_WORDS_BARE.items():
        if bad_bare in tok_set:
            return f'banned word "{bad}" used — say "{good}" instead'
    for root, good in BANNED_ROOTS.items():
        root_bare = _strip_diacritics(root)
        if any(root_bare in tok for tok in toks):
            return f'inflected form of banned root "{root}" used — say "{good}" instead'
    return None


def _lexicon_prompt_block() -> str:
    """Renders the full merged banned-word/phrase table into the system prompt (not just a
    sample) so the model sees every entry the post-check will enforce, including whatever
    content/video/_system/EMIRATI-LEXICON.json adds on top of the curated list below."""
    word_lines = " · ".join(f"{bad}←{good}" for bad, good in sorted(BANNED_WORDS.items()))
    phrase_lines = " · ".join(f"«{bad}»←«{good}»" for bad, good in sorted(BANNED_PHRASES.items()))
    return f"ممنوعة (يسار) ← الصحيح (يمين):\n{word_lines}\n\nعبارات ممنوعة كاملة:\n{phrase_lines}"


EMIRATI_SYSTEM_NOTE = f"""أنت تكتب سطراً عربياً بلهجة إماراتية خفيفة لموقع سينما. اتبع هذه القواعد
بصرامة (من ملف تصحيحات المالك ومعجم content/video/_system/EMIRATI-LEXICON.json، ومخالفتها كلّفت
إعادة تسجيل 256 مقطعاً مرة سابقة):

{_lexicon_prompt_block()}

قاعدة الكاف/الجيم: لاحقة المخاطبة "ـج" للأنثى فقط. إذا خاطبت مشاهداً عاماً أو مذكراً
فاكتب دائماً بالكاف الصريحة (لك، عليك، تلفونك) ولا تكتب أبداً "لج، عليج، تلفونج" في سياق غير مؤنث.

ممنوع تماماً: أي تنوين (ً/ٌ/ٍ) في النص المنطوق — "عدد صحيح" لا "عدداً صحيحاً".
ممنوع تماماً: الأرقام الهندية العربية (٠١٢٣٤٥٦٧٨٩) — استعمل 0-9 الغربية فقط في أي رقم أو نسبة
مثل 91% لا ٩١٪.

قواعد الحقائق والمصدر (جولة تصحيح المالك الأولى، 2026-09-26):
- اذكر فقط أرقاماً وحقائق مررتها لك في البيانات أو الملاحظات — لا اختلاق ولا تخمين.
- لا تذكر أبداً عدد مرات العرض (showtimes/screenings) كدليل جودة — هذا رقم توزيع لا تقييم.
- لا تذكر أبداً أسواق التوقّع أو الرهان (Kalshi وأشباهها) كأساس للحكم — ولو ورد رقم منها في
  الملاحظات تجاهله تماماً. إذا ما فيه رقم تقييم نقدي رسمي (RT/Metacritic) بعد، افحص الملاحظات:
  لو فيها ردود فعل نقدية حقيقية مسمّاة بمطبوعة أو ناقد (مثل "THR قال..."، "Variety..."، "ناقد
  قال إنه أفضل دور له") فالحكم "mixed" واذكر تلك المطبوعات بالاسم في الأساس — لا تهملها وتكتب
  "unknown" وعندك مراجعات حقيقية بين يديك. "unknown" فقط لو ما فيه أي رد فعل نقدي مسمّى إطلاقاً.
- نسبة الإشغال اليومي (occupancy) مقبولة فقط في سياق شباك التذاكر الهندي، لا كدليل جودة عام.
- سمِّ لغة الفيلم بدقة عند وجودها في البيانات (مثلاً مليالم، تاميل، هندي، مصري) — **الأفلام
  الهندية غير الهندية لغةً ليست "بوليوود"**؛ بوليوود = السينما الهندية بالهندية تحديداً فقط.
- إذا توفّر رقم Rotten Tomatoes للنقاد فاستعمله كالمصدر الأساسي للأساس (basis)، لا Metacritic
  ولا Letterboxd — استعملهما فقط لو ما فيه رقم RT.
- إذا ما فيه اسم عربي شائع للفيلم فاكتب العنوان الإنجليزي بحروف لاتينية داخل السطر العربي (لا
  تُترجم ولا تُعرِّب حرفياً)، وإلا استعمل الاسم العربي المعطى.
- **نفس القاعدة على أسماء الممثلين/المخرجين**: لا تخمّن كتابة عربية لاسم أجنبي (مثل ستاثام أو
  أي اسم غير متأكد من رسمه بالعربي) — اكتبه بحروف لاتينية زي ما هو (Statham) بدل تعريب خاطئ.
- **ممنوع تبدأ السطر بكلمة "فيلم"** (مثل "فيلم Digger...") — ابدأ باسم الفيلم مباشرة أو بحكم
  أو برقم، ونوّع الصياغة.
- تصريفات الأفعال الممنوعة ممنوعة هي وياها: "يجي" ممنوعة بكل صيغها (يجيك، تجيك، بيجي، يجينا...)
  لا الفعل المجرد فقط — استعمل تصريف "إيي" المناسب دائماً.

الأسلوب: جملتان قصيرتان كحد أقصى، كل جملة تحمل حقيقة واحدة (رقم أو حكم)، بلا حشو ولا مبالغة
("وايد" تُستخدم باعتدال لا في كل جملة). إذا لم تتوفر تقييمات كافية (أفلام هندية/فلبينية/عربية
صغيرة بلا نقاد) فقل ذلك بصراحة بدل اختلاق رقم، مثلاً: «ما لقينا تقييمات كافية لهالفيلم للحين»."""


def _client():
    """Anthropic client: ANTHROPIC_API_KEY env var, else AWS SSM /elyoxe/anthropic/key."""
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        import boto3

        ssm = boto3.client("ssm", region_name="ap-south-1")
        key = ssm.get_parameter(Name="/elyoxe/anthropic/key", WithDecryption=True)["Parameter"]["Value"]
    return anthropic.Anthropic(api_key=key)


# Lines in reviews.md-style notes that must never reach the model as usable "facts" — prediction
# markets/betting odds are never a basis (controller ruling, round 1). Stripped defensively here
# even though the system prompt also tells the model to ignore them, since the notes text is
# free-form research prose the model shouldn't have to filter itself.
_NOTES_KEYWORD = re.compile(r"kalshi|betting market|prediction market|odds market", re.I)
_MD_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")


def _sanitize_notes(text: str) -> str:
    """Drops any clause mentioning a prediction/betting market, and the markdown citation
    links next to it. Clause boundaries here are the delimiters this research prose actually
    uses (". ", "; ", " — ", line breaks) rather than a bare "." split, since RT percentages
    and dollar figures ("53.8%", "$14M") contain periods that would wrongly end a clause.
    """
    out_lines = []
    for line in text.splitlines():
        clauses = re.split(r"(?<=[.;])\s+(?=[A-Z؀-ۿ])|\s+—\s+", line)
        kept = [c for c in clauses if not _NOTES_KEYWORD.search(c)]
        kept_line = " ".join(kept)
        # A citation link left dangling next to a dropped clause (e.g. "[Kalshi](url)") —
        # drop any remaining markdown link whose own text or URL still names the market.
        kept_line = _MD_LINK.sub(lambda m: "" if _NOTES_KEYWORD.search(m.group(0)) else m.group(0), kept_line)
        out_lines.append(kept_line.strip())
    return "\n".join(l for l in out_lines if l).strip()


def _film_prompt(fid: str, film: dict, extra_notes: str | None) -> str:
    rt = film.get("rt") or {}
    lines = [
        f"الفيلم: {film.get('title')} ({film.get('title_ar') or 'بلا عنوان عربي'})",
        f"السنة: {film.get('year')}",
        f"المخرج: {film.get('director')}",
        f"الأنواع: {', '.join(film.get('genres', {}).get('ar') or film.get('genres', {}).get('en') or [])}",
    ]
    if film.get("language"):
        lines.append(f"لغة الفيلم: {film['language']}")
    if rt.get("critics") is not None:
        lines.append(f"Rotten Tomatoes (النقاد، جُلِب الآن — الأحدث والمصدر الأساسي للأساس، "
                     f"تجاهل أي رقم RT مختلف بالملاحظات فهو قديم): {rt['critics']}% من {rt.get('critics_count')} نقد")
    if rt.get("audience") is not None:
        lines.append(f"Rotten Tomatoes (الجمهور): {rt['audience']}%")
    if rt.get("consensus"):
        lines.append(f"إجماع النقاد (إنجليزي): {rt['consensus']}")
    if film.get("synopsis_en"):
        lines.append(f"الملخص (إنجليزي): {film['synopsis_en']}")
    if extra_notes:
        clean_notes = _sanitize_notes(extra_notes)
        if clean_notes:
            lines.append("ملاحظات بحث إضافية (بلا أسواق توقّع/رهان — تم حذفها إن وجدت):\n" + clean_notes)
    lines.append(
        "\nرد بـJSON فقط بهذا الشكل بلا أي نص آخر: "
        '{"verdict": "yes|mixed|skip|unknown", "ar": "جملة أو جملتان بالإماراتية", '
        '"en": "one or two sentences in English", '
        '"basis": "SHORT citation under 15 words, RT first if available, e.g. \'RT 91% (37 نقد) · الجمهور 88%\'. '
        'Never a screening count. Never a prediction-market/betting number."}'
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


def write_missing(data: dict, force: bool = False, notes: dict[str, str] | None = None,
                   only_fids: set[str] | None = None) -> dict:
    """Writes verdicts/<fid>.json for films that don't have one yet.

    force=True also regenerates films whose verdict was written by "claude" (still never a
    hand-edited file — "by" != "claude" is always left alone). `notes` is an optional
    {fid: extra research text} map (e.g. lines pulled from reviews.md) folded into the prompt.
    `only_fids`, if given, restricts regeneration to that set of fids (e.g. a targeted fix
    round) — every other film is left exactly as it is, whether or not `force` is set.
    """
    VERDICTS_DIR.mkdir(exist_ok=True)
    notes = notes or {}
    client = None
    results = {}

    for fid, film in data.get("films", {}).items():
        if only_fids is not None and fid not in only_fids:
            continue
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
