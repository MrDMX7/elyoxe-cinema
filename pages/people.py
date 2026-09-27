"""Cast & directors pages (phase 2, A. People): /people/<slug>/ and /en/people/<slug>/, and a cast strip on every
film page (slot film.cast, the «الطاقم» tab). Data: data["people"] and film["cast"] / film["directors"] (steps/people.py).

A person gets a page only with a name (Arabic or English) and at least one film we list (showing or archived).
The page: the photo (only a freely licensed one, with its author and licence under it), the names, two sentences
from Wikipedia with a link to the article, «يعرض له الحين» (the films showing now, as poster tiles with the
cheapest ticket — price cells the client reprices after the visitor's card), the films of theirs we listed before
(archived pages), their notable works from Wikidata (text, capped) and JSON-LD Person."""
import re

from site_kit import P, PAGE_TARGET, SITE, Page, Plugin, esc

CSS = ("people",)
DIRS = ("people",)
PHOTO = re.compile(r"^/posters/people/[A-Za-z0-9._-]+\.webp$")
SAFE = re.compile(r"^https://[^\s\"'<>]+$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")
QID = re.compile(r"^Q\d+$")
TILES = 18          # poster tiles for showing films; any beyond are text links
NOTABLE = 12
STRIP = 10          # people in a film page's strip


def _roles(g, directs, acts, lang):
    f = g == "f"
    if lang == "ar":
        r = (["مخرجة" if f else "مخرج"] if directs else []) + (["ممثلة" if f else "ممثل"] if acts else [])
        return " و".join(r)
    return " and ".join((["Director"] if directs else []) + (["Actor"] if acts else []))


