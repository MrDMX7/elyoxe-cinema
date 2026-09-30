"""A cinema-format dictionary (301, r4-home, owner idea 2026-09-30): /formats/ (+ /en/formats/) «وش الفرق؟» —
IMAX, 4DX, MX4D, ScreenX, Dolby Cinema/Atmos, the luxury-seating tiers (VIP/Platinum/Gold/Theatre/Suites) and
kids halls, each in one or two plain lines, which UAE chains have it (from halls.yaml, the same file /halls/
reads), the price range our own price data shows today, and which kind of film it suits. `site_kit.FORMAT_SLUGS`
is the single source of truth for the anchor a hall label on the ticket and the compact time buttons links to
(Kit.hall_html(link=True), kit/ticket.py and kit/sched.py's times_compact) — this page is built from that same
table, so a new key added there gets a section here for free (an id with no matching FORMAT_DEFS entry is an
error at build time, not a silent gap).

A luxury-seating tier and a kids hall have no third-party manufacturer behind them (a chain's own naming), so
their entries cite the chain's own halls.yaml `source` field (already researched, dated 2026-09-25) instead of
inventing a manufacturer claim; IMAX/4DX/MX4D/ScreenX/Dolby cite the format owner's own page (researched
2026-09-30). Every citation sits in one small-text block at the page's bottom (owner rule: sources, not scattered
mid-copy)."""
from site_kit import CITY, FORMAT_SLUGS, L, NavItem, P, Page, Pages, Plugin, esc, human_date, money, num

CSS = ("formats",)   # src/css/formats.css, appended to /assets/cinema.css
TITLE = ("وش الفرق؟", "What's the difference?")
HUB_DESC = ("IMAX، 4DX، MX4D، ScreenX، Dolby، القاعات الفاخرة وقاعات الأطفال — شو فيها فعلاً، مين عنده، وتستاهل لأي فيلم.",
            "IMAX, 4DX, MX4D, ScreenX, Dolby, the luxury tiers and kids halls — what's actually inside, who has it, and which films they suit.")

