"""One real run: seed data/films_cache.json and verdicts/*.json for the current UAE slate.

Builds a minimal `data` dict (fid = readers.common.slug(title)) for the ~25 films actually
playing in UAE cinemas as of 2026-09-25 (per the owner's list), enriches it for real
(Wikidata + Rotten Tomatoes + Wikipedia — network allowed here, unlike the tests), pulls in
the matching paragraph from research_notes/…/reviews.md as extra context per film, and writes
any missing verdicts/<fid>.json. Safe to re-run: enrich() reuses the cache, write_missing()
never touches a file that already exists (hand-edited or already written).

Run: python seed_verdicts.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from readers.common import slug
from enrich import enrich
from verdicts import write_missing

FILMS = [
    "Heart of the Beast", "Resident Evil", "Crawlers", "Sacrifice",
    "Avengers: Endgame Encore", "Spider-Man: Brand New Day", "Coyote vs. Acme", "Fall 2",
    "Mutiny", "Bloody Tennis", "Shish Dou", "Red Flag", "Butterfly Effect: Azzam",
    "The Odyssey", "Practical Magic 2", "Toy Story 5", "Minions & Monsters", "Pressure",
    "Moana (live action)", "Insidious", "The Paradise", "The Vvaan",
    "Pradhama Drishtya Kuttakkar", "The Smurfs", "Digger",
]

REVIEWS_MD = (Path(__file__).resolve().parents[2] / "research_notes"
              / "أفلام سينمات العين سبتمبر 2026" / "reviews.md")

# a couple of titles need a second search hint for the paragraph match below, since the
# reviews.md prose names them slightly differently than the UAE listing does
_ALIASES = {
    "Avengers: Endgame Encore": ["Avengers: Endgame: Encore", "Avengers: Endgame"],
    "Butterfly Effect: Azzam": ["أثر الفراشة", "Azzam"],
    "Moana (live action)": ["Moana"],
    "The Smurfs": ["Smurfs"],
    "Fall 2": ["Fall 2: Deadpoint"],
}


def _notes_for(title: str, text: str) -> str | None:
    """Pulls the bullet block(s) mentioning this film out of reviews.md, if any.

    reviews.md nests a film's actual ratings (RT %, Metacritic, box office, ...) as indented
    sub-bullets under one top-level "- **Title** (...)" line, and those sub-bullet lines don't
    repeat the title (e.g. "  - RT 96% (249 critics), Certified Fresh; Metacritic 79 ..." has
    no "Resident Evil" in it). Matching only lines that literally contain the title — the
    original approach — silently dropped every sub-bullet, which is how the round-1 Resident
    Evil verdict ended up citing Metacritic 79 instead of the RT 96% two lines below it. Fixed
    by grabbing a matched top-level bullet's full indented block, not just the matching line.
    """
    candidates = [title] + _ALIASES.get(title, [])
    lines = text.splitlines()
    blocks, i = [], 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        is_top_bullet = stripped.startswith("-") and indent <= 2
        if is_top_bullet and any(c.lower() in stripped.lower() for c in candidates):
            block = [stripped]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    break
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt_indent <= indent:
                    break
                block.append(nxt.strip())
                j += 1
            blocks.append("\n".join(block))
            i = j
        else:
            i += 1
    return "\n\n".join(blocks) if blocks else None


# reviews.md's own "What films are in UAE cinemas" section lists titles under a language
# header ("**English:** ...", "**Malayalam:** ...", ...) — parsed here instead of hardcoded,
# so the same logic covers the ~50 more films the live job will add later, not just today's 25.
# Round-1 controller fix: Pradhama Drishtya Kuttakkar was mislabeled "Bollywood" in the first
# pass — it's Malayalam, and only the "Hindi" bucket is actually Bollywood.
_LANG_LABEL_AR = {
    "english": "إنجليزية", "arabic": "عربية (مصرية)", "hindi": "هندية (بوليوود)",
    "malayalam": "مليالم", "tamil": "تاميل", "telugu": "تيلوغو", "punjabi": "بنجابية",
    "tagalog": "تاغالوغ", "nepali": "نيبالية",
}
_LANG_HEADER = re.compile(r"^\s*-\s*\*\*([A-Za-z]+):\*\*\s*(.*)$")


def _language_for(title: str, text: str) -> str | None:
    candidates = [title] + _ALIASES.get(title, [])
    for line in text.splitlines():
        m = _LANG_HEADER.match(line)
        if not m:
            continue
        lang, rest = m.group(1).lower(), m.group(2)
        if lang not in _LANG_LABEL_AR:
            continue
        entries = [e.strip() for e in rest.split(",")]
        if any(any(c.lower() in e.lower() for c in candidates) for e in entries):
            return _LANG_LABEL_AR[lang]
    return None


# Wikidata search hints for titles that collide with an older or unrelated work of the same
# name — the displayed title stays the UAE listing's own title; only the lookup query changes.
_SEARCH_TITLE_HINTS = {
    "The Odyssey": "Christopher Nolan The Odyssey",  # else matches a 2016 Jérôme Salle film
    "Insidious": "Insidious: Out of the Further",     # "Insidious" alone is the whole franchise
}


def build_data() -> dict:
    films = {}
    for t in FILMS:
        f = {"title": t}
        if t in _SEARCH_TITLE_HINTS:
            f["search_title"] = _SEARCH_TITLE_HINTS[t]
        films[slug(t)] = f
    return {"films": films}


def main(only_titles: list[str] | None = None, force: bool = False):
    data = build_data()
    print(f"enriching {len(data['films'])} films (Wikidata + Rotten Tomatoes + Wikipedia)...")
    enrich(data, cache_path="data/films_cache.json")

    notes = {}
    if REVIEWS_MD.exists():
        text = REVIEWS_MD.read_text(encoding="utf-8")
        for title in FILMS:
            n = _notes_for(title, text)
            if n:
                notes[slug(title)] = n
            lang = _language_for(title, text)
            if lang:
                data["films"][slug(title)]["language"] = lang
    else:
        print(f"warning: reviews.md not found at {REVIEWS_MD}", file=sys.stderr)

    only_fids = {slug(t) for t in only_titles} if only_titles else None
    print(f"writing missing verdicts ({len(notes)} films have reviews.md context)..."
          + (f" [only_fids={only_fids}]" if only_fids else ""))
    results = write_missing(data, notes=notes, force=force, only_fids=only_fids)
    print(f"wrote/regenerated {len(results)} verdict(s); "
          f"{len(data['films']) - len(results)} left as-is (already had one, or not in only_fids).")

    for fid, film in data["films"].items():
        rt = film.get("rt") or {}
        print(f"  {fid:35s} title_ar={film.get('title_ar')!r:20s} lang={film.get('language')!r:15s} "
              f"rt_critics={rt.get('critics')} rt_audience={rt.get('audience')}")


if __name__ == "__main__":
    # python seed_verdicts.py                 -> full run (fills in any missing verdicts)
    # python seed_verdicts.py --fix "Title A" "Title B"  -> force-regenerate only these
    args = sys.argv[1:]
    if args and args[0] == "--fix":
        main(only_titles=args[1:], force=True)
    else:
        main()
