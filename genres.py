"""The fixed genre vocabulary of «سينما»: one key per genre, its Arabic and English label.

Readers hand over whatever the chain prints ("Action,Adventure", "Survival Thriller",
"Drama | Comedy", "Biography") and enrich.py adds Wikidata's labels ("superhero film",
"computer-animated film"); `genre_keys()` folds all of them onto GENRES' keys. The build reads
labels from GENRES only — latest.json carries keys, never labels.
"""
from __future__ import annotations

import re

GENRES: dict[str, tuple[str, str]] = {
    "action": ("أكشن", "Action"),
    "adventure": ("مغامرة", "Adventure"),
    "animation": ("أنيميشن", "Animation"),
    "comedy": ("كوميدي", "Comedy"),
    "crime": ("جريمة", "Crime"),
    "drama": ("دراما", "Drama"),
    "family": ("عائلي", "Family"),
    "fantasy": ("فانتازيا", "Fantasy"),
    "horror": ("رعب", "Horror"),
    "romance": ("رومانسي", "Romance"),
    "scifi": ("خيال علمي", "Sci-Fi"),
    "thriller": ("إثارة", "Thriller"),
    "documentary": ("وثائقي", "Documentary"),
    "music": ("موسيقي", "Music"),
    "sport": ("رياضي", "Sport"),
    "war": ("حرب", "War"),
    "other": ("أخرى", "Other"),
}
KEYS = tuple(GENRES)

# (key, pattern) — every pattern that matches a raw label adds its key. Word-bounded so "war"
# never matches "award" or "Star Wars"-style titles inside a longer label.
_RULES: list[tuple[str, re.Pattern]] = [(k, re.compile(p, re.I)) for k, p in [
    ("action", r"\baction\b|\bsuperhero|\bmartial arts\b|\bspy\b|\bdisaster\b"),
    ("adventure", r"\badventure|\bsurvival\b|\bswashbuckl"),
    ("animation", r"\banimat|\banime\b|\bcartoon"),
    ("comedy", r"\bcomed|\bcomic\b|\bsatir|\bparod|\bsitcom"),
    ("crime", r"\bcrime\b|\bgangster|\bheist|\bnoir\b|\bdetective|\bmafia"),
    ("drama", r"\bdrama|\bbiograph|\bbiopic|\bhistor|\bperiod\b|\bcoming[- ]of[- ]age"),
    ("family", r"\bfamily\b|\bchildren|\bkids?\b"),
    ("fantasy", r"\bfantas|\bfairy|\bmytholog|\bsword and sorcery"),
    ("horror", r"\bhorror|\bslasher|\bzombie|\bghost\b"),
    ("romance", r"\bromance|\bromantic|\blove story"),
    ("scifi", r"\bscience[- ]fiction|\bsci[- ]?fi\b|\bcyberpunk|\bspace opera|\bdystopi"),
    ("thriller", r"\bthriller|\bsuspense|\bmystery|\bpsychological\b|\bneo-noir"),
    ("documentary", r"\bdocumentar|\bdocu\b"),
    ("music", r"\bmusic|\bconcert|\bdance film"),
    ("sport", r"\bsports?\b"),
    ("war", r"\bwar\b|\bmilitary\b"),
]]
_SPLIT = re.compile(r"\s*(?:,|\||/|;|&|\band\b)\s*", re.I)


def genre_keys(raw) -> list[str]:
    """Raw genre labels (a list, or one "A, B | C" string) -> ordered unique GENRES keys.

    A label that maps to nothing becomes "other" only when no label mapped at all — a film with
    "Action, Biography" is ["action", "drama"], not ["action", "drama", "other"]. Known keys
    pass straight through, so the function is idempotent on its own output.
    """
    if not raw:
        return []
    items = [raw] if isinstance(raw, str) else list(raw)
    labels: list[str] = []
    for item in items:
        if not item or not isinstance(item, str):
            continue
        labels.extend(p for p in _SPLIT.split(item.strip()) if p)
    out: list[str] = []
    unmapped = False
    for label in labels:
        low = label.strip().lower()
        if low in GENRES:
            hits = [low]
        else:
            hits = [k for k, pat in _RULES if pat.search(label)]
        if not hits:
            unmapped = True
        for k in hits:
            if k not in out:
                out.append(k)
    if not out and unmapped:
        out.append("other")
    if len(out) > 1 and "other" in out:
        out.remove("other")
    return out


def merge_keys(*lists) -> list[str]:
    """Union of several key lists, first-seen order; "other" only survives alone."""
    out: list[str] = []
    for lst in lists:
        for k in lst or []:
            if k in GENRES and k not in out:
                out.append(k)
    if len(out) > 1 and "other" in out:
        out.remove("other")
    return out
