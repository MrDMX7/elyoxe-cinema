"""«شي يشبه» (phase 2, D): which films showing now are like this one — shared genres, shared people (cast and
directors, compared by person id), same language. A reason
is kept for every point so the page can say why, never a bare «you may also like».

similar(films, fid, pool, n=4, weight=None) -> [(fid, score, reasons)]
  films: latest.json's films (cast/directors: person ids, data["people"] keys); pool: the candidate fids
  reasons: [("person", pid), ...] + [("genre", key), ...] + [("lang", language)] — a pid is never printed as
  it is: the page names it from data["people"] or leaves it out."""
from site_kit import genre_keys


def _ids(v):
    """cast/directors as person ids: phase 2 stores Wikidata QIDs; a name string or {"qid"|"name": …} still reads."""
    if not v: return []
    if isinstance(v, (str, dict)): v = [v]
    out = []
    for x in v:
        n = (x.get("qid") or x.get("name") or x.get("name_en")) if isinstance(x, dict) else x
        if isinstance(n, str) and n.strip(): out.append(n.strip())
    return out


def people_of(films, people=None):
    """{fid: {person id}} from each film's cast (billing order, first 8) + directors."""
    return {fid: set(_ids(f.get("cast"))[:8]) | set(_ids(f.get("directors")) + _ids(f.get("director")))
            for fid, f in films.items()}


def similar(films, fid, pool, n=4, weight=None, _pp=None):
    me = films[fid]
    pp = _pp or people_of(films)
    mine_g, mine_p, lang = set(genre_keys(me)), pp.get(fid, set()), me.get("lang")
    rows = []
    for x in pool:
        if x == fid or x not in films: continue
        f = films[x]
        g = sorted(mine_g & set(genre_keys(f)))
        p = sorted(mine_p & pp.get(x, set()))
        same = bool(lang) and f.get("lang") == lang
        score = 3 * len(g) + 4 * len(p) + (1 if same else 0)
        if not g and not p: continue            # a shared language alone is not «يشبه»
        reasons = [("person", v) for v in p] + [("genre", v) for v in g] + ([("lang", lang)] if same else [])
        rows.append((x, score, reasons))
    w = weight or (lambda x: 0)
    rows.sort(key=lambda r: (-r[1], -w(r[0]), r[0]))
    return rows[:n]
