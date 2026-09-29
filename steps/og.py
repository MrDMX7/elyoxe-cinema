"""steps/og.py — «سينما» share images: one 1200x630 PNG per film, ar + en (Task A3, roadmap #206).

For a showing film: poster at the reading-start side (right for ar, left for en), the film's title,
a price line — «من {price} درهم الليلة في {city}» (ar) / "From AED {price} tonight in {city}" (en)
— and the date, plus the «سينما»/"Cinema" wordmark. Every number drawn is read from `data`, never
invented, AND the two numbers on the price line describe the SAME place: `city` is picked first
(whichever UAE city has the most of today's shows for the film, ties: CITY_ORDER, Dubai first), then
`price` is the lowest confirmed no-card price among THAT city's shows only — never the globally
cheapest price with a city named that doesn't actually have it (review fix round 1: a 3-show
Dubai-100/90 + Sharjah-20 case used to render "من 20 درهم الليلة في دبي", a price Dubai never had).
A city with no priced show today drops the price line entirely rather than ever naming an
unavailable price. An archived film gets the variant without a price/city line (poster, title,
wordmark only) — its inputs hold still, so it is never re-rendered once written.

Fonts: every subset woff2 under src/fonts/ covers ONE script only — Arabic glyphs XOR digits/Latin
(fontTools cmap check; confirmed neither `*-arabic.woff2` has any digit, nor `*-latin.woff2` any
Arabic codepoint). A line that mixes them (the Arabic price/date lines always do: Western numerals
inside Arabic text) is split into same-script runs and each run drawn with its own font, in logical
order (`_runs`/`draw_line`) — review fix round 1 for the missing-glyph boxes a single-font draw used
to produce on every Arabic image with a price or a date.

Cache: data/og/ (gitignored, mirrors data/posters/) holds every PNG this step has rendered, named
"<fid>-<lang>-<hash>.png" where <hash> is a sha1 of exactly what was drawn (RENDER_VERSION, title,
price, city, today's date, the poster file's size+mtime) — unchanged inputs are never re-rendered; a
build just reuses the file already on disk. RENDER_VERSION is bumped whenever `_card()`'s own output
changes independently of the data (as in this fix round), so a stale pre-fix render is never reused.
data["films"][fid]["og"] = {"ar": "<name>.png", "en": "<name>.png"} for every film this step could
render, read by pages/og.py (a build-time plugin) which copies whichever files are still current into
out/og/ and points that film's og:image/twitter:image there (both read the same tag: docs/PLUGINS.md's
phase-1 page has no separate twitter:image, and Twitter falls back to og:image under
summary_large_image).

A film with no local poster file yet (posters.py has not mirrored it), or when Pillow/the shaping
libraries are unavailable, is simply skipped for this run — never a crash, never a broken image; its
film page keeps the site-wide default `assets/og-<lang>.png` until a later run can render it.

run(data, ctx) -> {"rendered": n, "skipped": n, "cities": {fid: city_slug, ...}}

Story images (r3-seo, roadmap #256/#258): the same pipeline also renders one 1080x1920 PNG per showing film
per day — "<fid>-<lang>-story-<hash>.png" in the same data/og/ cache, same prune pass, same skip-on-failure
rule — poster full-bleed top, title, and a price line «من {price} درهم» (ar) / "From AED {price}" (en), the
cheapest confirmed no-card price for the film ANYWHERE today (a Stories card names no city, so it is never
tied to one city's price the way the 1200x630 card is). An archived film gets no story card (nothing to sell
a ticket for) rather than a stale placeholder. data["films"][fid]["og_story"] = {"ar": "<name>.png", "en": ...},
read by pages/og.py the same way as ["og"]; pages/og.py links it from the film hero's share actions
(«ستوري إنستقرام»/"Instagram Story") as a plain download link — no separate share flow, no new button style.
"""
from __future__ import annotations

