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
    """Pulls the bullet paragraph(s) mentioning this film out of reviews.md, if any."""
    candidates = [title] + _ALIASES.get(title, [])
    hits = []
    for line in text.splitlines():
        if any(c.lower() in line.lower() for c in candidates) and line.strip().startswith("-"):
            hits.append(line.strip())
    return "\n".join(hits) if hits else None


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


def main():
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
    else:
        print(f"warning: reviews.md not found at {REVIEWS_MD}", file=sys.stderr)

    print(f"writing missing verdicts ({len(notes)} films have reviews.md context)...")
    results = write_missing(data, notes=notes)
    print(f"wrote {len(results)} new verdict(s); "
          f"{len(data['films']) - len(results)} already had one (or are hand-edited).")

    for fid, film in data["films"].items():
        rt = film.get("rt") or {}
        print(f"  {fid:35s} title_ar={film.get('title_ar')!r:20s} "
              f"rt_critics={rt.get('critics')} rt_audience={rt.get('audience')}")


if __name__ == "__main__":
    main()
