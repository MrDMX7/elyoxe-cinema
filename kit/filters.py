"""The filter sheet's content: the one question on top («مع منو» / «متى» / «وين»), then the genre, «لازم يخلص قبل»,
language, sort and the prayer switch (site_kit.Kit's filter helpers, moved out of the chrome by W1-P1 so the sheet's
content and its mechanics have different owners). Owner in Wave 2: W2-P4; W2-P5 owns the sheet mechanics (kit/chrome.py).

The question (MASTER-PLAN §2.0, §3.1, §4.2 #26, W2-P4): each answer is stored once, in `cinema.who`, `cinema.when` and
`cinema.where`, and read by the grid here (src/js/filters.js) and by the pick (W2-P2b, through window.CINEMA.ask()).
«مع منو» has three options and each says what it sets: «كبار» (the default: no limit), «العايلة» (nothing above PG13,
no horror or war), «العيال» (children's films, ending before 9). «بروحي» and «ربعي» are deleted: both set nothing
anywhere. Nothing else is set behind the visitor's back (the old preset changed the genre, the end time and the sort).

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)

# «العايلة»: nothing above PG13, and no horror or war (a film with no rating counts when the data flags it for families)
FAMILY_MAX = {"G", "PG", "PG13"}
FAMILY_NO = {"horror", "war"}
# the question's words (the dialect gate reviews them, §1.7): (value, ar, en[, what it sets ar, en])
ASK_T = {"who": ("مع منو", "Who’s coming"), "when": ("متى", "When"), "where": ("وين", "Where")}
WHO = (("", "كبار", "Adults", "كل الأفلام", "Any film"),
       ("family", "العايلة", "Family", "لين PG13، بدون رعب ولا حرب", "Up to PG13, no horror or war"),
       ("kids", "العيال", "Kids", "للأطفال، ويخلص قبل 9 بالليل", "Children’s films, over by 9 pm"))
WHEN = (("now", "الحين", "Now"), ("tonight", "الليلة", "Tonight"), ("late", "بعد العشا", "After dinner"), ("tomorrow", "بكرة", "Tomorrow"))
WHERE = (("near", "قريب مني", "Near me"), ("mine", "سينمتي", "My cinemas"), ("", "أي مكان", "Anywhere"))
# §1.7 voice table: «العيال» after 20:00, the empty filter, and the disabled button that says why
KIDS_LATE = ("العيال؟ الليلة ما في شي يناسب، شوف بكرة الصبح", "Kids? Nothing suitable tonight, try tomorrow morning.")
KIDS_AM = ("بكرة الصبح", "Tomorrow morning")
EMPTY = ("ما في شي يطابق. خفّف التصفية شوي", "Nothing matches. Loosen the filters a little.")
NONE_BTN = ("ولا فيلم، خفّف التصفية", "No films, loosen the filters")
RESET = ("شيل التصفية", "Clear filters")


def who_fits(f):
    """The «مع منو» answers a film passes, as the grid's tile carries them (data-who): «family» when it is rated PG13
    or under (or unrated and flagged for families) and is neither horror nor war; «kids» when it is a children's film.
    One rule, here: the grid (filters.js) and the pick (W2-P2b) read the attribute, never a second copy of it."""
    r = str(f.get("rating") or "").upper().replace(" ", "").replace("-", "")
    fam, kids = film_flags(f)
    out = []
    if (r in FAMILY_MAX or (not r and fam)) and not set(genre_keys(f)) & FAMILY_NO: out.append("family")
    if kids: out.append("kids")
    return " ".join(out)


class FiltersKit:
    def filters(self, lang, fids):
        """Genre chips (cinema.js): all, family, kids, and the four genres most films here share."""
        counts = {}
        for fid in fids:
            for k in genre_keys(self.films[fid]): counts[k] = counts.get(k, 0) + 1
        top = [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]]
        b = lambda attrs, label, on=False: f'<button type="button" class="chip" {attrs} aria-pressed="{"true" if on else "false"}">{esc(label)}</button>'
        chips = [b('data-filter="all"', "الكل" if lang == "ar" else "All", True),
                 b('data-filter="family"', "عائلي" if lang == "ar" else "Family"),
                 b('data-filter="kids"', "للأطفال" if lang == "ar" else "Kids")]
        chips += [b(f'data-filter="genre:{esc(k)}"', genre_label(k, lang)) for k in top]
        return f'<div class="chips filters js-only" role="group" aria-label="{"النوع" if lang == "ar" else "Genre"}">{"".join(chips)}</div>'

    def controls(self, lang, sort=True, prayer=False, who=True):
        """The second row cinema.js drives (the cinema page's, until W2-P6 deletes its control rows): «مع منو» (the same
        three answers as the filter sheet, one stored value), «يخلص قبل», the sort, the prayer switch."""
        ar = lang == "ar"
        b = lambda attrs, label, on=False: f'<button type="button" class="chip" {attrs} aria-pressed="{"true" if on else "false"}">{esc(label)}</button>'
        out = []
        if who:
            out.append(f'<div class="ctl-g"><span class="ctl-l" id="who-{lang}">{esc(L(ASK_T["who"], lang))}</span>'
                       f'<div class="chips who" role="group" aria-labelledby="who-{lang}">{"".join(b(f"data-who={chr(34)}{k}{chr(34)}", a if ar else e, not k) for k, a, e, _, _ in WHO)}</div></div>')
        opts = [("", "أي وقت", "Any time"), ("21:00", "9 بالليل", "9 pm"), ("22:00", "10 بالليل", "10 pm"), ("23:00", "11 بالليل", "11 pm"), ("24:00", "12 بالليل", "Midnight")]
        out.append(f'<label class="ctl-g ends"><span class="ctl-l">{"يخلص قبل" if ar else "Ends before"}</span>'
                   f'<select data-ends-before="">{"".join(f"<option value={chr(34)}{v}{chr(34)}>{esc(a if ar else e)}</option>" for v, a, e in opts)}</select></label>')
        if sort:
            ss = [("price", "الأرخص لك", "Cheapest for you"), ("time", "الأقرب وقت", "Soonest"), ("verdict", "الأحسن تقييم", "Best reviewed")]
            out.append(f'<div class="ctl-g"><span class="ctl-l" id="sort-{lang}">{"رتّب" if ar else "Sort"}</span>'
                       f'<div class="chips sorts" role="group" aria-labelledby="sort-{lang}">{"".join(b(f"data-sort={chr(34)}{k}{chr(34)}", a if ar else e) for k, a, e in ss)}</div></div>')
        if prayer: out.append(self.prayer_switch(lang))
        return f'<div class="ctl js-only">{"".join(out)}</div>'

    def prayer_switch(self, lang):
        """«راعِ أوقات الصلاة» (off by default): cinema.js marks shows overlapping Maghrib / Isha, and can hide them."""
        ar = lang == "ar"
        lab = "راعِ أوقات الصلاة" if ar else "Mind prayer times"
        return (f'<div class="ctl-g prayer"><span id="pr-{lang}">{lab}</span>'
                f'<button type="button" class="switch" role="switch" aria-checked="false" data-prayer aria-labelledby="pr-{lang}"><i></i></button>'
                f'<button type="button" class="chip hide-clash" data-hide-clash aria-pressed="false" hidden>{"أخفِ العروض المتقاطعة" if ar else "Hide clashing shows"}</button>'
                f'<span class="pr-t" data-prayer-times aria-live="polite"></span></div>')

    SORTS = (("time", "الأقرب وقتاً", "Soonest"), ("price", "الأرخص لك", "Cheapest for you"), ("verdict", "الأعلى تقييماً", "Best reviewed"))

    def ask(self, lang):
        """The one question, the sheet's first three rows (MASTER-PLAN §2.0): «مع منو» (each answer says what it sets; under
        «العيال» after 20:00 the offer of tomorrow morning, §1.7), «متى» and «وين» («سينمتي» shows only once the visitor has a
        favourite cinema, W3-P1; «قريب مني» asks for the location on the tap, near.js). One option each is pressed; «كبار»,
        no «متى» and «أي مكان» are the defaults, stored as nothing."""
        ar = lang == "ar"
        def opt(attr, v, label, on, small="", extra=""):
            return (f'<button type="button" class="opt" data-{attr}="{v}" aria-pressed="{"true" if on else "false"}"{extra}>{esc(label)}'
                    + (f'<small>{esc(small)}</small>' if small else "") + '</button>')
        def row(key, body, after=""):
            return (f'<div class="sec ask"><h3 class="l" id="sf-{key}">{esc(L(ASK_T[key], lang))}</h3>'
                    f'<div class="opts {key}" role="group" aria-labelledby="sf-{key}">{body}</div>{after}</div>')
        who = "".join(opt("who", v, a if ar else e, not v, sa if ar else se) for v, a, e, sa, se in WHO)
        late = (f'<p class="kids-late" data-kids-late hidden>{esc(L(KIDS_LATE, lang))} '
                f'<button type="button" class="lnk" data-kids-am>{esc(L(KIDS_AM, lang))}</button></p>')
        when = "".join(opt("when", v, a if ar else e, False) for v, a, e in WHEN)
        where = "".join(opt("where", v, a if ar else e, not v, extra=" hidden" if v == "mine" else "") for v, a, e in WHERE)
        return (row("who", who, late) + row("when", when)
                + row("where", where, '<p class="near-m" data-near-msg aria-live="polite"></p>'))

    def filter_sheet(self, lang, fids, prayer=False, yes=False):
        """The one question on top (ask), then every control of the old rows over the film list: genre (all, «يستاهل»
        and the six genres most of these films share; «عائلي» and «للأطفال» left with «مع منو»), «لازم يخلص قبل»,
        language, sort, the prayer switch; then «مسح» and «اعرض N فيلم» (the count follows the filters as they change,
        and is read out politely; at none the button is disabled and says «ولا فيلم، خفّف التصفية», §1.7)."""
        ar = lang == "ar"
        b = lambda attrs, label, on=False: f'<button type="button" class="opt" {attrs} aria-pressed="{"true" if on else "false"}">{esc(label)}</button>'
        sec = lambda key, body: (f'<div class="sec"><h3 class="l" id="sf-{key}">{esc(L(HOME_T[key], lang))}</h3>'
                                 f'<div class="opts" role="group" aria-labelledby="sf-{key}">{body}</div></div>')
        counts, langs = {}, {}
        for fid in fids:
            for k in genre_keys(self.films[fid]):
                if k not in ("family", "kids"): counts[k] = counts.get(k, 0) + 1   # families and children: «مع منو»
            lg = self.films[fid].get("lang")
            if lg: langs[lg] = langs.get(lg, 0) + 1
        top = [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]]
        genre = (b('data-filter="all"', "الكل" if ar else "All", True)
                 # «يستاهل» (the verdict), where a home row's «الكل» lands (fix round 1, M4)
                 + (b('data-filter="yes"', L(HOME_T["yes"], lang)) if yes else "") + "".join(b(f'data-filter="genre:{esc(k)}"', genre_label(k, lang)) for k in top))
        ends = [("", "ما يهم", "Any time"), ("21:00", "9 بالليل", "9 pm"), ("22:00", "10 بالليل", "10 pm"), ("23:00", "11 بالليل", "11 pm"), ("24:00", "12 بالليل", "Midnight")]
        before = "".join(b(f'data-before="{v}"', a if ar else e, not v) for v, a, e in ends)
        top_l = [k for k, n in sorted(langs.items(), key=lambda kv: (-kv[1], kv[0])) if n >= 2][:5]
        lg = b('data-flang=""', "الكل" if ar else "All", True) + "".join(b(f'data-flang="{esc(k)}"', L(LANGS.get(k, (k, k)), lang)) for k in top_l)
        sort = "".join(b(f'data-sort="{k}"', a if ar else e) for k, a, e in self.SORTS)
        # «وش الفرق؟» (301, r4-home): IMAX vs 4DX vs Dolby vs the luxury tiers, one link out of the sheet — never
        # a filter itself (the sheet has none by hall/format; this only answers what a hall label means)
        fmt_link = f'<p class="hint sfmt"><a href="{P(lang, "formats")}">{"وش الفرق بين القاعات؟" if ar else "What’s the difference between the halls?"}</a></p>'
        body = (self.ask(lang) + sec("genre", genre) + sec("before", before)
                + (sec("lang", lg) if len(top_l) > 1 else "") + sec("sort", sort) + fmt_link
                + (f'<div class="sec">{self.prayer_switch(lang)}</div>' if prayer else "")
                + f'<div class="go"><button type="button" class="btn ghost" data-reset>{esc(L(HOME_T["clear"], lang))}</button>'
                f'<button type="button" class="btn main" data-sheet-close data-show-all><span data-fshow>{"اعرض" if ar else "Show"} <span data-fn>{esc(self.films_n(len(fids), lang))}</span></span>'
                f'<span data-fnone>{esc(L(NONE_BTN, lang))}</span></button></div>'
                f'<p class="vh" data-fn-live aria-live="polite"></p>')
        return self.sheet("sheet-filter", HOME_T["filter"], body, lang)

    def sort_sheet(self, lang):
        ar = lang == "ar"
        opts = "".join(f'<button type="button" class="opt" data-sort="{k}" aria-pressed="false">{esc(a if ar else e)}</button>' for k, a, e in self.SORTS)
        return self.sheet("sheet-sort", HOME_T["sort"], f'<div class="sec"><div class="opts" data-sort-pick>{opts}</div></div>', lang)

    @staticmethod
    def films_n(n, lang):
        """«23 فيلم», «فيلمين» — as cinema.js's filmsN."""
        if lang == "en": return f"{n} film" + ("" if n == 1 else "s")
        return ar_count(n, ("فيلم واحد", "فيلمين", "أفلام", "فيلم"))
