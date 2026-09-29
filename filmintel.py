"""filmintel.py — richer film intelligence for the film page, spoiler-safe (UNIT r3-film): intel/<fid>.json,
written once per new/changed film, the same shape as verdicts.py — reused unchanged here, not duplicated
(the dialect gate, the Anthropic client, the JSON extractor: verdicts.EMIRATI_SYSTEM_NOTE, ._dialect_violation,
._client, ._extract_json, ._genre_labels, ._site_lines).

Never invents a fact. Every reason, audience point, fun fact and spoiler answer must trace to a number or
text actually passed in the prompt: the site's own title/runtime/genre (verdicts._site_lines), RT critics/
audience/consensus, a Wikipedia "Plot" section fetched for the film's own accepted Wikidata match, or Reddit
post TITLES (never a comment body or a username) named by source. A film with none of RT scores, a Wikidata
match or reachable Reddit results gets no intel file written beyond a "skip" marker — nothing shipped is
better than something invented (memory: feedback_emirati_dialect.md's honesty rule).

write_missing(data, cap=INTEL_CAP) is the entry point (steps/intel.py calls it once a refresh, offline-safe,
never raising past its own catch). read(fid) is the page-side accessor (pages/intel.py).

intel/<fid>.json shape:
    {"fid", "reasons": [{"text", "pos": true|false}, 2-4], "audience": [{"text", "source"}, 0-3],
     "fun_fact": {"text", "source"} | null, "ending": "..." | null (only with has_plot), "qa": [{"q","a"}, 0-8],
     "has_plot": bool, "written": "YYYY-MM-DD", "by": "claude"}
    {"fid", "by": "skip", "written": "YYYY-MM-DD"}   — no basis yet; retried once a basis appears
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import requests

import verdicts as vd

INTEL_DIR = Path(__file__).resolve().parent / "intel"
MODEL = vd.MODEL
MAX_ATTEMPTS = 4
INTEL_CAP = 8   # per refresh run — one Claude call per new film, light on the phone, never fails the run
UA = {"User-Agent": "elyoxe-cinema/1.0 (+https://cinema.elyoxe.com)"}

PLOT_HEADINGS = {"plot", "plot summary", "synopsis", "premise", "storyline"}
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


def has_intel_basis(film: dict) -> bool:
    """RT critics/audience, or a Wikidata match (so a plot or a fun fact can be built) — never generate from
    nothing but the title."""
    rt = film.get("rt") or {}
    return rt.get("critics") is not None or rt.get("audience") is not None or bool((film.get("wikidata") or {}).get("qid"))


def needs_generate(existing: dict | None, film: dict) -> bool:
    if existing is None:
        return True
    if existing.get("by") == "skip":
        return has_intel_basis(film)   # a basis appeared since — try again
    return False   # a "claude" file is stable (cost, and dialect drift risk of mass regeneration); hand-edited never touched


def _echoes_source(text: str, snippets: list[str]) -> bool:
    t = (text or "").strip()
    return any(len(s) > 15 and (s in t or t in s) for s in snippets)


INTEL_SYSTEM_EXTRA = """
أنت الآن تكتب ذكاء إضافياً عن فيلم لصفحته (لا حكماً — الحكم مكتوب في مكان ثاني). التزم:
- كل حقيقة (رقم، اسم، حدث بالقصة) لازم تكون بالمعطيات تحت حرفياً — ممنوع الاختلاق أو الاستنتاج من معرفتك العامة عن الفيلم.
- «reasons»: سببان إلى أربعة أسباب قصيرة («ليش يستاهل» أو «ليش لا») من الأرقام والحقائق فقط — لا حشو ولا مبالغة، وزّعها إيجابي/سلبي حسب الأرقام نفسها لا حسب رأيك.
- «audience»: ملخّص لرأي الجمهور بأسلوبك الخاص، بلا اقتباس حرفي من أي نص أعطيتك إياه (لا من إجماع النقاد ولا من عناوين Reddit) — لخّص المعنى فقط. لو ما فيه شي حقيقي تبني عليه رأي الجمهور، رجّع [] فاضية.
- «fun_fact»: معلومة وحدة فقط من القصة أو الحقائق المعطاة، بمصدرها («Wikipedia»)، أو null لو ما فيه شي مناسب.
- «ending» و«qa» (أسئلة عن الفيلم): فقط لو أعطيتك قصة الفيلم كاملة تحت — منها فقط، بلا أي معلومة من خارجها. لو ما أعطيتك قصة، رجّعهم null و[].
- ممنوع تذكر مصدرك بالاسم الداخلي («القصة اللي عطيتك»، «البيانات») — اكتب عن الفيلم نفسه دائماً.
"""


def _intel_prompt(film: dict, plot: str | None, reddit: list[str]) -> str:
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
        lines.append(f"إجماع النقاد (إنجليزي، لخّصه بكلماتك، لا تنسخه): {rt['consensus']}")
    if plot:
        lines.append("قصة الفيلم كاملة من ويكيبيديا (إنجليزي، فيها حرق — لقسمي ending وqa فقط):\n" + plot[:4000])
    if reddit:
        lines.append("عناوين نقاش عن الفيلم من Reddit (لخّص معناها بأسلوبك، لا تنسخها، ولا تذكر أسماء مستخدمين):\n"
                     + "\n".join(f"- {s}" for s in reddit))
    schema = (
        '{"reasons": [{"text": "...", "pos": true}, ...2-4], '
        '"audience": [{"text": "...", "source": "Rotten Tomatoes أو Reddit"}, ...0-3], '
        '"fun_fact": {"text": "...", "source": "Wikipedia"} أو null, '
        + ('"ending": "شرح النهاية بجملتين إلى أربع من القصة فوق", "qa": [{"q": "...", "a": "..."}, ...4-8]'
           if plot else '"ending": null, "qa": []')
        + "}"
    )
    lines.append("\nرد بـJSON فقط بهذا الشكل بلا أي نص آخر:\n" + schema)
    return "\n".join(lines)


def _validate(parsed: dict, plot: str | None, reddit: list[str]) -> str | None:
    reasons = parsed.get("reasons")
    if not isinstance(reasons, list) or not (2 <= len(reasons) <= 4):
        return "reasons must be a list of 2 to 4 items"
    for r in reasons:
        if not isinstance(r, dict) or not r.get("text") or "pos" not in r:
            return "each reason needs text and pos"
    audience = parsed.get("audience")
    if audience is None:
        audience = []
    if not isinstance(audience, list) or len(audience) > 3:
        return "audience must be a list of at most 3 items"
    for a in audience:
        if not isinstance(a, dict) or not a.get("text") or not a.get("source"):
            return "each audience point needs text and source"
        if _echoes_source(a["text"], reddit):
            return "an audience text echoes a Reddit title near verbatim — paraphrase it instead"
    ff = parsed.get("fun_fact")
    if ff is not None and (not isinstance(ff, dict) or not ff.get("text") or not ff.get("source")):
        return "fun_fact needs text and source, or null"
    if plot:
        if not parsed.get("ending"):
            return "a plot was given — ending must be a real explanation, not null/empty"
        qa = parsed.get("qa")
        if not isinstance(qa, list) or not (4 <= len(qa) <= 8):
            return "qa must be 4 to 8 items when a plot is given"
        for item in qa:
            if not isinstance(item, dict) or not item.get("q") or not item.get("a"):
                return "each qa item needs q and a"
    elif parsed.get("ending") or parsed.get("qa"):
        return "no plot was given — ending and qa must be null/[]"
    texts = [r.get("text", "") for r in reasons] + [a.get("text", "") for a in audience]
    if ff:
        texts.append(ff.get("text", ""))
    if parsed.get("ending"):
        texts.append(parsed["ending"])
    for qa in (parsed.get("qa") or []):
        texts.append(qa.get("q", "")); texts.append(qa.get("a", ""))
    for t in texts:
        why = vd._dialect_violation(t)
        if why:
            return why
    return None


def _generate_one(client, fid: str, film: dict, plot: str | None, reddit: list[str]) -> dict:
    prompt = _intel_prompt(film, plot, reddit)
    last_reason = None
    for _attempt in range(MAX_ATTEMPTS):
        sys_note = vd.EMIRATI_SYSTEM_NOTE + "\n" + INTEL_SYSTEM_EXTRA
        if last_reason:
            sys_note += f"\n\nمحاولتك السابقة رُفضت لأن: {last_reason}. أعد الصياغة بلا هذه المخالفة."
        # thinking explicitly off: this account's claude-sonnet-5 otherwise spends the WHOLE max_tokens budget
        # on its own extended thinking before any text (checked 2026-09-30 — max_tokens=1500 came back
        # stop_reason "max_tokens", 1500 thinking_tokens, no text block at all); {"type":"disabled"} confirmed
        # to give a plain end_turn with text instead. max_tokens raised too (this call's JSON, up to 8 Q&A
        # pairs plus everything else, is bigger than verdicts.py's one-paragraph verdict).
        resp = client.messages.create(model=MODEL, max_tokens=4000, thinking={"type": "disabled"}, system=sys_note,
                                       messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        try:
            parsed = vd._extract_json(text)
        except (ValueError, json.JSONDecodeError) as e:
            last_reason = f"invalid JSON ({e})"
            continue
        why = _validate(parsed, plot, reddit)
        if why:
            last_reason = why
            continue
        return {
            "fid": fid,
            "reasons": parsed["reasons"],
            "audience": parsed.get("audience") or [],
            "fun_fact": parsed.get("fun_fact"),
            "ending": parsed.get("ending") if plot else None,
            "qa": (parsed.get("qa") or [])[:8] if plot else [],
            "has_plot": bool(plot),
            "written": date.today().isoformat(),
            "by": "claude",
        }
    raise RuntimeError(f"{fid}: could not produce compliant intel after {MAX_ATTEMPTS} attempts (last: {last_reason})")


def _write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def read(fid: str) -> dict | None:
    path = INTEL_DIR / f"{fid}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_missing(data: dict, cap: int = INTEL_CAP, only_fids: set[str] | None = None) -> dict:
    """Writes or refreshes intel/<fid>.json for at most `cap` films a call — one Claude call each, so the run
    stays light. A single film's failure (network, API, dialect retries exhausted) is caught and skipped;
    never raises past this function."""
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
                _write(path, {"fid": fid, "by": "skip", "written": date.today().isoformat()})
                continue
            qid = (film.get("wikidata") or {}).get("qid")
            plot = wikipedia_plot(qid)
            reddit = reddit_snippets(film.get("title"), film.get("year"))
            if client is None:
                client = vd._client()
            intel = _generate_one(client, fid, film, plot, reddit)
            _write(path, intel)
            results[fid] = intel
        except Exception as e:  # noqa: BLE001 - one bad film must never stop the others or the run
            print(f"filmintel: {fid} failed: {e}")
            continue
    return results
