"""steps/og.py — «سينما» share images: one 1200x630 PNG per film, ar + en (Task A3, roadmap #206).

For a showing film: poster at the reading-start side (right for ar, left for en), the film's title,
a price line — «من {price} درهم الليلة في {city}» (ar) / "From AED {price} tonight in {city}" (en)
— and the date, plus the «سينما»/"Cinema" wordmark. Every number drawn is read from `data`, never
invented: `price` is the lowest confirmed ticket price (no card applied) across today's shows for
that film; `city` is whichever UAE city has the most of today's shows for it (ties: CITY_ORDER,
Dubai first). An archived film gets the variant without a price/city line (poster, title, wordmark
only) — its inputs hold still, so it is never re-rendered once written.

Cache: data/og/ (gitignored, mirrors data/posters/) holds every PNG this step has rendered, named
"<fid>-<lang>-<hash>.png" where <hash> is a sha1 of exactly what was drawn (title, price, city,
today's date, the poster file's size+mtime) — unchanged inputs are never re-rendered; a build just
reuses the file already on disk. data["films"][fid]["og"] = {"ar": "<name>.png", "en": "<name>.png"}
for every film this step could render, read by pages/og.py (a build-time plugin) which copies
whichever files are still current into out/og/ and points that film's og:image/twitter:image there
(both read the same tag: docs/PLUGINS.md's phase-1 page has no separate twitter:image, and Twitter
falls back to og:image under summary_large_image).

A film with no local poster file yet (posters.py has not mirrored it), or when Pillow/the shaping
libraries are unavailable, is simply skipped for this run — never a crash, never a broken image; its
film page keeps the site-wide default `assets/og-<lang>.png` until a later run can render it.

run(data, ctx) -> {"rendered": n, "skipped": n, "cities": {fid: city_slug, ...}}
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import site_kit as sk  # noqa: E402  (CITY names, human_date — plain strings, no HTML)

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
    """The lowest confirmed no-card price and the city with the most of today's shows, for one film."""
    todays = [s for s in shows if s.get("film") == fid and s.get("date") == today]
    if not todays:
        return None, None
    prices = [p["aed"] for s in todays for p in (s.get("prices") or []) if (p.get("aed") or 0) > 0]
    if not prices:
        return None, None
    by_city: dict[str, int] = {}
    for s in todays:
        city = (cinemas.get(s.get("cinema")) or {}).get("city")
        if city:
            by_city[city] = by_city.get(city, 0) + 1
    if not by_city:
        return None, None
    best = max(by_city.values())
    city = next((c for c in CITY_ORDER if by_city.get(c) == best), max(by_city, key=lambda c: by_city[c]))
    price = int(min(prices)) if float(min(prices)).is_integer() else round(min(prices), 2)
    return price, city


def _poster_path(data_dir, url):
    """The local mirror of a poster URL (posters.py: data/posters/<basename>), else None."""
    if not url:
        return None
    p = Path(data_dir or (ROOT / "data")) / "posters" / os.path.basename(str(url))
    return p if p.is_file() else None


def _hash(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _card(lang, title, price, city_label, day, poster_path, wordmark):
    """Build one 1200x630 PNG (bytes). Raises on any Pillow/font failure — the caller decides what a
    failure means (skip that film/lang, never abort the whole step)."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, features
    import arabic_reshaper
    from bidi.algorithm import get_display
    from fontTools.ttLib import TTFont

    fonts_dir = ROOT / "src" / "fonts"
    raqm = features.check("raqm")

    def font(name, size):
        t = TTFont(str(fonts_dir / name)); t.flavor = None
        import io
        b = io.BytesIO(); t.save(b); b.seek(0)
        return ImageFont.truetype(b, size)

    def shaped(s):
        # with raqm the subset font shapes correctly on its own; without it, reshaper+bidi (docs/PLUGINS.md
        # notes the subset has no presentation forms — acceptable degradation for a background share image,
        # never a crash: src/og_make.py accepts the same trade-off)
        return s if (lang != "ar" or raqm) else get_display(arabic_reshaper.reshape(s))

    is_ar = lang == "ar"
    poster_side_right = is_ar  # reading-start side: right for ar, left for en
    im = Image.new("RGB", (W, H), NIGHT)
    glow = Image.new("RGB", (W, H), NIGHT)
    g = ImageDraw.Draw(glow)
    cx = (W - POSTER_W - 260) if poster_side_right else (POSTER_W + 260)
    for r in range(380, 0, -6):
        k = (1 - r / 380) ** 1.6
        c = tuple(int(NIGHT[i] + (VELVET[i] - NIGHT[i]) * k * .7) for i in range(3))
        g.ellipse((cx - r * 1.3, 250 - r, cx + r * 1.3, 250 + r), fill=c)
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(50)), 1.0)
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

    text_right = not poster_side_right  # the text block sits on the side opposite the poster
    tx = W - 90 if text_right else (POSTER_W + 90 if poster_path else 90)
    anchor = "rm" if text_right else "lm"

    mark = font("markazi-700-arabic.woff2" if is_ar else "readex-latin.woff2", 150 if is_ar else 120)
    title_f = font("markazi-700-arabic.woff2" if is_ar else "readex-latin.woff2", 74 if is_ar else 62)
    body_f = font("readex-arabic.woff2" if is_ar else "readex-latin.woff2", 36)
    small_f = font("readex-latin.woff2", 28)

    d.text((tx, 130), shaped(wordmark), font=mark, fill=GOLD, anchor=anchor, direction="rtl" if (is_ar and raqm) else None)
    d.text((tx, 300), shaped(title[:60]), font=title_f, fill=SCREEN, anchor=anchor, direction="rtl" if (is_ar and raqm) else None)
    y = 400
    if price is not None and city_label:
        line = f"من {price} درهم الليلة في {city_label}" if is_ar else f"From AED {price} tonight in {city_label}"
        d.text((tx, y), shaped(line), font=body_f, fill=GOLD, anchor=anchor, direction="rtl" if (is_ar and raqm) else None)
        y += 55
    d.text((tx, y), day, font=small_f, fill=SEAT, anchor=anchor)

    import io as _io
    buf = _io.BytesIO()
    im.save(buf, "PNG", optimize=True)
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
            title = f.get("title_ar") or f.get("title") if lang == "ar" else f.get("title") or f.get("title_ar")
            title = str(title or fid)
            wordmark = "سينما" if lang == "ar" else "Cinema"
            day = sk.human_date(today, lang)
            price_here = None if archived else price
            city_here = None if archived else (city_label[0] if lang == "ar" and city_label else
                                                 city_label[1] if city_label else None)
            h = _hash(fid, lang, "archived" if archived else "live", title, price_here, city_here,
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

    # prune yesterday's renders for films whose price/city/date changed today (never let data/og/ grow forever)
    for p in out_dir.glob("*.png"):
        if p.name not in keep:
            try:
                p.unlink()
            except OSError:
                pass

    return {"rendered": rendered, "skipped": skipped, "cities": cities}
