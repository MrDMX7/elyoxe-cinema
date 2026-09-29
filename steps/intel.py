"""steps/intel.py — film intelligence (UNIT r3-film): reasons, audience opinion, a fun fact, and — only with a
sourced Wikipedia plot — a spoiler-gated ending explanation and Q&A, cached in intel/<fid>.json like
verdicts.py (filmintel.py owns the generation and the dialect gate). Capped per run and isolated by
refresh.py's run_steps like every other steps/*.py: a failure here never stops the publish.

Also reads OMDB_KEY (env, else AWS SSM /elyoxe/anthropic/... sibling path /elyoxe/omdb/key) and, only when a
key is configured, fills film["imdb_score"] from OMDb — omdb.py's own cache keeps this to at most one fetch
per film per OMDB_TTL, so a configured key never re-fetches every hour. No key: untouched, exactly as before
(insights.py's own comment: "no OMDb key: always empty")."""
from __future__ import annotations

import filmintel
import omdb


def run(data: dict, ctx: dict) -> dict | None:
    if ctx.get("offline"):
        return {"skipped": "offline"}
    results = filmintel.write_missing(data)
    for fid, film in data.get("films", {}).items():
        intel = filmintel.read(fid)
        if intel is not None and intel.get("by") == "claude":
            film["intel"] = intel
    omdb_report = omdb.fill_scores(data, ctx.get("data_dir"))
    return {"generated": len(results), "omdb": omdb_report}
