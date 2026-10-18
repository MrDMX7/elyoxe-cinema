"""filmintel.py — richer film intelligence for the film page, spoiler-safe (UNIT r3-film, fix round): intel/<fid>.json,
written once per new/changed film, the same shape as verdicts.py — reused unchanged here, not duplicated
(the dialect gate, the Anthropic client, the JSON extractor: verdicts.EMIRATI_SYSTEM_NOTE, ._dialect_violation,
._client, ._extract_json, ._genre_labels, ._site_lines).

Never invents a fact. Every reason, audience point, fun fact and spoiler answer must trace to a number or
text actually passed in the prompt: the site's own title/runtime/genre (verdicts._site_lines), RT critics/
audience/consensus, a Wikipedia "Plot" section fetched for the film's own accepted Wikidata match (only once
the film has actually released — see is_released()), or Reddit post TITLES (never a comment body or a
username) named by source. A film with none of RT scores, a Wikidata match or reachable Reddit results gets
no intel file written beyond a "skip" marker — nothing shipped is better than something invented (memory:
feedback_emirati_dialect.md's honesty rule).

Two separate Claude calls, not one, so a spoiler can never leak into a field a visitor sees before opening a
spoiler gate (round-1 controller review, fix round): the "open" call (reasons/audience/fun_fact/consensus_ar)
never receives the plot text at all; only the "spoiler" call (ending/qa) does. A plot with no narrated ending
(e.g. a pre-release "Premise" section — excluded from PLOT_HEADINGS now, belt and suspenders) may honestly
answer ending: null, which is not an error.

write_missing(data, cap=INTEL_CAP) is the entry point (steps/intel.py calls it once a refresh, offline-safe,
never raising past its own catch). read(fid) is the page-side accessor (pages/intel.py).

intel/<fid>.json shape:
    {"fid", "reasons": [{"text", "pos": true|false}, 2-4], "audience": [{"text", "source"}, 0-3],
     "fun_fact": {"text", "source"} | null, "consensus_ar": "..." | null, "synopsis_ar": "..." | null (item 232:
     two or three spoiler-free Arabic sentences from film["synopsis_en"], the Wikipedia lead — null without one),
     "ending": "..." | null, "qa": [{"q","a"}, 0-8] (only with a real ending),
     "has_plot": bool, "written": "YYYY-MM-DD", "by": "claude",
     "next_check": "YYYY-MM-DD" | absent}   — present whenever a retry later might change the outcome
                                               (no ending yet, or a basis is still missing); absent once
                                               stable, so a finished record is never auto-rewritten
    {"fid", "by": "skip", "written": "...", "next_check": "..."}    — no basis yet; retried once one appears
    {"fid", "by": "failed", "written": "...", "next_check": "...", "reason": "..."}  — a bad run (dialect
        retries exhausted, API/network error); backed off so it can't eat the whole per-run cap every time
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

import requests

import verdicts as vd

INTEL_DIR = Path(__file__).resolve().parent / "intel"
MODEL = vd.MODEL
MAX_ATTEMPTS = 4
INTEL_CAP = 20   # per refresh run (raised from 8, 2026-09-30 — item 293) — light on the phone, never fails the run
RECHECK_DAYS = 3   # backoff before retrying a skip/failed film, or re-checking whether a plot now exists — a
                    # persistently-failing or pre-release film always sorts first in dict order, and without
                    # this it would eat the whole cap every run and starve every film after it (round-1 review)
UA = {"User-Agent": "elyoxe-cinema/1.0 (+https://cinema.elyoxe.com)"}

PLOT_HEADINGS = {"plot", "plot summary"}   # NOT premise/synopsis/storyline (round-1 review): those exist
                                            # before release and rarely narrate an ending, which forced the
                                            # model to invent one to satisfy an "ending required" rule
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
MIN_PLOT_CHARS = 200


def _wikidata_enwiki_title(qid: str) -> str | None:
    """The English Wikipedia page title for a Wikidata QID, or None (network failures never raise)."""
    try:
        r = requests.get("https://www.wikidata.org/w/api.php",
                          params={"action": "wbgetentities", "ids": qid, "props": "sitelinks", "format": "json"},
                          headers=UA, timeout=10)
        r.raise_for_status()
        ent = (r.json().get("entities") or {}).get(qid) or {}
        return ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title")
    except Exception:
        return None


def wikipedia_plot(qid: str | None) -> str | None:
    """The Wikipedia "Plot" section's plain text for a film whose Wikidata match was accepted (enrich.py) —
    its own real prose, never a guess. None with no match, no such section, a too-short one, or any network
    failure. Never raises.

    Uses the plain MediaWiki action API (action=parse), not the old REST "mobile-sections" endpoint, which
    now answers every request with 403 (deprecated/blocked, checked 2026-09-30) — two calls: `prop=sections`
    to find the Plot section's index (its number moves per film), then `prop=text&section=<n>` for its HTML,
    stripped to plain text."""
    if not qid:
        return None
    title = _wikidata_enwiki_title(qid)
    if not title:
        return None
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php",
                         params={"action": "parse", "page": title, "prop": "sections", "format": "json"},
                         headers=UA, timeout=10)
        r.raise_for_status()
        sections = (r.json().get("parse") or {}).get("sections") or []
    except Exception:
        return None
    idx = next((s.get("index") for s in sections
               if _WS.sub(" ", s.get("line") or "").strip().lower() in PLOT_HEADINGS), None)
    if not idx:
        return None
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php",
                         params={"action": "parse", "page": title, "prop": "text", "section": idx, "format": "json"},
                         headers=UA, timeout=10)
        r.raise_for_status()
        html = ((r.json().get("parse") or {}).get("text") or {}).get("*") or ""
    except Exception:
        return None
    text = _WS.sub(" ", _TAG.sub(" ", html)).strip()
    text = re.sub(r"^\S+\s*\[\s*edit\s*\]\s*", "", text)   # the section's own "Plot [ edit ]" heading, stripped
    return text if len(text) >= MIN_PLOT_CHARS else None


def reddit_snippets(title_en: str | None, year, cap: int = 6) -> list[str]:
    """Up to `cap` Reddit post TITLES (never a comment body, never a username) mentioning the film, from
    Reddit's public search JSON — best-effort, [] on any failure or if unreachable. Raw material for the
    model to paraphrase, never to quote (write_missing() rejects an output that echoes one near-verbatim)."""
    if not title_en:
        return []
    q = f"{title_en} {year or ''} review".strip()
    try:
        r = requests.get("https://www.reddit.com/search.json",
                          params={"q": q, "sort": "relevance", "limit": cap}, headers=UA, timeout=8)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    out = []
    for child in (data.get("data") or {}).get("children") or []:
        t = (child.get("data") or {}).get("title")
        if t and len(t.strip()) > 8:
            out.append(t.strip())
    return out[:cap]


def is_released(film: dict) -> bool:
    """False only when film["released"] (refresh.py's carry_released: a chain's own coming-soon release date,
    kept while the film still shows) names a real date after today. A film with no such field is assumed
    released — it is already in the site's showing list, which is the common case; "released" only exists at
    all for a film the coming-soon step is still tracking. Gates wikipedia_plot(): a plot fetched before
    release is usually a "Premise", not a narrated ending (round-1 review)."""
    rel = film.get("released")
    if isinstance(rel, str) and len(rel) == 10:
        return rel <= date.today().isoformat()
    return True


def has_intel_basis(film: dict) -> bool:
    """RT critics/audience, or a Wikidata match (so a plot or a fun fact can be built) — never generate from
    nothing but the title."""
    rt = film.get("rt") or {}
    return rt.get("critics") is not None or rt.get("audience") is not None or bool((film.get("wikidata") or {}).get("qid"))


def _next_check(days: int = RECHECK_DAYS) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def needs_generate(existing: dict | None, film: dict) -> bool:
    if existing is None:
        return True
    if existing.get("by") == "skip" and film.get("synopsis_en"):
        return True   # a synopsis appeared since the skip (steps/film_synopsis.py): no reason to wait out its backoff
    nxt = existing.get("next_check")
    if nxt and date.today().isoformat() < nxt:
        return False   # backed off — still due, don't spend a cap slot on it this run
    by = existing.get("by")
    if by == "skip":
        return has_intel_basis(film) or bool(film.get("synopsis_en"))   # a basis (or a synopsis) appeared since — try again
    if by == "failed":
        return True   # backoff window passed — retry
    if by == "claude":
        if film.get("synopsis_en") and "synopsis_ar" not in existing:
            return True   # the Arabic synopsis (item 232, 2026-10-17) is missing — only the open half is redone
        return not existing.get("has_plot", False)   # try again only to add the spoiler half once a real
                                                       # ending exists; a "claude" record that already has one
                                                       # is stable (cost, and dialect drift risk of mass
                                                       # regeneration) — hand-edited ("by": "hand") never touched
    return False


def _echoes_source(text: str, snippets: list[str]) -> bool:
    t = (text or "").strip()
    return any(len(s) > 15 and (s in t or t in s) for s in snippets)


OPEN_SYSTEM_EXTRA = """
أنت تكتب ذكاء إضافياً عن فيلم لصفحته (لا حكماً — الحكم مكتوب في مكان ثاني)، وما عندك قصة الفيلم بهذا الطلب
أبداً — فما تقدر تحرق الفيلم حتى لو حبيت. التزم:
- كل حقيقة (رقم، اسم) لازم تكون بالمعطيات تحت حرفياً — ممنوع الاختلاق أو الاستنتاج من معرفتك العامة عن الفيلم
  أو أحداثه.
