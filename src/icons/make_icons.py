"""The PWA icons from the wordmark: «سينما» in Markazi Text 700, marquee gold on night, the velvet glow
behind it (the one glow the identity allows). Run once when the wordmark changes; the PNGs are committed.

  python src/icons/make_icons.py   ->  src/icons/icon-192.png  icon-512.png  maskable-512.png

Pillow on Windows has no libraqm, so the word is shaped with arabic-reshaper + python-bidi first (the
fonts' own OFL woff2 subset carries the presentation forms)."""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "fonts", "markazi-700-arabic.woff2")
NIGHT, VELVET, GOLD = (15, 11, 12), (122, 22, 38), (226, 182, 89)
WORD = "سينما"


def shaped(word):
    if features.check("raqm"):
        return word, {"direction": "rtl", "language": "ar"}
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(word)), {}


def icon(size, fill):
    """`fill` = the share of the width the word may take (maskable icons keep it inside the safe circle)."""
    big = size * 4
    im = Image.new("RGB", (big, big), NIGHT)
    glow = Image.new("RGB", (big, big), NIGHT)
    ImageDraw.Draw(glow).ellipse([big * .12, big * .2, big * .88, big * .8], fill=VELVET)
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(big * .14)), .75)
    text, kw = shaped(WORD)
    d = ImageDraw.Draw(im)
    pt = big
    while True:
        f = ImageFont.truetype(FONT, pt)
        l, t, r, b = d.textbbox((0, 0), text, font=f, **kw)
        if r - l <= big * fill: break
        pt = int(pt * .95)
    d.text(((big - (r - l)) / 2 - l, (big - (b - t)) / 2 - t), text, font=f, fill=GOLD, **kw)
    return im.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    icon(192, .78).save(os.path.join(HERE, "icon-192.png"), optimize=True)
    icon(512, .78).save(os.path.join(HERE, "icon-512.png"), optimize=True)
    icon(512, .6).save(os.path.join(HERE, "maskable-512.png"), optimize=True)
    print("icons written to", HERE)