import functools
import hashlib
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import site_kit as sk  # noqa: E402  (CITY names, human_date — plain strings, no HTML)

RENDER_VERSION = "v3"  # v3: Arabic runs in visual RTL order, text clear of the poster, archived cards drop the date. bump whenever _card()'s output changes independently of the data (font-coverage fix)
W, H = 1200, 630
NIGHT, VELVET, GOLD, SCREEN, SEAT = (15, 11, 12), (122, 22, 38), (226, 182, 89), (241, 234, 224), (168, 156, 142)
CITY_ORDER = [c for c, _, _ in sk.CITIES]
POSTER_W = 420  # a 2:3 poster at full card height (630 * 2 / 3)


def _today(now_iso) -> str:
    try:
        return datetime.fromisoformat(now_iso).date().isoformat() if now_iso else date.today().isoformat()
    except ValueError:
        return date.today().isoformat()


def _cheapest_and_city(shows, cinemas, fid, today):
    """The city with the most of today's shows for this film, and — WITHIN THAT CITY ONLY — its
    cheapest confirmed no-card price. The two numbers must describe the same place: picking the
    global cheapest price across every city independently of which city gets named would let a
    price only available in city X get attached to city Y's name (review fix, roadmap #206). No
    priced show in the chosen city -> price is None and the caller drops the price line entirely,
    rather than ever naming a price the chosen city doesn't actually have."""
    todays = [s for s in shows if s.get("film") == fid and s.get("date") == today]
    if not todays:
        return None, None
    by_city: dict[str, list] = {}
    for s in todays:
        city = (cinemas.get(s.get("cinema")) or {}).get("city")
        if city:
            by_city.setdefault(city, []).append(s)
    if not by_city:
        return None, None
    best = max(len(v) for v in by_city.values())
    city = next((c for c in CITY_ORDER if len(by_city.get(c, ())) == best), max(by_city, key=lambda c: len(by_city[c])))
    prices = [p["aed"] for s in by_city[city] for p in (s.get("prices") or []) if (p.get("aed") or 0) > 0]
    if not prices:
        return None, city               # this city has no priced show today: no price line, ever
    price = int(min(prices)) if float(min(prices)).is_integer() else round(min(prices), 2)
    return price, city


SW, SH = 1080, 1920   # Instagram/TikTok Stories canvas


def _cheapest_today(shows, fid, today):
    """The lowest confirmed no-card price among ALL of today's shows for `fid`, any city (a Stories card
    names no city, unlike the 1200x630 card's `_cheapest_and_city` — so it is never tied to one city)."""
    prices = [p["aed"] for s in shows if s.get("film") == fid and s.get("date") == today
              for p in (s.get("prices") or []) if (p.get("aed") or 0) > 0]
    if not prices:
        return None
    return int(min(prices)) if float(min(prices)).is_integer() else round(min(prices), 2)