# (slug, name_ar, name_en, hall keys it groups, what[ar,en], best-for[ar,en], source | None)
# — None means the entry cites the matched halls.yaml chain sources instead (no single manufacturer behind it)
FORMAT_DEFS = [
    ("imax", "آيماكس (IMAX)", "IMAX", ("IMAX",),
     ("شاشة IMAX أطول من العادية وتغطي نظرك أكثر، وبعض الأفلام تُصوَّر لها خصيصاً فتطلع لك صورة أكبر فوق وتحت. النسخة "
      "الأحدث «آيماكس ليزر» فيها عرض ليزر بدقة أعلى وصوت من 12 قناة — نوفو تشغّلها في سينما آي إم جي وورلدز بدبي.",
      "A taller IMAX screen that fills more of your view; some films are shot specifically for it, showing more of "
      "the frame. The newer «IMAX with Laser» adds sharper laser projection and 12-channel sound — Novo runs it at "
      "IMG Worlds Cinemas in Dubai."),
     ("يستاهل لأفلام الأكشن والخيال العلمي والمغامرة اللي تعتمد على المشهد الكبير.",
      "Worth it for action, sci-fi and adventure films built around the big picture."),
     ("IMAX", "https://www.imax.com/")),
    ("4dx", "فور دي إكس (4DX)", "4DX", ("4DX",),
     ("كراسي تتحرك وياك فوق وتحت ويمين ويسار، مع هوا وماي ودخان وأحياناً ريحة — أكثر من 20 مؤثر ممكن يشتغلون سوا.",
      "Seats that move with the film in three directions, plus wind, water, fog and sometimes scent — over 20 "
      "effects can run together."),
     ("حلو لأفلام الأكشن والإثارة السريعة، ومب مريح لفيلم طويل هادي.",
      "Fun for fast action and thrillers; not comfortable for a long, quiet film."),
     ("CJ 4DPLEX", "https://cj4dplex.com/4dx")),
    ("mx4d", "إم إكس فور دي (MX4D)", "MX4D", ("MX4D",),
     ("نفس فكرة الكراسي المتحركة والمؤثرات (هوا وماي وثلج وضربات خفيفة بالكرسي)، بس من شركة MediaMation الأمريكية "
      "بدل CJ 4DPLEX صاحبة الـ4DX.",
      "The same moving-seat idea — wind, water, snow and small seat jabs — from the American maker MediaMation "
      "instead of CJ 4DPLEX, the company behind 4DX."),
     ("نفس حكم الـ4DX: يستاهل لفيلم أكشن سريع، مب لفيلم هادي.",
      "The same call as 4DX: a fast action film, not a quiet one."),
     ("MediaMation", "https://www.mediamation.com/mx4d-flying-efx-theatre/")),
    ("screenx", "سكرين إكس (ScreenX)", "ScreenX", ("SCREENX",),
     ("الصورة تمتد من الشاشة الوسط على جدارين جنب بزاوية 270 درجة — بس في مشاهد مختارة صوّرها المخرج لها خصيصاً، "
      "مب الفيلم كامل.",
      "The picture spills from the centre screen onto both side walls, a 270-degree view — only in scenes the "
      "director shot for it, not the whole film."),
     ("يستاهل لأفلام فيها مشاهد أكشن أو طبيعة واسعة اتصوّرت خصيصاً له.",
      "Worth it for action or wide nature scenes shot specifically for the format."),
     ("CJ 4DPLEX", "https://cj4dplex.com/")),
    ("dolby", "دولبي سينما وأتموس (Dolby Cinema / Atmos)", "Dolby Cinema / Atmos", ("DOLBY", "ATMOS"),
     ("صورة Dolby Vision بتباين وألوان أوضح، وصوت Dolby Atmos ينزل عليك من فوق ومن حواليك، مب بس من قدام.",
      "Dolby Vision picture with sharper contrast and colour, and Dolby Atmos sound coming from above and around "
      "you, not just from the front."),
     ("يستاهل لأفلام فيها موسيقى وصوت قوي — أكشن، وأفلام كونسيرت.",
      "Worth it for films built on sound — action and concert films."),
     ("Dolby", "https://www.dolby.com/movies-tv/cinema/")),
    ("luxury", "القاعات الفاخرة (VIP، بلاتينيوم، جولد، ثياتر، سويتس)", "Luxury seating (VIP / Platinum / Gold / Theatre / Suites)",
     ("VIP", "GOLD", "THEATRE", "SUITES", "PLATINUM"),
     ("مب تقنية عرض — كراسي جلد أوسع تنسدح بالكامل، وأكل وشرب يوصلك كرسيك. كل سينما تسمّيها باسم مختلف: VIP عند "
      "سيني رويال، بلاتينيوم عند ريل وروكسي، جولد وثياتر عند فوكس، سويتس عند ستار.",
      "Not a projection technology — wider, fully reclining leather seats and food to your seat. Every chain "
      "names it differently: VIP at Cine Royal, Platinum at Reel and Roxy, GOLD and THEATRE at VOX, Suites at "
      "Star."),
     ("يستاهل لأي فيلم تبيه مرتاح لين النهاية، خصوصاً لو طويل — مب مرتبط بنوع فيلم معيّن.",
      "Worth it for any film you want to watch in comfort, especially a long one — not tied to a particular kind "
      "of film."),
     None),
    ("kids", "قاعات الأطفال (Kids)", "Kids halls", ("KIDS",),
     ("قاعة مخصصة للعيال، كراسي وأحياناً أرضية ملونة، وما يعرض فيها إلا أفلام أنيميشن وعائلية.",
      "A hall built for children — colourful seating, sometimes a play floor — showing only animation and family "
      "films."),
     ("لأفلام الأطفال والعائلة بس.", "For children's and family films only."),
     None),
]
assert {d[0] for d in FORMAT_DEFS} == set(FORMAT_SLUGS.values()), "FORMAT_DEFS and site_kit.FORMAT_SLUGS must name the same entries"


def register(site):
    fp = Formats(site)
    return Plugin(pages=[Page(("formats",), lang, lambda lang=lang: fp.build(lang)) for lang in ("ar", "en")],
                  nav=[NavItem("formats", href=lambda lang: P(lang, "formats"), label=TITLE)])


