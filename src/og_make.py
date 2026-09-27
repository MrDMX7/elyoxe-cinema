"""Make src/og-ar.png and src/og-en.png (1200x630): the «سينما» wordmark in Markazi on night with the velvet glow.
Pillow on Windows has no raqm, so Arabic is shaped with arabic-reshaper + python-bidi. Fonts: the site's own woff2
files, decompressed to TTF in memory via fontTools (woff2 needs brotli)."""
import io
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features
import arabic_reshaper
from bidi.algorithm import get_display
from fontTools.ttLib import TTFont

SRC = r"C:/Users/requi/workspace/saas/cinema/src"
NIGHT, VELVET, GOLD, SCREEN, SEAT = (15, 11, 12), (122, 22, 38), (226, 182, 89), (241, 234, 224), (168, 156, 142)


def font(name, size):
    t = TTFont(f"{SRC}/fonts/{name}")
    t.flavor = None
    b = io.BytesIO(); t.save(b); b.seek(0)
    return ImageFont.truetype(b, size)


def markazi(size):
    """The full Markazi TTF (the site's woff2 subset has no Arabic presentation forms, which the reshaper emits)."""
    f = ImageFont.truetype("markazi.ttf", size)
    try: f.set_variation_by_axes([700])
    except Exception: pass
    return f


RAQM = features.check("raqm")


def ar(s):
    """With raqm (this Pillow has it) the text is shaped natively; without it, reshaper + bidi."""
    return s if RAQM else get_display(arabic_reshaper.reshape(s))


def card(lang):
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), NIGHT)
    glow = Image.new("RGB", (W, H), NIGHT)
    g = ImageDraw.Draw(glow)
    cx, cy = (820, 250) if lang == "ar" else (380, 250)
    for r in range(420, 0, -6):
        k = (1 - r / 420) ** 1.6
        c = tuple(int(NIGHT[i] + (VELVET[i] - NIGHT[i]) * k * .75) for i in range(3))
        g.ellipse((cx - r * 1.4, cy - r, cx + r * 1.4, cy + r), fill=c)
    im = glow.filter(ImageFilter.GaussianBlur(40))
    d = ImageDraw.Draw(im)
    if lang == "ar":
        mark = font("markazi-700-arabic.woff2", 230) if RAQM else markazi(230)
        body = font("readex-arabic.woff2", 44) if RAQM else markazi(54)
        d.text((W - 90, 250), ar("سينما"), font=mark, fill=GOLD, anchor="rm", direction="rtl" if RAQM else None)
        d.text((W - 92, 440), ar("كل سينما في الإمارات، والسعر بعد خصم بطاقتك"), font=body, fill=SCREEN, anchor="rm", direction="rtl" if RAQM else None)
        d.text((W - 92, 510), "cinema.elyoxe.com", font=font("readex-latin.woff2", 30), fill=SEAT, anchor="rm")
    else:
        mark = font("readex-latin.woff2", 170)
        body = font("readex-latin.woff2", 40)
        d.text((90, 250), "Cinema", font=mark, fill=GOLD, anchor="lm")
        d.text((92, 440), "Every UAE cinema, priced after your card", font=body, fill=SCREEN, anchor="lm")
        d.text((92, 510), "cinema.elyoxe.com", font=font("readex-latin.woff2", 30), fill=SEAT, anchor="lm")
    im.save(f"{SRC}/og-{lang}.png", optimize=True)


for lang in ("ar", "en"):
    card(lang)
print("ok")
