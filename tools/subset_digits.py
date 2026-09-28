"""Make the two tiny Markazi Text faces the stylesheet declares (W1-P2, MASTER-PLAN §1.4), once, from the site's own
OFL woff2 files, and commit what it writes:

  src/fonts/markazi-700-digits.woff2   0–9 and the colon (U+0030–003A) from markazi-700-latin.woff2: the only Markazi face
                                       that may draw a numeral, at display size (a rank numeral, the Thursday date, the
                                       leader). ≤ 3 KB; a page fetches it only when it sets a numeral in Markazi, so the
                                       15.7 KB Latin face is never pulled onto a page by a digit.
  src/fonts/markazi-700-mark.woff2     the five letters of «سينما» (ا س م ن ي) from markazi-700-arabic.woff2, with the
                                       joining forms: the Arabic wordmark on /en/ (owner default D7) without the 23 KB
                                       Arabic face on every English page.

    python tools/subset_digits.py [--check]
--check writes nothing: it makes both in memory and exits 1 when a committed file draws other characters or another
set of glyphs than it would make, or is over 3 KB (tests/test_w1_p2.py runs it). It compares what the files hold, not
their bytes: another fontTools or brotli (the Fold's, CI's) may pack the same font a few bytes differently.

Kerning only (no ligatures, no fraction or numerator forms: they would pull in glyphs no page draws); hinting kept, as
the source files carry it. The OFL allows subsetting (Markazi Text declares no Reserved Font Name); the licence stays
beside the files (src/fonts/OFL-MarkaziText.txt)."""
import io, os, sys

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "src", "fonts")
MAKE = {
    "markazi-700-digits.woff2": ("markazi-700-latin.woff2", [0x30 + i for i in range(11)], ["kern"]),
    "markazi-700-mark.woff2": ("markazi-700-arabic.woff2", [ord(c) for c in "سينما"], ["ccmp", "init", "medi", "fina", "rlig", "kern", "mark", "mkmk"]),
}
LIMIT = 3000   # bytes, the plan's cap for the digits face (§5.2 W1-P2); the mark's own is the same


def make(src, unicodes, features):
    font = TTFont(os.path.join(FONTS, src))
    o = subset.Options()
    o.flavor = "woff2"
    o.layout_features = features
    o.name_IDs = [0, 1, 2, 3, 4, 5, 6]
    o.recalc_timestamp = False          # the output depends on the source only: the same bytes every run
    s = subset.Subsetter(o)
    s.populate(unicodes=unicodes)
    s.subset(font)
    b = io.BytesIO()
    font.flavor = "woff2"
    font.save(b)
    return b.getvalue()


def held(data):
    """What a font holds: its characters and its glyph count (joining forms and marks included)."""
    f = TTFont(io.BytesIO(data))
    return sorted(f.getBestCmap()), len(f.getGlyphOrder())


def main(argv):
    check = "--check" in argv
    bad = []
    for name, (src, unicodes, features) in MAKE.items():
        data = make(src, unicodes, features)
        path = os.path.join(FONTS, name)
        if not check and len(data) > LIMIT: bad.append(f"{name}: {len(data)} B, over {LIMIT}")
        if check:
            have = open(path, "rb").read() if os.path.exists(path) else b""
            if len(have) > LIMIT: bad.append(f"{name}: committed {len(have)} B, over {LIMIT}")
            if not have or held(have) != held(data): bad.append(f"{name}: the committed file holds other glyphs than tools/subset_digits.py makes")
        else:
            with open(path, "wb") as f: f.write(data)
            print(f"{name}: {len(data)} B from {src} ({len(unicodes)} characters)")
    for b in bad: print(b, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