@functools.lru_cache(maxsize=1)
def _story_backdrop():
    """The night backdrop with a soft velvet glow low in the frame, behind the title/price block — drawn once
    (identical for every story card), same technique as `_backdrop` scaled to the Stories canvas."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.new("RGB", (SW, SH), NIGHT)
    glow = Image.new("RGB", (SW, SH), NIGHT)
    g = ImageDraw.Draw(glow)
    cy = int(SH * 0.72)
    for r in range(560, 0, -8):
        k = (1 - r / 560) ** 1.6
        c = tuple(int(NIGHT[i] + (VELVET[i] - NIGHT[i]) * k * .7) for i in range(3))
        g.ellipse((SW / 2 - r, cy - r * .6, SW / 2 + r, cy + r * .6), fill=c)
    return Image.blend(im, glow.filter(ImageFilter.GaussianBlur(60)), 1.0)


def _story_card(lang, title, price, wordmark, poster_path):
    """Build one 1080x1920 PNG (bytes): poster full-width top, title, «من {price} درهم» price line (dropped
    when there is none), wordmark at the foot. Same run-splitting/font rules as `_card` (draw_line below is
    the same routine, just centered instead of edge-anchored). Raises on any Pillow/font failure — the
    caller (run()) decides what that means (skip this film/lang, never abort the whole step)."""
    from PIL import Image, ImageDraw, features

    raqm = features.check("raqm")
    font = _font
    is_ar = lang == "ar"
    im = _story_backdrop().copy()
    d = ImageDraw.Draw(im)

    def draw_center(y, text, ar_font, other_font, fill):
        runs = _visual_runs(text, lang)
        fonts = [ar_font if ar else other_font for ar, _ in runs]
        widths = [f.getlength(t) for f, (_, t) in zip(fonts, runs)]
        cx = (SW - sum(widths)) / 2
        for f, (ar, t), w in zip(fonts, runs, widths):
            d.text((cx, y), t, font=f, fill=fill, anchor="lm", direction="rtl" if (ar and raqm) else None)
            cx += w

    poster_bottom = 0
    if poster_path:
        try:
            pst = Image.open(poster_path).convert("RGB")
            pw, ph = pst.size
            target_w = SW
            target_h = round(ph * target_w / pw)
            cap = round(SH * 0.66)   # never past two-thirds down: the title/price block needs the lower third
            pst = pst.resize((target_w, target_h))
            if target_h > cap:
                pst = pst.crop((0, 0, target_w, cap))
                target_h = cap
            im.paste(pst, (0, 0))
            d = ImageDraw.Draw(im)
            poster_bottom = target_h
        except Exception:
            pass  # a poster that fails to open still leaves the typographic card intact

    ar_name, other_name = ("markazi-700-arabic.woff2", "markazi-700-latin.woff2") if is_ar else (None, "readex-latin.woff2")
    size, avail = 88 if is_ar else 76, SW - 120

    def width(t, sz):
        return sum((font(ar_name, sz) if ar else font(other_name, sz)).getlength(r) for ar, r in _runs(t) if (ar_name or not ar))

    title = title[:60]
    while size > 48 and width(title, size) > avail:
        size -= 4
    while width(title, size) > avail and " " in title.strip():
        title = title.rstrip(". ").rsplit(" ", 1)[0] + "..."
    tt_ar = font(ar_name, size) if ar_name else None
    tt_other = font(other_name, size)

    y = max(poster_bottom + 110, round(SH * 0.72))
    draw_center(y, title, tt_ar, tt_other, SCREEN)
    y += size + 40
    if price is not None:
        line = f"من {price} درهم" if is_ar else f"From AED {price}"
        body_ar, body_lat = font("readex-arabic.woff2", 54), font("readex-latin.woff2", 54)
        draw_center(y, line, body_ar, body_lat, GOLD)
        y += 80
    wm_ar, wm_other = (font("markazi-700-arabic.woff2", 64), font("markazi-700-latin.woff2", 64)) if is_ar else (None, font("readex-latin.woff2", 52))
    draw_center(SH - 90, wordmark[:60], wm_ar, wm_other, SEAT)

    import io as _io
    buf = _io.BytesIO()
    im.save(buf, "PNG", compress_level=6)
    return buf.getvalue()


def _poster_path(data_dir, url):
    """The local mirror of a poster URL (posters.py: data/posters/<basename>), else None."""
    if not url:
        return None
    p = Path(data_dir or (ROOT / "data")) / "posters" / os.path.basename(str(url))
    return p if p.is_file() else None


def _hash(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _is_arabic_letter(ch: str) -> bool:
    return 0x0600 <= ord(ch) <= 0x06FF


def _runs(text: str):
    """Split `text` (logical order) into (is_arabic, substring) runs — every one of the site's own
    subset fonts covers EITHER Arabic letters OR digits/Latin/punctuation, never both (fontTools
    cmap check, review fix): a line mixing an Arabic word and a Western-numeral price/date needs a
    font switch at the script boundary, not a shared font neither subset actually has."""
    if not text:
        return []
    out, cur, buf = [], _is_arabic_letter(text[0]), [text[0]]
    for ch in text[1:]:
        ar = _is_arabic_letter(ch)
        if ar == cur:
            buf.append(ch)
        else:
            out.append((cur, "".join(buf))); cur, buf = ar, [ch]
    out.append((cur, "".join(buf)))
    return out


def _visual_runs(text: str, lang: str):
    """The runs of `text` in VISUAL order, left to right. Arabic is a right-to-left paragraph: its runs
    are laid right to left, so the first logical run («من») ends up rightmost and a Western-numeral run
    keeps its own left-to-right digits in its place (release fix: the v2 cards laid Arabic runs left to
    right, which read «دبي في الليلة درهم 46 من»). English stays one run."""
    if lang != "ar":
        return [(False, text)] if text else []
    out = []
    for ar, t in reversed(_runs(text)):
        core = t.strip()
        if not ar and core:   # an LTR run inside RTL: its logical leading space sits on its right, trailing on its left
            lead, trail = t[:len(t) - len(t.lstrip())], t[len(t.rstrip()):]
            t = trail + core + lead
        out.append((ar, t))
    return out


def _text_anchor(lang: str, has_poster: bool):
    """(x, right_anchored) for the text block, which sits opposite the poster. Arabic: poster on the
    right, text right-aligned against the poster's left edge (release fix: v2 left-anchored it at
    POSTER_W+90, so it ran across the poster). English: poster left, text left-aligned after it."""
    if lang == "ar":
        return (W - POSTER_W - 70 if has_poster else W - 90), True
    return (POSTER_W + 70 if has_poster else 90), False


@functools.lru_cache(maxsize=2)
def _backdrop(poster_side_right: bool):
    """The velvet glow behind the text: identical for every card on the same side, so drawn once."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.new("RGB", (W, H), NIGHT)
    glow = Image.new("RGB", (W, H), NIGHT)
    g = ImageDraw.Draw(glow)
    cx = (W - POSTER_W - 260) if poster_side_right else (POSTER_W + 260)
    for r in range(380, 0, -6):
        k = (1 - r / 380) ** 1.6
        c = tuple(int(NIGHT[i] + (VELVET[i] - NIGHT[i]) * k * .7) for i in range(3))
        g.ellipse((cx - r * 1.3, 250 - r, cx + r * 1.3, 250 + r), fill=c)
    return Image.blend(im, glow.filter(ImageFilter.GaussianBlur(50)), 1.0)


