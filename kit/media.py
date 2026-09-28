"""Posters and trailer frames: the poster (or its typographic tile) and the backdrop (site_kit.Kit's media
helpers, moved as they were by W1-P1). Owner in Wave 2: W2-P1 (MASTER-PLAN §6.2).

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)


class MediaKit:
    # -------- posters
    def poster(self, fid, lang, cls="pst", eager=False, size=(342, 513), lazy=True, sizes=None, srcset=True, label=True):
        """The poster, or — when there is none (or it fails to load) — a typographic tile in the film's colour."""
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
        return (f'<span class="{cls}" style="--pc:{pc}"><span class="pst-t"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</span></span>')

    def backdrop(self, fid, hero=False, sizes="100vw", lang="ar"):
        """A real frame from the film's trailer (steps/backdrops.py) when one was scored clean, at 640/1280
        widths, `sizes="100vw"` (it is drawn full-bleed, never at a fixed column like the poster): eager +
        `fetchpriority="high"` for the hero (the page's largest paint), lazy otherwise. Falls back to the
        old poster-blurred-over-its-colour treatment when the film has no backdrop entry yet (steps/backdrops.py
        hasn't reached it, its trailer failed every frame, or Kit's own sanitising in __init__ dropped a
        malformed entry) -- and to night + the velvet glow + the typographic tile when there is no poster
        either. Blurred 40 px, its resolution does not show: on a film page the poster-fallback path asks
        for exactly what the hero poster resolves to (same srcset and sizes, so one download serves both);
        on the home hero (desktop only, hidden on a phone, so lazy) the 342 px file."""
        f = self.films[fid]
        pc = f.get("poster_color") or hue(fid)
        bd = f.get("backdrop")
        if isinstance(bd, dict) and bd.get("w1280") and bd.get("w640"):
            w1280, w640 = esc(rel(bd["w1280"])), esc(rel(bd["w640"]))
            # int()'d like every other numeric attribute in this file (size[0]/size[1] above) --
            # never an f-string interpolation of a raw value, even one steps/backdrops.py itself
            # always writes as a plain int today (fix round 1, review Minor #1).
            try:
                w = int(bd.get("w") or 1280)
            except (TypeError, ValueError):
                w = 1280
            try:
                h = int(bd.get("h") or 720)
            except (TypeError, ValueError):
                h = 720
            attrs = (' fetchpriority="high"' if hero else "") + ("" if hero else ' loading="lazy"')
            img = (f'<img src="{w1280}" srcset="{w640} 640w, {w1280} 1280w" sizes="{sizes}" width="{w}" height="{h}"'
                   f' alt="" decoding="async"{attrs} onerror="this.remove()" class="fr">')
            return f'<div class="bd" style="--pc:{pc}" aria-hidden="true">{img}</div>'
        if f.get("poster"):
            ss = (f' srcset="{esc(rel(f["poster"]))} 342w, {esc(rel(f["poster_2x"]))} 684w" sizes="{POSTER_SIZES["pst hero"]}"'
                  if hero and f.get("poster_2x") else "")
            lz = "" if hero else ' loading="lazy"'
            img = f'<img src="{esc(rel(f["poster"]))}"{ss} alt="" width="342" height="513" decoding="async"{lz} onerror="this.remove()">'
            return f'<div class="bd" style="--pc:{pc}" aria-hidden="true">{img}</div>'
        # no poster: never a flat colour field — night, the velvet glow, and the film's typographic tile
        return (f'<div class="bd noimg" style="--pc:{pc}" aria-hidden="true"><span class="pst bd-t">'
                f'<span class="pst-t"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</span></span></div>')