class Formats(Pages):
    def matches(self, keys):
        """[(chain, halls.yaml entry)] for the chains that declare a hall in `keys`, chain order as the file has
        them (vox first: the chain most of these formats started at)."""
        out = []
        for chain, c in self.h.y.items():
            for e in c.get("halls", []):
                if e.get("key") in keys: out.append((chain, e))
        return out

    def price_range(self, keys):
        """(low, high, n cinemas) from today's live prices at every show in any of `keys`, or None with too
        little behind it (the same floor pages/questions.py uses: honesty over a thin sample)."""
        ps = [p["aed"] for s in self.shows if self.hkey(s) in keys for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
        cids = {s["cinema"] for s in self.shows if self.hkey(s) in keys}
        if len(ps) < 3: return None
        return min(ps), max(ps), len(cids)

    def cities_for(self, keys):
        return sorted({self.cinemas[s["cinema"]]["city"] for s in self.shows if self.hkey(s) in keys})

    def entry(self, lang, slug, name_ar, name_en, keys, what, best, src, sources):
        ar = lang == "ar"
        name = name_ar if ar else name_en
        rows = self.matches(keys)
        chains = "، ".join(dict.fromkeys(self.h.chain_name(ch, lang) for ch, _ in rows)) if ar else \
            ", ".join(dict.fromkeys(self.h.chain_name(ch, lang) for ch, _ in rows))
        cities = self.cities_for(keys)
        cn = ("، " if ar else ", ").join(L(CITY[c], lang) for c in cities)
        have = ""
        if chains:
            have = (f'<p class="have">{"عندهم: " if ar else "At: "}{esc(chains)}'
                    + (f' — {esc(cn)}' if cn else "") + '</p>')
        elif cn:
            have = f'<p class="have">{esc(cn)}</p>'
        pr = self.price_range(keys)
        price = ""
        if pr:
            lo, hi, n = pr
            day = human_date(self.today, lang)
            rng = num(money(lo)) + (f' – {num(money(hi))}' if hi != lo else "")
            price = (f'<p class="rng">{("نطاق السعر اليوم (" if ar else "Today’s price range (") + esc(day) + "): "}'
                     f'{rng} <small>{esc("درهم" if ar else "AED")}</small>'
                     f' <small class="dim">({num(n)} {esc("سينما" if ar else ("cinema" if n == 1 else "cinemas"))})</small></p>')
        if src is None:
            # a chain's own naming, no manufacturer: cite the matched halls.yaml entries' own sources instead
            for ch, e in rows:
                if e.get("source"): sources.setdefault(e["source"], self.h.chain_name(ch, lang))
        else:
            sources.setdefault(src[1], src[0])
        return (f'<section class="wrap fentry" id="{slug}"><h2>{esc(name)}</h2>'
                f'<p class="what">{esc(what[0 if ar else 1])}</p>{have}{price}'
                f'<p class="best"><b>{"يستاهل لأي نوع فيلم؟" if ar else "Worth it for which film?"}</b> {esc(best[0 if ar else 1])}</p>'
                f'</section>')

    def build(self, lang):
        ar = lang == "ar"
        sources = {}   # url -> label, in citation order (dict keeps insertion order)
        body = (f'<section class="head wrap">{self.crumbs(lang, (L(TITLE, lang), None))}<h1 class="pt">{esc(L(TITLE, lang))}</h1>'
                f'<p class="lead">{esc(L(HUB_DESC, lang))}</p></section>')
        body += '<nav class="fjump wrap" aria-label="' + ("روابط سريعة" if ar else "Quick links") + '">'
        body += "".join(f'<a href="#{slug}">{esc(name_ar if ar else name_en)}</a>' for slug, name_ar, name_en, *_ in FORMAT_DEFS)
        body += '</nav>'
        for slug, name_ar, name_en, keys, what, best, src in FORMAT_DEFS:
            body += self.entry(lang, slug, name_ar, name_en, keys, what, best, src, sources)
        if sources:
            src_list = "، ".join(f'<a href="{esc(u)}" rel="noopener" target="_blank">{esc(n)}</a>' for u, n in sources.items()) if ar else \
                ", ".join(f'<a href="{esc(u)}" rel="noopener" target="_blank">{esc(n)}</a>' for u, n in sources.items())
            body += (f'<section class="wrap fsrc"><p class="hint small">{"المصادر: " if ar else "Sources: "}{src_list}. '
                     f'{"الأسعار من بيانات عروضنا اليوم، قبل خصم أي بطاقة." if ar else "Prices from today’s show data, before any card discount."}</p></section>')
        title = ("قاموس قاعات السينما في الإمارات — وش الفرق بين IMAX و4DX ودولبي والقاعات الفاخرة؟" if ar
                 else "UAE cinema formats explained — IMAX vs 4DX vs Dolby vs luxury seating")
        desc = L(HUB_DESC, lang)
        graph = [self.breadcrumb_ld(lang, (L(TITLE, lang), P(lang, "formats")))]
        return {"title": title, "desc": desc, "body": body, "kind": "formats", "nav": "formats", "graph": graph}