- «reasons»: سببان إلى أربعة أسباب قصيرة («ليش يستاهل» أو «ليش لا») من الأرقام والحقائق فقط — لا حشو ولا
  مبالغة، وزّعها إيجابي/سلبي حسب الأرقام نفسها لا حسب رأيك.
- «audience»: ملخّص لرأي الجمهور بأسلوبك الخاص، بلا اقتباس حرفي من أي نص أعطيتك إياه (لا من إجماع النقاد ولا
  من عناوين Reddit) — لخّص المعنى فقط. لو ما فيه شي حقيقي تبني عليه رأي الجمهور، رجّع [] فاضية.
- «fun_fact»: معلومة وحدة فقط من الحقائق المعطاة تحت (لا من أحداث الفيلم اللي ما عندك أصلاً)، بمصدرها، أو
  null لو ما فيه شي مناسب.
- «consensus_ar»: لو أعطيتك إجماع نقاد إنجليزي تحت، لخّصه بالعربي بكلماتك بجملة أو جملتين — بلا نسخ حرفي.
  غير ذلك رجّعه null.
- «synopsis_ar»: لو أعطيتك ملخّصاً إنجليزياً للفيلم تحت، اكتب عن شو الفيلم بجملتين إلى ثلاث بالعربي من ذاك الملخّص
  فقط — بلا نهاية وبلا أي حرق، بلا تقييم، وبلا نسخ حرفي أو ترجمة آلية؛ أسماء الممثلين والأماكن الأجنبية بحروف
  لاتينية كما وردت، وبلا تنوين ولا «جوه/جوا» (قل «داخل»). غير ذلك رجّعه null.
