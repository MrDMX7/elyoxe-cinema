"""The filter sheet's content: genre chips, «مع منو رايح؟», «لازم يخلص قبل», language, sort, the prayer switch
(site_kit.Kit's filter helpers, moved out of the chrome by W1-P1 so the sheet's content and its mechanics
have different owners). Owner in Wave 2: W2-P4; W2-P5 owns the sheet mechanics (kit/chrome.py).

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)


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
        """The second row cinema.js drives: «مع منو رايح؟» presets, «يخلص قبل», the sort, the prayer switch."""
        ar = lang == "ar"
        b = lambda attrs, label: f'<button type="button" class="chip" {attrs} aria-pressed="false">{esc(label)}</button>'
        out = []
        if who:
            ws = [("solo", "بروحي", "Just me"), ("friends", "ربعي", "Friends"), ("family", "العائلة", "Family"), ("kids", "العيال", "The kids")]
            out.append(f'<div class="ctl-g"><span class="ctl-l" id="who-{lang}">{"مع منو رايح؟" if ar else "Going with"}</span>'
                       f'<div class="chips who" role="group" aria-labelledby="who-{lang}">{"".join(b(f"data-who={chr(34)}{k}{chr(34)}", a if ar else e) for k, a, e in ws)}</div></div>')
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

    def filter_sheet(self, lang, fids, prayer=False, yes=False):
        """Every control of the old rows over the film list, in one sheet: genre (all, family, kids and the six
        genres most of these films share), «مع منو رايح؟», «لازم يخلص قبل», language, sort, the prayer switch;
        then «مسح» and «اعرض N فيلم» (the count follows the filters as they change, and is read out politely)."""
        ar = lang == "ar"
        b = lambda attrs, label, on=False: f'<button type="button" class="opt" {attrs} aria-pressed="{"true" if on else "false"}">{esc(label)}</button>'
        sec = lambda key, body: (f'<div class="sec"><h3 class="l" id="sf-{key}">{esc(L(HOME_T[key], lang))}</h3>'
                                 f'<div class="opts" role="group" aria-labelledby="sf-{key}">{body}</div></div>')
        counts, langs = {}, {}
        for fid in fids:
            for k in genre_keys(self.films[fid]):
                if k not in ("family", "kids"): counts[k] = counts.get(k, 0) + 1   # «عائلي»/«للأطفال» have their own chips
            lg = self.films[fid].get("lang")
            if lg: langs[lg] = langs.get(lg, 0) + 1
        top = [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]]
        genre = (b('data-filter="all"', "الكل" if ar else "All", True) + b('data-filter="family"', "عائلي" if ar else "Family")
                 + b('data-filter="kids"', "للأطفال" if ar else "Kids")
                 # «يستاهل» (the verdict), where a home row's «الكل» lands (fix round 1, M4)
                 + (b('data-filter="yes"', L(HOME_T["yes"], lang)) if yes else "") + "".join(b(f'data-filter="genre:{esc(k)}"', genre_label(k, lang)) for k in top))
        ws = [("solo", "بروحي", "Just me"), ("friends", "ربعي", "Friends"), ("family", "العائلة", "Family"), ("kids", "العيال", "The kids")]
        who = "".join(b(f'data-who="{k}"', a if ar else e) for k, a, e in ws)
        ends = [("", "ما يهم", "Any time"), ("21:00", "9 بالليل", "9 pm"), ("22:00", "10 بالليل", "10 pm"), ("23:00", "11 بالليل", "11 pm"), ("24:00", "12 بالليل", "Midnight")]
        before = "".join(b(f'data-before="{v}"', a if ar else e, not v) for v, a, e in ends)
        top_l = [k for k, n in sorted(langs.items(), key=lambda kv: (-kv[1], kv[0])) if n >= 2][:5]
        lg = b('data-flang=""', "الكل" if ar else "All", True) + "".join(b(f'data-flang="{esc(k)}"', L(LANGS.get(k, (k, k)), lang)) for k in top_l)
        sort = "".join(b(f'data-sort="{k}"', a if ar else e) for k, a, e in self.SORTS)
        body = (sec("genre", genre) + sec("who", who) + sec("before", before)
                + (sec("lang", lg) if len(top_l) > 1 else "") + sec("sort", sort)
                + (f'<div class="sec">{self.prayer_switch(lang)}</div>' if prayer else "")
                + f'<div class="go"><button type="button" class="btn ghost" data-reset>{esc(L(HOME_T["clear"], lang))}</button>'
                f'<button type="button" class="btn main" data-sheet-close data-show-all>{"اعرض" if ar else "Show"} <span data-fn>{esc(self.films_n(len(fids), lang))}</span></button></div>'
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