@functools.lru_cache(maxsize=None)
def _ttf_bytes(name: str) -> bytes:
    """src/fonts/<name> (woff2) decoded to plain TrueType, once per process (final review I1: this
    conversion was ~95% of a card's render time when it ran six times per card)."""
    import io
    from fontTools.ttLib import TTFont
    t = TTFont(str(ROOT / "src" / "fonts" / name)); t.flavor = None
    b = io.BytesIO(); t.save(b)
    return b.getvalue()


@functools.lru_cache(maxsize=None)
def _font(name: str, size: int):
    import io
    from PIL import ImageFont
    return ImageFont.truetype(io.BytesIO(_ttf_bytes(name)), size)


def _card(lang, title, price, city_label, day, poster_path, wordmark):
    """Build one 1200x630 PNG (bytes). Raises on any Pillow/font failure — the caller decides what a
    failure means (skip that film/lang, never abort the whole step)."""
    from PIL import Image, ImageDraw, features

    raqm = features.check("raqm")
    font = _font

    def draw_line(d, x, y, text, ar_font, other_font, fill, right_anchor):
        """One line, right- or left-anchored at x: each run drawn with the font that actually has its
        glyphs (ar_font for Arabic letters, other_font — always Latin, which covers digits — for
        everything else), laid out in visual order (`_visual_runs`: right to left for Arabic, so a digit
        run keeps its place in the sentence and its own left-to-right digits)."""
        runs = _visual_runs(text, lang)
        fonts = [ar_font if ar else other_font for ar, _ in runs]
        widths = [f.getlength(t) for f, (_, t) in zip(fonts, runs)]
        total = sum(widths)
        cx = (x - total) if right_anchor else x
        for f, (ar, t), w in zip(fonts, runs, widths):
            d.text((cx, y), t, font=f, fill=fill, anchor="lm", direction="rtl" if (ar and raqm) else None)
            cx += w

    is_ar = lang == "ar"
    poster_side_right = is_ar  # reading-start side: right for ar, left for en
    im = _backdrop(poster_side_right).copy()
    d = ImageDraw.Draw(im)

    if poster_path:
        try:
            pst = Image.open(poster_path).convert("RGB")
            pw, ph = pst.size
            target_h = H
            target_w = max(1, round(pw * target_h / ph))
            pst = pst.resize((target_w, target_h))
            if target_w > POSTER_W:
                left = target_w - POSTER_W if poster_side_right else 0
                pst = pst.crop((left, 0, left + POSTER_W, target_h))
            im.paste(pst, (W - pst.width, 0) if poster_side_right else (0, 0))
            d = ImageDraw.Draw(im)
        except Exception:
            pass  # a poster that fails to open still leaves the typographic side intact

    tx, text_right = _text_anchor(lang, bool(poster_path))

    # every subset font here covers ONE script only (fontTools cmap, review fix): the Arabic display/body
    # fonts have no digits, the Latin ones have no Arabic — so an Arabic line pairs its own font with a
    # same-family, same-size Latin companion for whatever draw_line's run-split hands it (a digit inside
    # a price or a date), never a single font asked to draw a glyph it doesn't have.
    body_ar, body_lat = font("readex-arabic.woff2", 36), font("readex-latin.woff2", 36)
    small_ar, small_lat = font("readex-arabic.woff2", 28), font("readex-latin.woff2", 28)
    # the display face differs by language (Markazi for ar, Readex for en — src/og_make.py's own split),
    # so wordmark/title need their own ar/other pair per language rather than reusing body/small's
    if is_ar:
        wm_ar, wm_other = font("markazi-700-arabic.woff2", 150), font("markazi-700-latin.woff2", 150)
        tt_ar, tt_other = font("markazi-700-arabic.woff2", 74), font("markazi-700-latin.woff2", 74)
    else:
        wm_ar, wm_other = None, font("readex-latin.woff2", 120)
        tt_ar, tt_other = None, font("readex-latin.woff2", 62)
    right = text_right

    draw_line(d, tx, 130, wordmark[:60], wm_ar, wm_other, GOLD, right)
    # the title fits the text column (release fix: a long English title ran off the card's edge): step the
    # size down to a floor, then cut on a word with "..." -- never past the poster or the card's edge
    avail = (tx - 60) if right else (W - 60 - tx)
    title = title[:60]
    ar_name, other_name = ("markazi-700-arabic.woff2", "markazi-700-latin.woff2") if is_ar else (None, "readex-latin.woff2")
    size = 74 if is_ar else 62

    def width(t, sz):
        return sum((font(ar_name, sz) if ar else font(other_name, sz)).getlength(r) for ar, r in _runs(t) if (ar_name or not ar))

    while size > 40 and width(title, size) > avail:
        size -= 4
    while width(title, size) > avail and " " in title.strip():
        title = title.rstrip(". ").rsplit(" ", 1)[0] + "..."
    tt_ar = font(ar_name, size) if ar_name else None
    tt_other = font(other_name, size)
    draw_line(d, tx, 300, title, tt_ar, tt_other, SCREEN, right)
    y = 400
    if price is not None and city_label:
        line = f"من {price} درهم الليلة في {city_label}" if is_ar else f"From AED {price} tonight in {city_label}"
        draw_line(d, tx, y, line, body_ar, body_lat, GOLD, right)
        y += 55
    draw_line(d, tx, y, day, small_ar, small_lat, SEAT, right)

    import io as _io
    buf = _io.BytesIO()
    im.save(buf, "PNG", compress_level=6)   # optimize=True cost 4.5x the encode time for 3% fewer bytes (I1)
    return buf.getvalue()