- ممنوع تذكر مصدرك الداخلي («المعطيات»، «البيانات») — اكتب عن الفيلم نفسه دائماً.
"""

SPOILER_SYSTEM_EXTRA = """
أنت الآن تشرح نهاية فيلم وتجاوب أسئلة عنه من قصته الكاملة المعطاة تحت فقط — هذا القسم يحرق الفيلم، ومحجوب عن
الزائر بزر تحذير، وهذا مقصود. التزم:
- كل شي تكتبه لازم من القصة المعطاة تحت حرفياً — ممنوع أي معلومة من معرفتك العامة عن الفيلم.
- «ending»: شرح النهاية بجملتين إلى أربع، من القصة فقط. لو القصة المعطاة ملخّص عام بلا خاتمة واضحة (مثلاً
  فيلم لم يُعرض بعد)، رجّعه null بصراحة — ما تخترع نهاية.
- «qa»: أربعة إلى ثمانية أسئلة وأجوبة عن أحداث القصة، فقط لو كتبت ending حقيقي. لو ending null، رجّع [] فاضية.
"""


def _open_prompt(film: dict, reddit: list[str]) -> str:
    rt = film.get("rt") or {}
    lines = [
        f"الفيلم: {film.get('title')} ({film.get('title_ar') or 'بلا عنوان عربي'})",
        *vd._site_lines(film),
        f"السنة: {film.get('year')}",
        f"الأنواع: {', '.join(vd._genre_labels(film.get('genres')))}",
    ]
    if rt.get("critics") is not None:
        lines.append(f"Rotten Tomatoes (النقاد): {rt['critics']}% من {rt.get('critics_count')} نقد")
    if rt.get("audience") is not None:
        lines.append(f"Rotten Tomatoes (الجمهور): {rt['audience']}%")
    if rt.get("consensus"):
        lines.append(f"إجماع النقاد (إنجليزي، لخّصه بالعربي بكلماتك، لا تنسخه): {rt['consensus']}")
    if film.get("synopsis_en"):
        lines.append("ملخّص الفيلم (إنجليزي، من ويكيبيديا، بلا نهاية — اكتب منه synopsis_ar بكلماتك): "
                     + str(film["synopsis_en"])[:1200])
    if reddit:
        lines.append("عناوين نقاش عن الفيلم من Reddit (لخّص معناها بأسلوبك، لا تنسخها، ولا تذكر أسماء مستخدمين):\n"
                     + "\n".join(f"- {s}" for s in reddit))
    schema = (
        '{"reasons": [{"text": "...", "pos": true}, ...2-4], '
        '"audience": [{"text": "...", "source": "Rotten Tomatoes أو Reddit"}, ...0-3], '
        '"fun_fact": {"text": "...", "source": "..."} أو null, '
        '"consensus_ar": "..." أو null, '
        '"synopsis_ar": "..." أو null}'
    )
    lines.append("\nملاحظة: ما عندك قصة الفيلم هنا أبداً — لا تخمّن أي تفصيل من أحداثه.")
    lines.append("\nرد بـJSON فقط بهذا الشكل بلا أي نص آخر:\n" + schema)
    return "\n".join(lines)


SYNOPSIS_SYSTEM_EXTRA = """
أنت تكتب ملخّصاً قصيراً لفيلم لصفحته (لا حكماً ولا نهاية). التزم:
- «synopsis_ar»: عن شو الفيلم بجملتين إلى ثلاث بالعربي من الملخّص الإنجليزي المعطى تحت فقط — بلا نهاية وبلا أي حرق،
  بلا تقييم، وبلا نسخ حرفي أو ترجمة آلية. أسماء الممثلين والأماكن الأجنبية بحروف لاتينية كما وردت.