class People:
    def __init__(self, site):
        self.s = site
        raw = site.d.get("people") or {}
        self.films_of = {}
        for fid, f in site.films.items():
            for role in ("directors", "cast"):
                for q in f.get(role) or []:
                    if isinstance(q, str):
                        roles = self.films_of.setdefault(q, {}).setdefault(fid, set())
                        roles.add(role)
        self.p = {}
        for q, p in raw.items():
            if not (isinstance(p, dict) and QID.match(str(q)) and SLUG.match(str(p.get("slug") or ""))):
                continue
            if not (p.get("name_ar") or p.get("name_en")) or not self.films_of.get(q):
                continue
            self.p[q] = p

    # -------- names
    def name(self, q, lang):
        p = self.p[q]
        return (p.get("name_ar") if lang == "ar" else p.get("name_en")) or p.get("name_en") or p.get("name_ar")

    def is_en(self, q, lang):
        return lang == "ar" and not self.p[q].get("name_ar")

    def name_attr(self, q, lang):
        return ' lang="en" dir="ltr"' if self.is_en(q, lang) else ""

    def href(self, q, lang):
        return P(lang, "people", self.p[q]["slug"])

    def photo(self, q):
        ph = self.p[q].get("photo") or {}
        if PHOTO.match(str(ph.get("src") or "")) and PHOTO.match(str(ph.get("src2x") or "")):
            return ph
        return None

    # -------- the person page
    def page(self, q, lang):
        s, p, ar = self.s, self.p[q], lang == "ar"
        nm = self.name(q, lang)
        fids = self.films_of[q]
        directs = any("directors" in r for r in fids.values())
        acts = any("cast" in r for r in fids.values())
        role = _roles(p.get("gender"), directs, acts, lang)
        head = s.crumbs(lang, (nm, None)) + f'<h1 class="pt"{self.name_attr(q, lang)}>{esc(nm)}</h1>'
        other = p.get("name_en") if ar else p.get("name_ar")
        if other and other != nm:
            head += f'<p class="fte"{"" if not ar else " lang=\"en\" dir=\"ltr\""}>{esc(other)}</p>'
        if role:
            head += f'<p class="pp-role">{esc(role)}</p>'
        ph = self.photo(q)
        fig = ""
        if ph:
            credit = []
            if ph.get("author"):
                a = esc(ph["author"])
                credit.append(f'<a href="{esc(ph["page"])}" rel="noopener" target="_blank">{a}</a>' if SAFE.match(str(ph.get("page") or "")) else a)
            if ph.get("licence"):
                li = esc(ph["licence"])
                credit.append(f'<a href="{esc(ph["licence_url"])}" rel="noopener license" target="_blank" lang="en">{li}</a>'
                              if SAFE.match(str(ph.get("licence_url") or "")) else f'<span lang="en">{li}</span>')
            src = "ويكيميديا كومنز" if ar else "Wikimedia Commons"
            cap = (("الصورة: " if ar else "Photo: ") + ("، " if ar else ", ").join(credit) + (f"، عبر {src}" if ar else f", via {src}"))
            fig = (f'<figure class="pp-ph"><img src="{esc(ph["src"])}" srcset="{esc(ph["src"])} 160w, {esc(ph["src2x"])} 320w" sizes="160px"'
                   f' width="160" height="200" alt="{esc(nm)}" decoding="async" fetchpriority="high"><figcaption>{cap}</figcaption></figure>')
        bio = (p.get("bio") or {})
        b = bio.get(lang) or (bio.get("en") if ar else None)
        bio_html = ""
        if b and b.get("text"):
            en_on_ar = ar and b is not bio.get("ar")
            link = (f' <a class="src" href="{esc(b["url"])}" rel="noopener" target="_blank">{"ويكيبيديا" if ar else "Wikipedia"}</a>'
                    if SAFE.match(str(b.get("url") or "")) else "")
            bio_html = f'<p class="syn"{" lang=\"en\" dir=\"ltr\"" if en_on_ar else ""}>{esc(b["text"])}</p><p class="pp-src">{link}</p>'
        body = f'<section class="head wrap pp">{fig}<div class="pp-t">{head}{bio_html}</div></section>'

        showing = [f for f in fids if s.films[f].get("status") != "archived"]
        showing.sort(key=lambda f: (-s.today_count.get(f, 0), f))
        archived = sorted((f for f in fids if s.films[f].get("status") == "archived"), key=lambda f: str(s.films[f].get("last_seen") or ""), reverse=True)
        if showing:
            h2 = ("يعرض لها الحين" if p.get("gender") == "f" else "يعرض له الحين") if ar else "Showing now"
            tiles = "".join(s.film_tile(f, lang, s._by_film.get(f, [])) for f in showing[:TILES])
            more = "".join(f'<li><a href="{P(lang, "film", f)}"{s.title_attr(f, lang)}>{esc(s.ftitle(f, lang))}</a></li>' for f in showing[TILES:])
            body += (f'<section class="tonight wrap similar pp-now"><div class="sec-h"><h2>{esc(h2)}</h2></div>'
                     f'<div class="posters grid">{tiles}</div>' + (f'<ul class="pp-l">{more}</ul>' if more else "") + '</section>')
        if archived:
            h2 = ("عُرض لها في سينمات الإمارات" if p.get("gender") == "f" else "عُرض له في سينمات الإمارات") if ar else "Shown in UAE cinemas"
            items = "".join(f'<li><a href="{P(lang, "film", f)}"{s.title_attr(f, lang)}>{esc(s.ftitle(f, lang))}</a></li>' for f in archived)
            body += f'<section class="wrap pp-arch"><h2>{esc(h2)}</h2><ul class="pp-l">{items}</ul></section>'
        ours = {(s.films[f].get("wikidata") or {}).get("qid") for f in fids}
        works = [w for w in p.get("notable") or [] if isinstance(w, dict) and w.get("qid") not in ours and (w.get("en") or w.get("ar"))][:NOTABLE]
        if works:
            def wname(w):
                t = (w.get("ar") if ar else w.get("en")) or w.get("en") or w.get("ar")
                return f'<li class="nw"{" lang=\"en\" dir=\"ltr\"" if ar and not w.get("ar") else ""}>{esc(t)}</li>'
            src = f' <a class="src" href="https://www.wikidata.org/wiki/{q}" rel="noopener" target="_blank" lang="en">Wikidata</a>'
            body += (f'<section class="wrap pp-arch"><h2>{"أعمال بارزة" if ar else "Notable work"}</h2>'
                     f'<ul class="pp-l">{"".join(wname(w) for w in works)}</ul><p class="pp-src">{src}</p></section>')

        person = {"@type": "Person", "name": nm, "url": SITE + self.href(q, lang),
                  "sameAs": [f"https://www.wikidata.org/wiki/{q}"] + [x["url"] for x in bio.values() if x and SAFE.match(str(x.get("url") or ""))]}
        if other and other != nm: person["alternateName"] = other
        if ph: person["image"] = SITE + ph["src2x"]
        if b and b.get("text"): person["description"] = b["text"]
        if role: person["jobTitle"] = role
        graph = [person, s.breadcrumb_ld(lang, (nm, self.href(q, lang)))]
        names = [s.ftitle(f, lang) for f in showing[:3]]
        if ar:
            title = f"{nm} — {'أفلامها' if p.get('gender') == 'f' else 'أفلامه'} في سينما الإمارات"
            desc = (f"{nm}{('، ' + role) if role else ''}. " + (f"{'يعرض لها' if p.get('gender') == 'f' else 'يعرض له'} الحين: {'، '.join(names)} — المواعيد وأرخص تذكرة بعد خصم بطاقتك."
                    if names else "الأفلام اللي عُرضت في سينمات الإمارات."))
        else:
            title = f"{nm} — films in UAE cinemas"
            desc = (f"{nm}{(', ' + role.lower()) if role else ''}. " + (f"Showing now: {', '.join(names)} — showtimes and the cheapest ticket after your card."
                    if names else "Films shown in UAE cinemas."))
        return {"title": title, "desc": desc, "body": body, "kind": "person", "graph": graph,
                "og_image": SITE + ph["src2x"] if ph else None, "nav": "films"}

    # -------- the strip on a film page
    def strip(self, site, lang, fid):
        f = site.films.get(fid) or {}
        ar = lang == "ar"
        rows = [(q, "d") for q in f.get("directors") or [] if q in self.p] + [(q, "c") for q in f.get("cast") or [] if q in self.p]
        seen, items = set(), []
        for q, r in rows:
            if q in seen:
                continue
            seen.add(q)
            ph = self.photo(q)
            img = (f'<img src="{esc(ph["src"])}" width="48" height="60" alt="" loading="lazy" decoding="async">' if ph
                   else '<span class="cast-i" aria-hidden="true"></span>')
            g = self.p[q].get("gender") == "f"
            tag = f'<small>{("إخراج" if ar else "Director")}</small>' if r == "d" else ""
            items.append(f'<li><a href="{self.href(q, lang)}">{img}<span{self.name_attr(q, lang)}>{esc(self.name(q, lang))}</span>{tag}</a></li>')
            if len(items) >= STRIP:
                break
        if not items:
            return ""
        return f'<section class="cast"><h2 class="cast-h">{"طاقم الفيلم" if ar else "Cast and director"}</h2><ul class="cast-l">{"".join(items)}</ul></section>'


def register(site):
    ppl = People(site)
    pages = [Page(("people", p["slug"]), lang, (lambda q=q, lang=lang: ppl.page(q, lang)))
             for q, p in sorted(ppl.p.items(), key=lambda kv: kv[1]["slug"]) for lang in ("ar", "en")]
    return Plugin(pages=pages, slots={"film.cast": lambda site, lang, fid: ppl.strip(site, lang, fid)} if ppl.p else {})
