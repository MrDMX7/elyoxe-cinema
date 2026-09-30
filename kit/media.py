"""Posters and «الشاشة», the screen (MASTER-PLAN §1.6, W2-P1): the poster (or its typographic tile), the film's trailer
frame read and checked, and the screen's two parts — the layer behind the words (the graded frame, or the lit field
of the poster case) and the case itself. Owner in Wave 2: W2-P1 (MASTER-PLAN §6.2).

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)

# a phone draws the frame full-bleed: `100vw`, so a DPR-2 phone takes the 1280w file (the old "…, 320px" gave it the
# 640w file, a 4.3x upscale: MASTER-PLAN §4.2 #5); the portrait crop (W1-D1, only from a >= 1080p source) where one
# exists, for a phone only
FRAME_SIZES = "100vw"
PORTRAIT_MEDIA = "(max-width:767px)"
LANDSCAPE_MEDIA = "(min-width:768px)"
# the lit case: 120–160 px wide on a phone (block-size clamp(180px,27svh,240px), 2:3), 240 px on a desktop
CASE_SIZES = "(min-width:1024px) 240px, 160px"


def _int(v, d):
    """A positive int for a numeric attribute (never an f-string of a raw value), else `d`."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return d
    return v if v > 0 else d


class MediaKit:
    # -------- posters
    def poster(self, fid, lang, cls="pst", eager=False, size=(342, 513), lazy=True, sizes=None, srcset=True, label=True,
               backdrop_fallback=False):
        """The poster, or — when there is none (or it fails to load) — a typographic tile in the film's colour.
        `backdrop_fallback` (296, r4-home): a film with no poster but a trailer backdrop (steps/backdrops.py) draws
        a 2:3 crop of that frame instead — the portrait crop `p` when W1-D1 wrote one (already graded 2:3 for
        exactly this box), else the landscape frame (`w640`/`w1280`) cover-cropped by CSS at its own window `x`.
        The flat colour tile stays the fallback when there is neither (callers that place the tile inside a link
        already wrapping the whole card pass this; a poster still wins when the film has one)."""
        f = self.films[fid]
        pc = f.get("poster_color") or hue(fid)
        img = ""
        if f.get("poster"):
            first = self._first_poster is None and eager
            if first: self._first_poster, self._first_sizes = f, sizes or POSTER_SIZES.get(cls, POSTER_SIZES["pst"])
            # width descriptors + the size the tile is drawn at, so a desktop grid tile or a 72 px list poster
            # does not fetch the 684 px file on a 1x screen
            ss = (f' srcset="{esc(rel(f["poster"]))} 342w, {esc(rel(f["poster_2x"]))} 684w" sizes="{sizes or POSTER_SIZES.get(cls, POSTER_SIZES["pst"])}"'
                  if f.get("poster_2x") and srcset else "")
            # a real poster carries its own title: the tile's title stays underneath, hidden, and comes back
            # (the class drops) only if the image fails to load
            img = (f'<img src="{esc(rel(f["poster"]))}"{ss} width="{size[0]}" height="{size[1]}" alt="" decoding="async"'
                   + (' fetchpriority="high"' if first else ' loading="lazy"' if lazy else "") + ">")
            # (a tile names the film under its poster already: `label=False` leaves the hidden copy out)
            return (f'<span class="{cls} img" style="--pc:{pc}">' + (f'<span class="pst-t" aria-hidden="true"{self.title_attr(fid, lang)}>'
                    f'{esc(self.ftitle(fid, lang))}</span>' if label else "") + f'{img}</span>')
        if backdrop_fallback:
            fr = self.frame(fid)
            if fr:
                lazy_attr = ' loading="lazy"' if lazy else ""
                if fr.get("p"):
                    # the portrait crop is already 2:3, graded for exactly this box: no srcset needed
                    style, img = f'--pc:{pc}', (f'<img src="{esc(fr["p"])}" width="{fr["pw"]}" height="{fr["ph"]}" alt="" decoding="async"{lazy_attr}>')
                else:
                    # the landscape frame, CSS cover-cropped to 2:3 at its own window `x` (ui-tile.css .pst.bd)
                    ss2 = (f' srcset="{esc(fr["w640"])} 640w, {esc(fr["w1280"])} 1280w" sizes="{sizes or POSTER_SIZES.get(cls, POSTER_SIZES["pst"])}"'
                           if srcset else "")
                    x = f';--x:{round(fr["x"] * 100, 1):g}%' if "x" in fr else ""
                    style = f'--pc:{pc}{x}'
                    img = f'<img src="{esc(fr["w640"])}"{ss2} width="{fr["w"]}" height="{fr["h"]}" alt="" decoding="async"{lazy_attr}>'
                return (f'<span class="{cls} bd img" style="{style}">' + (f'<span class="pst-t"{self.title_attr(fid, lang)}>'
                        f'{esc(self.ftitle(fid, lang))}</span>' if label else "") + f'{img}</span>')
        return (f'<span class="{cls}" style="--pc:{pc}"><span class="pst-t"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</span></span>')

    # -------- «الشاشة»
    def frame(self, fid):
        """The film's trailer frame (steps/backdrops.py), or None. site_kit's __init__ checked the two landscape paths;
        W1-D1's newer keys are checked here before any of them reaches markup: the portrait crop `p` against
        OUR_BACKDROP with its positive size, the window `x` a number in [0, 1], the 4 spill colours against HEX."""
        bd = self.films[fid].get("backdrop")
        if not (isinstance(bd, dict) and bd.get("w1280") and bd.get("w640")): return None
        out = {"w1280": rel(bd["w1280"]), "w640": rel(bd["w640"]), "w": _int(bd.get("w"), 1280), "h": _int(bd.get("h"), 720)}
        pw, ph = _int(bd.get("pw"), 0), _int(bd.get("ph"), 0)
        if bd.get("p") and OUR_BACKDROP.match(str(bd["p"])) and pw and ph: out.update(p=rel(bd["p"]), pw=pw, ph=ph)
        x = bd.get("x")
        if isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 1: out["x"] = float(x)
        sp = bd.get("spill")
        if isinstance(sp, list) and len(sp) == 4 and all(isinstance(c, str) and HEX.match(c) for c in sp): out["spill"] = list(sp)
        return out

    def screen(self, fid, lang, first=True, case=True):
        """«الشاشة» (MASTER-PLAN §1.6): {kind, layer, case, preload, spill} for one film.
          kind "fr"    a graded trailer frame: `layer` is the picture, the portrait crop on a phone where W1-D1 wrote one
                       (<source media>), else the landscape frame at `100vw` placed at the frame's window `x`; grained
                       by the sheet; `spill` its 4 bottom-edge colours
          kind "lit"   no frame, a poster: the lit poster case. `layer` is the case's light (the poster's own colour in
                       the dark, no image: the blurred fog is gone, §4.2 #2) and `case` the sharp poster
          kind "noimg" neither: the velvet-to-night light, and as `case` the film's title in Markazi with its year (never
                       a flat block)
        `first`: the page's LCP picture — eager, fetchpriority high, and `preload` is its <link> (the same srcset,
        sizes and media as the picture, so one download serves both). Otherwise the picture is written unloaded
        (data-src / data-srcset) and src/js/bill.js loads it when its slide may be seen.
        `case=False`: the page draws its own poster card as the case (the film hero's .fposter), so no `case` here."""
        f = self.films[fid]
        pc = esc(f.get("poster_color") or hue(fid))
        fr = self.frame(fid)
        load = (lambda a, v: f' {a}="{v}"') if first else (lambda a, v: f' data-{a}="{v}"')
        pri = ' fetchpriority="high"' if first else ' decoding="async"'
        if fr:
            w1280, w640 = esc(fr["w1280"]), esc(fr["w640"])
            ss = f"{w640} 640w, {w1280} 1280w"
            x = f";--x:{round(fr['x'] * 100, 1):g}%" if "x" in fr else ""
            src = (f'<source media="{PORTRAIT_MEDIA}"{load("srcset", esc(fr["p"]))} width="{fr["pw"]}" height="{fr["ph"]}">'
                   if fr.get("p") else "")
            img = (f'<img{load("src", w1280)}{load("srcset", ss)} sizes="{FRAME_SIZES}" width="{fr["w"]}" height="{fr["h"]}"'
                   f' alt=""{pri} onerror="this.remove()">')
            pre = ""
            if first:
                land = f'<link rel="preload" as="image" href="{w1280}" imagesrcset="{ss}" imagesizes="{FRAME_SIZES}"'
                pre = (f'<link rel="preload" as="image" href="{esc(fr["p"])}" media="{PORTRAIT_MEDIA}" fetchpriority="high">'
                       f'{land} media="{LANDSCAPE_MEDIA}" fetchpriority="high">' if fr.get("p") else f'{land} fetchpriority="high">')
            return {"kind": "fr", "layer": f'<div class="bd fr" style="--pc:{pc}{x}" aria-hidden="true"><picture>{src}{img}</picture></div>',
                    "case": "", "preload": pre, "spill": fr.get("spill")}
        if f.get("poster"):
            p342 = esc(rel(f["poster"])); p684 = esc(rel(f.get("poster_2x") or f["poster"]))
            ss = f"{p342} 342w, {p684} 684w"
            cs = (f'<span class="case" style="--pc:{pc}"><img{load("src", p342)}{load("srcset", ss)} sizes="{CASE_SIZES}" width="342" height="513"'
                  f' alt=""{pri} onerror="this.remove()"></span>') if case else ""
            pre = (f'<link rel="preload" as="image" href="{p342}" imagesrcset="{ss}" imagesizes="{CASE_SIZES}" fetchpriority="high">'
                   if first and case else "")
            return {"kind": "lit", "layer": f'<div class="bd lit" style="--pc:{pc}" aria-hidden="true"></div>', "case": cs,
                    "preload": pre, "spill": None}
        yr = f'<span class="num">{esc(f["year"])}</span>' if f.get("year") else ""
        cs = (f'<span class="case pst" style="--pc:{pc}" aria-hidden="true"><span class="pst-t"{self.title_attr(fid, lang)}>'
              f'{esc(self.ftitle(fid, lang))}</span>{yr}</span>') if case else ""
        return {"kind": "noimg", "layer": f'<div class="bd noimg" style="--pc:{pc}" aria-hidden="true"></div>', "case": cs,
                "preload": "", "spill": None}

    def backdrop(self, fid, hero=False, sizes=None, lang="ar"):
        """The screen's layer alone, for a page that draws its own words and poster card over it (the film hero): the
        graded frame, else the lit field of the poster case. `hero`: it is the page's LCP picture (eager, and it sets
        the page's image preload). A frame is full-bleed on every page, so its `sizes` is always FRAME_SIZES (`100vw`):
        a caller's `sizes` is not read (the old "…, 320px" gave phones the 640w file, MASTER-PLAN §4.2 #5)."""
        s = self.screen(fid, lang, first=hero, case=False)
        if hero and s["preload"]: self._preload = s["preload"]
        return s["layer"]
