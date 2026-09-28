"""Home's billboard: the slides, the frame or the lit poster, the JSON island bill.js swaps from (pages/core.py's
billboard family, moved as it was by W1-P1). Owner in Wave 2: W2-P1 «الشاشة» (MASTER-PLAN §6.2).

Methods of pages.core.CorePages: `self` is a Pages, which reads everything else (self.page, self.poster,
self.shows ...) through to the site."""
from site_kit import *  # noqa: F401,F403  (the names these pages were written against)


class BillPages:
    # -------------------------------------------------- home: the billboard
    def bill_facts(self, fid, lang):
        """The billboard's facts, each its own span (no dots): the critics' (or audience's) score, the runtime,
        the rating when the score did not already take its place, two genres."""
        f = self.films[fid]; rt = f.get("rt") or {}
        out = [self.score(f, lang)]
        if f.get("runtime"): out.append(f'{num(f["runtime"])} {L(HOME_T["min"], lang)}')
        if f.get("rating") and (rt.get("critics") is not None or rt.get("audience") is not None):
            out.append(f'<bdi class="num" dir="ltr">{esc(f["rating"])}</bdi>')
        g = genre_words(f.get("genres"), lang)[:2]
        if g: out.append(esc(("، " if lang == "ar" else ", ").join(g)))
        return [x for x in out if x]

    def bill_film(self, fid, lang):
        """One film as the billboard's script swaps it in (the JSON island): what the server writes for the first."""
        f = self.films[fid]; v, vw = self.vword(fid, lang); vd = f.get("verdict") or {}
        say = vd.get("ar") if lang == "ar" else vd.get("en")
        bd = f.get("backdrop") if isinstance(f.get("backdrop"), dict) else None
        o = {"t": self.ftitle(fid, lang), "h": P(lang, "film", fid), "v": v, "w": vw, "x": self.bill_facts(fid, lang),
             "c": f.get("poster_color") or hue(fid)}
        if self.title_attr(fid, lang): o["e"] = 1
        if say and v != "unknown": o["s"] = dates(esc(say))   # no verdict yet: the word alone (Task 4 fix round 1, I4)
        if f.get("trailer"): o["tr"] = f["trailer"]
        if bd and bd.get("w1280") and bd.get("w640"): o["b"] = [rel(bd["w640"]), rel(bd["w1280"])]
        elif f.get("poster"): o["p"] = [rel(f["poster"]), rel(f.get("poster_2x") or f["poster"])]
        return o

    # a phone draws the frame darkened under the text: 640w is plenty (at 390 px, 2x, `100vw` took the 1280w file)
    BILL_BD_SIZES = "(min-width:1024px) 100vw, 320px"

    def bill_pick(self, ranked):
        """A city's five slides (fix round 1, I1): the first is its real most-shown film tonight, whatever it looks
        like (the eyebrow says so); the other four prefer the films of its top 10 that have a trailer frame, then
        the rest in order."""
        if not ranked: return []
        has = lambda f: isinstance(self.films[f].get("backdrop"), dict)
        rest = ranked[1:10]
        return (ranked[:1] + [f for f in rest if has(f)] + [f for f in ranked[1:] if not (f in rest and has(f))])[:5]

    def bill_frame(self, fid, o, lang):
        """The billboard's picture: the trailer frame (Kit.backdrop, 640w on a phone); with none yet, the poster — a
        heavily blurred, darkened full-bleed layer (the 342w file: blurred, its size does not show) and, on a
        desktop, a sharp copy at the inline end with the velvet glow (`sizes` 1px on a phone, so there it resolves
        to the same 342w file: one download); with no poster either, the film's typographic tile over the velvet
        glow (Kit.backdrop's fallback, shown). src/js/bill.js draws the same for the next films (fix round 1, I1)."""
        if o.get("b") or not o.get("p"): return self.backdrop(fid, hero=True, sizes=self.BILL_BD_SIZES, lang=lang)
        p342, p684 = esc(o["p"][0]), esc(o["p"][1])
        self.site._preload = f'<link rel="preload" as="image" href="{p342}" fetchpriority="high">'
        return (f'<div class="bd pf" style="--pc:{esc(o["c"])}" aria-hidden="true"><img src="{p342}" class="pb" alt="" width="342" height="513" decoding="async" fetchpriority="high">'
                f'<img src="{p342}" srcset="{p342} 342w, {p684} 684w" sizes="(min-width:1024px) 300px, 1px" class="ps" alt="" width="342" height="513" decoding="async"></div>')

    def bill_price(self, fid, shows):
        """[aed, chain, hall, hall key, cinema, table date]: the film's cheapest ticket among `shows`, the price
        cell's inputs (cinema.js reprices it after the visitor's card), or None."""
        b = self.min_price([s for s in shows if s["film"] == fid])
        if not b: return None
        aed, s = b; code, _ = self.hall_code_label(s)
        return [money(aed), self.cinemas[s["cinema"]]["chain"], code, self.hkey(s), s["cinema"], self.table_date(s)]

    def billboard(self, lang, tops, today):
        """The first of the default city's top 5, server-rendered over its trailer frame (Kit.backdrop, the page's
        LCP, preloaded), and the top 5 of every city as a JSON island: src/js/bill.js swaps the slide when the
        city changes and every 6 s (never under reduced motion; paused on hover, focus and a hidden tab)."""
        city = "dubai" if tops.get("dubai") else "*"
        fids = tops[city]; fid = fids[0]; o = self.bill_film(fid, lang)
        cn = L(CITY["dubai"], lang)
        eye = L(HOME_T["top_in"], lang).format(city=cn) if city != "*" else L(HOME_T["top"], lang)
        in_city = [s for s in today if self.cinemas[s["cinema"]].get("city") == "dubai"] if city != "*" else today
        if o.get("b"):
            self.site._preload = (f'<link rel="preload" as="image" href="{esc(o["b"][1])}" imagesrcset="{esc(o["b"][0])} 640w, {esc(o["b"][1])} 1280w"'
                                  f' imagesizes="{self.BILL_BD_SIZES}" fetchpriority="high">')
        mc = self.min_cell(in_city and [s for s in in_city if s["film"] == fid] or self._by_film.get(fid, []), lang)
        frm = (f'<span class="from" data-from="{esc(fid)}">{esc(L(HOME_T["from"], lang))} {mc[0]}</span>' if mc
               else f'<span class="from" data-from="{esc(fid)}" hidden></span>')
        tr = o.get("tr")
        trailer = (f'<a class="btn ghost" data-bill-tr href="{"https://www.youtube-nocookie.com/embed/" + esc(tr) if tr else "#"}"'
                   + (f' data-trailer="{esc(tr)}"' if tr else " hidden") + ' rel="noopener" target="_blank">'
                   f'<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>{esc(L(HOME_T["trailer"], lang))}</a>')
        say = f' {o["s"]}' if o.get("s") else ""
        slide = (f'<p class="eyebrow" data-bill-eye>{esc(eye)}</p>'
                 f'<h2 class="bill-t"><a href="{o["h"]}" data-bill-a{self.title_attr(fid, lang)}>{esc(o["t"])}</a></h2>'
                 f'<p class="bill-v" data-bill-v><b class="v-{o["v"]}">{esc(o["w"])}{"." if lang == "ar" or say else ""}</b>{say}</p>'
                 f'<p class="bill-f" data-bill-f>{"".join(f"<span>{x}</span>" for x in o["x"])}</p>'
                 f'<p class="cta"><a class="btn main" href="{o["h"]}" data-bill-go>{esc(L(HOME_T["times"], lang))}{frm}</a>{trailer}</p>')
        dots = "".join(f'<button type="button" aria-label="{esc(self.ftitle(x, lang))}" aria-pressed="{"true" if i == 0 else "false"}"><i></i></button>'
                       for i, x in enumerate(fids))
        # the island: each film once, then per city its top 5 with each one's cheapest ticket there
        by_city = {}
        for c, ids in tops.items():
            if not ids: continue   # nothing tonight there: bill.js shows the country's ("*")
            shows = today if c == "*" else [s for s in today if self.cinemas[s["cinema"]].get("city") == c]
            by_city[c] = [[x, self.bill_price(x, shows)] for x in ids]
        ffs = {x: self.bill_film(x, lang) for ids in tops.values() for x in ids}
        island = json.dumps({"f": ffs, "c": by_city}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        return (f'<section class="bill" data-bill aria-roledescription="{"عرض" if lang == "ar" else "carousel"}" aria-label="{esc(L(HOME_T["slides"], lang))}">'
                f'<div class="bill-bd" data-bill-bd>{self.bill_frame(fid, o, lang)}</div>'
                f'<div class="wrap bill-w"><div class="bill-in" data-bill-slide>{slide}</div>'
                f'<div class="bill-nav js-only"><button type="button" class="bill-pp" data-bill-pp aria-pressed="false"{"" if len(fids) > 1 else " hidden"}>'
                f'<span class="vh">{esc(L(HOME_T["pause"], lang))}</span></button>'
                f'<div class="dots" data-bill-dots role="group" aria-label="{esc(L(HOME_T["slides"], lang))}">{dots if len(fids) > 1 else ""}</div></div></div>'
                f'<script type="application/json" id="bill-data">{island}</script></section>')
