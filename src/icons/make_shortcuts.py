"""The home-screen shortcut icons (roadmap 138, src/manifest.webmanifest «shortcuts»), in the app icon's
identity: night, the velvet glow behind, one marquee-gold line glyph. Drawn, not lettered, so they read at 48 px
and the same in both languages; the glyph stays inside the middle 60 % (Android masks shortcuts to a circle).

  python src/icons/make_shortcuts.py   ->  src/icons/sc-now.png  sc-coming.png   (192 x 192)

«قائمتي» (a bookmark, /#mine) was dropped with its shortcut: no list existed behind it. When one does (/me/),
its glyph is a bookmark ribbon drawn the same way.

Run once when the identity changes; the PNGs are committed (build.py copies every src/icons/*.png)."""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
NIGHT, VELVET, GOLD = (15, 11, 12), (122, 22, 38), (226, 182, 89)
SIZE, K = 192, 4                     # drawn at 4x, then scaled down (smooth edges without an anti-aliasing API)


def base():
    big = SIZE * K
    im = Image.new("RGB", (big, big), NIGHT)
    glow = Image.new("RGB", (big, big), NIGHT)
    ImageDraw.Draw(glow).ellipse([big * .16, big * .16, big * .84, big * .84], fill=VELVET)
    return Image.blend(im, glow.filter(ImageFilter.GaussianBlur(big * .12)), .7)


def now(d, c, r, w):
    """«الحين»: a clock face, the hands at a few minutes past."""
    d.ellipse([c - r, c - r, c + r, c + r], outline=GOLD, width=w)
    for ang, ln in ((-90 + 30 * 2, .5), (-90, .72)):      # hour hand near 2, minute hand at 12
        a = math.radians(ang)
        d.line([c, c, c + r * ln * math.cos(a), c + r * ln * math.sin(a)], fill=GOLD, width=w)
    d.ellipse([c - w, c - w, c + w, c + w], fill=GOLD)


def coming(d, c, r, w):
    """«نازل الخميس»: a calendar leaf, one day marked."""
    x0, y0, x1, y1 = c - r, c - r * .85, c + r, c + r
    d.rectangle([x0, y0, x1, y1], outline=GOLD, width=w)
    d.rectangle([x0, y0, x1, y0 + r * .42], fill=GOLD)
    for x in (c - r * .5, c + r * .5):
        d.line([x, y0 - r * .25, x, y0 + r * .12], fill=GOLD, width=w)
    s = r * .3
    d.rectangle([c + r * .15, c + r * .3, c + r * .15 + s, c + r * .3 + s], fill=GOLD)


def icon(draw):
    im = base()
    big = SIZE * K
    draw(ImageDraw.Draw(im), big / 2, big * .27, int(big * .045))
    return im.resize((SIZE, SIZE), Image.LANCZOS)


if __name__ == "__main__":
    for name, fn in (("now", now), ("coming", coming)):
        icon(fn).save(os.path.join(HERE, f"sc-{name}.png"), optimize=True)
    print("shortcut icons written to", HERE)