- بلا تنوين، وبلا كلمة «جديد/جديدة» (قل «أول» أو «يديد»)، وبلا «جوه/جوا» (قل «داخل»).
- ممنوع تذكر مصدرك («الملخّص»، «المعطيات») — اكتب عن الفيلم نفسه.
"""


def _synopsis_prompt(film: dict) -> str:
    """The synopsis alone (item 232): a finished record gains its Arabic synopsis without re-asking for — and risking —
    the reasons, audience and consensus it already carries (the first try re-ran the whole open half and 3 of 5
    films failed on a word in a field that was already good)."""
    lines = [
        f"الفيلم: {film.get('title')} ({film.get('title_ar') or 'بلا عنوان عربي'})",
        *vd._site_lines(film),
        f"السنة: {film.get('year')}",
        f"الأنواع: {', '.join(vd._genre_labels(film.get('genres')))}",
        "ملخّص الفيلم (إنجليزي، من ويكيبيديا، بلا نهاية): " + str(film.get("synopsis_en") or "")[:1200],
        '\nرد بـJSON فقط بهذا الشكل بلا أي نص آخر:\n{"synopsis_ar": "..."}',
    ]
    return "\n".join(lines)


def _validate_synopsis(parsed: dict) -> str | None:
    syn = parsed.get("synopsis_ar")
    if isinstance(syn, str):
        syn = parsed["synopsis_ar"] = vd.TANWIN.sub("", syn).strip() or None
    if not syn:
        return "synopsis_ar must be a real Arabic synopsis, not null"
    if len(syn) > 700:
        return "synopsis_ar is too long — two or three sentences"
    return vd._dialect_violation(syn)


def _spoiler_prompt(film: dict, plot: str) -> str:
    schema = '{"ending": "..." أو null, "qa": [{"q": "...", "a": "..."}, ...4-8] أو []}'
    return (f"الفيلم: {film.get('title')}\n"
            "قصة الفيلم كاملة من ويكيبيديا (إنجليزي، فيها حرق):\n" + plot[:4000]
            + "\n\nرد بـJSON فقط بهذا الشكل بلا أي نص آخر:\n" + schema)


def _validate_open(parsed: dict, reddit: list[str], expects_consensus: bool, expects_synopsis: bool = False) -> str | None:
    reasons = parsed.get("reasons")
    if not isinstance(reasons, list) or not (2 <= len(reasons) <= 4):
        return "reasons must be a list of 2 to 4 items"
    for r in reasons:
        if not isinstance(r, dict) or not r.get("text") or "pos" not in r:
            return "each reason needs text and pos"
    audience = parsed.get("audience") or []
    if not isinstance(audience, list) or len(audience) > 3:
        return "audience must be a list of at most 3 items"
    for a in audience:
        if not isinstance(a, dict) or not a.get("text") or not a.get("source"):
            return "each audience point needs text and source"
        if a.get("source") == "Reddit" and not reddit:
            return "source Reddit was used but no Reddit titles were available"
        if _echoes_source(a["text"], reddit):
            return "an audience text echoes a Reddit title near verbatim — paraphrase it instead"
    ff = parsed.get("fun_fact")
    if ff is not None and (not isinstance(ff, dict) or not ff.get("text") or not ff.get("source")):
        return "fun_fact needs text and source, or null"
    consensus_ar = parsed.get("consensus_ar")
    if expects_consensus and not consensus_ar:
        return "a critics' consensus was given — consensus_ar must be a real paraphrase, not null"
    if not expects_consensus and consensus_ar:
        return "no critics' consensus was given — consensus_ar must be null"
    synopsis_ar = parsed.get("synopsis_ar")
    if isinstance(synopsis_ar, str):
        synopsis_ar = parsed["synopsis_ar"] = vd.TANWIN.sub("", synopsis_ar).strip() or None   # «عاماً» → «عاما»: prose, not speech
    if expects_synopsis and not (isinstance(synopsis_ar, str) and synopsis_ar.strip()):
        return "an English synopsis was given — synopsis_ar must be a real Arabic synopsis, not null"
    if not expects_synopsis and synopsis_ar:
        return "no synopsis was given — synopsis_ar must be null"
    if synopsis_ar and len(synopsis_ar) > 700:
        return "synopsis_ar is too long — two or three sentences"
    texts = [r.get("text", "") for r in reasons] + [a.get("text", "") for a in audience]
    if ff:
        texts.append(ff.get("text", ""))
    if consensus_ar:
        texts.append(consensus_ar)
    if synopsis_ar:
        texts.append(synopsis_ar)
    for t in texts:
        why = vd._dialect_violation(t)
        if why:
            return why
    return None


def _validate_spoiler(parsed: dict, plot: str) -> str | None:
    ending = parsed.get("ending")
    qa = parsed.get("qa")
    if ending is not None and not isinstance(ending, str):
        return "ending must be a string or null"
    if ending:
        if not isinstance(qa, list) or not (4 <= len(qa) <= 8):
            return "qa must be 4 to 8 items when a real ending is given"
        for item in qa:
            if not isinstance(item, dict) or not item.get("q") or not item.get("a"):
                return "each qa item needs q and a"
    else:
        if qa not in (None, []):
            return "no ending was given — qa must be empty"
    texts = []
    if ending:
        texts.append(ending)
    for item in (qa or []):
        texts.append(item.get("q", "")); texts.append(item.get("a", ""))
    for t in texts:
        why = vd._dialect_violation(t)
        if why:
            return why
    return None


def _call_json(client, prompt: str, sys_extra: str, validate_fn, *validate_args) -> dict:
    """Shared MAX_ATTEMPTS retry loop for either Claude call: parse, validate, and on a rejection tell the
    model why and ask again, exactly like verdicts.py's own retry loop."""
    last_reason = None
    for _attempt in range(MAX_ATTEMPTS):
        sys_note = vd.EMIRATI_SYSTEM_NOTE + "\n" + sys_extra
        if last_reason:
            sys_note += f"\n\nمحاولتك السابقة رُفضت لأن: {last_reason}. أعد الصياغة بلا هذه المخالفة."
        # thinking explicitly off (the CLI client takes it off with MAX_THINKING_TOKENS=0): claude-sonnet-5 on the API otherwise spends the WHOLE max_tokens budget
        # on its own extended thinking before any text (checked 2026-09-30 — max_tokens=1500 came back
        # stop_reason "max_tokens", 1500 thinking_tokens, no text block at all); {"type":"disabled"} confirmed
        # to give a plain end_turn with text instead.
        resp = client.messages.create(model=MODEL, max_tokens=4000, thinking={"type": "disabled"}, system=sys_note,
                                       messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        try:
            parsed = vd._extract_json(text)
        except (ValueError, json.JSONDecodeError) as e:
            last_reason = f"invalid JSON ({e})"
            continue
        why = validate_fn(parsed, *validate_args)
        if why:
            last_reason = why
            continue
        return parsed
    raise RuntimeError(f"could not produce compliant output after {MAX_ATTEMPTS} attempts (last: {last_reason})")


def _generate_one(client, fid: str, film: dict, plot: str | None, reddit: list[str],
                   existing: dict | None = None) -> dict:
    """Two calls, never one: the "open" fields (reasons/audience/fun_fact/consensus_ar) are asked for in a
    prompt that never contains the plot at all, so a spoiler cannot leak into them regardless of what the
    model does (round-1 review). The "spoiler" fields (ending/qa) are asked for only when a plot exists, from
    a separate prompt with nothing else in it. A "claude" record that already has its open half (added before
    a plot existed) reuses it instead of paying for it again — only the spoiler half is retried."""
    if existing and existing.get("by") == "claude":
        open_fields = {"reasons": existing.get("reasons") or [], "audience": existing.get("audience") or [],
                        "fun_fact": existing.get("fun_fact"), "consensus_ar": existing.get("consensus_ar"),
                        "synopsis_ar": existing.get("synopsis_ar")}
        if "synopsis_ar" not in existing and film.get("synopsis_en"):   # the one missing half, on its own
            open_fields["synopsis_ar"] = _call_json(client, _synopsis_prompt(film), SYNOPSIS_SYSTEM_EXTRA,
                                                    _validate_synopsis).get("synopsis_ar")
    else:
        rt = film.get("rt") or {}
        open_fields = _call_json(client, _open_prompt(film, reddit), OPEN_SYSTEM_EXTRA, _validate_open,
                                  reddit, bool(rt.get("consensus")), bool(film.get("synopsis_en")))

    ending, qa = None, []
    if existing and existing.get("by") == "claude" and existing.get("has_plot") and existing.get("ending"):
        ending, qa = existing["ending"], (existing.get("qa") or [])[:8]   # a finished spoiler half is never paid for twice
    elif plot:
        spoiler = _call_json(client, _spoiler_prompt(film, plot), SPOILER_SYSTEM_EXTRA, _validate_spoiler, plot)
        ending = spoiler.get("ending")
        qa = (spoiler.get("qa") or [])[:8] if ending else []

    out = {
        "fid": fid,
        "reasons": open_fields.get("reasons") or [],
        "audience": open_fields.get("audience") or [],
        "fun_fact": open_fields.get("fun_fact"),
        "consensus_ar": open_fields.get("consensus_ar"),
        "synopsis_ar": open_fields.get("synopsis_ar"),
        "ending": ending,
        "qa": qa,
        "has_plot": bool(ending),
        "written": date.today().isoformat(),
        "by": "claude",
    }
    if not out["has_plot"]:
        out["next_check"] = _next_check()   # retry the spoiler half once a real ending might exist
    return out


def _write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def read(fid: str) -> dict | None:
    path = INTEL_DIR / f"{fid}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_missing(data: dict, cap: int = INTEL_CAP, only_fids: set[str] | None = None) -> dict:
    """Writes or refreshes intel/<fid>.json for at most `cap` films a call — one or two Claude calls each, so
    the run stays light. A single film's failure (network, API, dialect retries exhausted) is caught, recorded
    with a backoff so it can't keep eating the cap every run, and skipped; never raises past this function."""
    INTEL_DIR.mkdir(exist_ok=True)
    client = None
    results: dict[str, dict] = {}
    done = 0
    for fid, film in data.get("films", {}).items():
        if done >= cap:
            break
        if only_fids is not None and fid not in only_fids:
            continue
        path = INTEL_DIR / f"{fid}.json"
        existing = None
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = None
        if not needs_generate(existing, film):
            continue
        done += 1
        try:
            if not has_intel_basis(film):
                if (existing or {}).get("by") == "claude" and existing.get("synopsis_ar"):
                    _write(path, {**existing, "next_check": _next_check()})   # its synopsis stays; look again later
                    continue
                if film.get("synopsis_en"):
                    # no scores and no Wikidata match, but a synopsis (steps/film_synopsis.py: Reel or OMDb): the
                    # Arabic synopsis alone — reasons stay with the numbers, which this film does not have yet
                    if client is None:
                        client = vd._client()
                    syn = _call_json(client, _synopsis_prompt(film), SYNOPSIS_SYSTEM_EXTRA, _validate_synopsis).get("synopsis_ar")
                    rec = {"fid": fid, "by": "claude", "reasons": [], "audience": [], "fun_fact": None, "consensus_ar": None,
                           "synopsis_ar": syn, "ending": None, "qa": [], "has_plot": False,
                           "written": date.today().isoformat(), "next_check": _next_check()}
                    _write(path, rec)
                    results[fid] = rec
                    continue
                _write(path, {"fid": fid, "by": "skip", "written": date.today().isoformat(),
                              "next_check": _next_check()})
                continue
            qid = (film.get("wikidata") or {}).get("qid")
            done_spoiler = bool(existing and existing.get("by") == "claude" and existing.get("has_plot"))
            plot = None if done_spoiler else (wikipedia_plot(qid) if is_released(film) else None)
            reddit = reddit_snippets(film.get("title"), film.get("year"))
            if client is None:
                client = vd._client()
            intel = _generate_one(client, fid, film, plot, reddit, existing)
            _write(path, intel)
            results[fid] = intel
        except Exception as e:  # noqa: BLE001 - one bad film must never stop the others or the run
            print(f"filmintel: {fid} failed: {e}")
            if existing and existing.get("by") == "claude":
                # a finished record stays (its reasons and spoiler half are paid for and good); only the half that
                # failed — the synopsis — is retried after the backoff (2026-10-17: five records were erased this way)
                _write(path, {**existing, "next_check": _next_check(), "retry_reason": str(e)[:200]})
                continue
            _write(path, {"fid": fid, "by": "failed", "written": date.today().isoformat(),
                          "next_check": _next_check(), "reason": str(e)[:200]})
            continue
    return results