def run(data: dict, ctx: dict) -> dict | None:
    data_dir = ctx.get("data_dir") or (ROOT / "data")
    out_dir = Path(data_dir) / "og"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = _today(ctx.get("now"))
    films, cinemas, shows = data.get("films") or {}, data.get("cinemas") or {}, data.get("shows") or []
    rendered, skipped, cities, keep = 0, 0, {}, set()

    for fid, f in films.items():
        archived = f.get("status") == "archived"
        price = city = city_label = None
        if not archived:
            price, city = _cheapest_and_city(shows, cinemas, fid, today)
            city_label = sk.CITY.get(city, (city, city)) if city else None
        poster = _poster_path(data_dir, f.get("poster_2x") or f.get("poster"))
        if not poster:
            skipped += 1
            continue
        st = poster.stat()
        og_field = f.get("og") if isinstance(f.get("og"), dict) else {}
        for lang in ("ar", "en"):
            title = (f.get("title_ar") or f.get("title")) if lang == "ar" else (f.get("title") or f.get("title_ar"))
            title = str(title or fid)
            wordmark = "سينما" if lang == "ar" else "Cinema"
            day = "" if archived else sk.human_date(today, lang)   # an archived card never shows a date it would keep forever
            price_here = None if archived else price
            city_here = None if archived else (city_label[0] if lang == "ar" and city_label else
                                                 city_label[1] if city_label else None)
            h = _hash(RENDER_VERSION, fid, lang, "archived" if archived else "live", title, price_here, city_here,
                      day if not archived else "", st.st_size, st.st_mtime_ns)
            name = f"{fid}-{lang}-{h}.png"
            keep.add(name)
            dest = out_dir / name
            if dest.is_file():
                og_field[lang] = name
                continue
            try:
                png = _card(lang, title, price_here, city_here, day, poster, wordmark)
                dest.write_bytes(png)
                og_field[lang] = name
                rendered += 1
            except Exception:  # noqa: BLE001 - Pillow/font/shaping trouble: skip, never abort the step
                skipped += 1
        if og_field:
            f["og"] = og_field
            if city:
                cities[fid] = city

        # the Stories card: showing films only, one per film per day (its hash already folds in today's date)
        if not archived:
            story_price = _cheapest_today(shows, fid, today)
            og_story = f.get("og_story") if isinstance(f.get("og_story"), dict) else {}
            for lang in ("ar", "en"):
                title = str((f.get("title_ar") or f.get("title")) if lang == "ar" else (f.get("title") or f.get("title_ar")) or fid)
                wordmark = "سينما" if lang == "ar" else "Cinema"
                h = _hash(RENDER_VERSION, "story", fid, lang, title, story_price, today, st.st_size, st.st_mtime_ns)
                name = f"{fid}-{lang}-story-{h}.png"
                keep.add(name)
                dest = out_dir / name
                if dest.is_file():
                    og_story[lang] = name
                    continue
                try:
                    png = _story_card(lang, title, story_price, wordmark, poster)
                    dest.write_bytes(png)
                    og_story[lang] = name
                    rendered += 1
                except Exception:  # noqa: BLE001 - same rule as the 1200x630 card: skip, never abort the step
                    skipped += 1
            if og_story:
                f["og_story"] = og_story

    # prune yesterday's renders for films whose price/city/date changed today (never let data/og/ grow forever)
    for p in out_dir.glob("*.png"):
        if p.name not in keep:
            try:
                p.unlink()
            except OSError:
                pass

    return {"rendered": rendered, "skipped": skipped, "cities": cities}
