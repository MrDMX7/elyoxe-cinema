"""Schedules: show ids, time buttons, the bounded compact form, the halls still to come (site_kit.Kit's
schedule helpers and pages/core.py's live_halls, moved as they were by W1-P1). Owner in Wave 2: W2-P3.

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)


class SchedKit:
    # -------- show ids, time buttons and the page's price lists (for the ticket)
    @staticmethod
    def sid(s):
        k = "|".join(str(s.get(x) or "") for x in ("cinema", "film", "date", "time", "hall", "hall_label", "book"))
        return hashlib.sha1(k.encode()).hexdigest()[:10]

    def pidx(self, s):
        pr = [[p["seat"], p["aed"]] for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
        if not pr: return None
        k = json.dumps(pr)
        if k not in self._Pi: self._Pi[k] = len(self._P); self._P.append(pr)
        return self._Pi[k]

    def book_url(self, s):
        """The show's booking URL, else the chain's own site (a time always leads somewhere with no script)."""
        return s.get("book") or CHAIN_SITE.get(self.cinemas[s["cinema"]]["chain"]) or (SITE + P("ar", self.cinemas[s["cinema"]].get("city"), s["cinema"]))

    def is_past(self, s):
        return (s["date"], s["time"]) < (self.today, self.now.strftime("%H:%M"))

    def tbtn(self, s, lang, links=True, tag=True, on=False):
        """A showtime is a link to its booking page (works with no script); cinema.js prevents the navigation
        and opens the ticket instead. data-show is the show's stable id; data-p indexes the page's price lists
        (#cinema-p), data-book is the booking URL. A show already started when the data was built is plain text."""
        t = f'<small>{self.hall_html(s, lang)}</small>' if tag and self.hkey(s) != "Standard" else ""
        if self.is_past(s):
            return f'<span class="tm past" data-start="{esc(s["time"])}">{esc(s["time"])}{t}</span>'
        a = [f'data-show="{self.sid(s)}"', f'data-start="{esc(s["time"])}"']
        if s.get("ends"): a.append(f'data-ends="{esc(s["ends"])}"')
        if s.get("lang"): a.append(f'data-lang="{esc(s["lang"])}"')
        if s.get("subs"): a.append(f'data-subs="{esc(s["subs"])}"')
        if isinstance(s.get("seats_left"), int) and s["seats_left"] > 0: a.append(f'data-left="{s["seats_left"]}"')
        pi = self.pidx(s)
        if pi is not None: a.append(f'data-p="{pi}"')
        if self.table_date(s) and pi is not None: a.append(f'data-asof="{esc(self.table_date(s))}"')
        # plain (over budget): the chain's site instead of the long per-show URL
        href = self.book_url(s) if links else (CHAIN_SITE.get(self.cinemas[s["cinema"]]["chain"]) or self.book_url(s))
        if links and s.get("book"): a.append(f'data-book="{esc(s["book"])}"')
        return (f'<a class="tm{" on" if on else ""}" href="{esc(href)}" rel="noopener nofollow" target="_blank" {" ".join(a)}'
                f'{" aria-current=\"true\"" if on else ""}>{esc(s["time"])}{t}</a>')

    def times(self, shows, lang, tag_halls=False, links=True, day_label=True, on=None):
        """Showtimes, one row per day: <div class="times" data-d="…"><span class="dl">اليوم</span><button…>…"""
        out = []
        for d in sorted({s["date"] for s in shows}):
            lab = f'<span class="dl">{esc(L(T["today"] if d == self.today else T["tomorrow"] if d == self.tomorrow else (d, d), lang))}</span>' if day_label else ""
            items = "".join(self.tbtn(s, lang, links, tag_halls, on is not None and self.sid(s) == on)
                            for s in sorted((s for s in shows if s["date"] == d), key=lambda s: s["time"]))
            out.append(f'<div class="times" data-d="{d}">{lab}{items}</div>')
        return "".join(out)

    def times_compact(self, shows, lang, tag=False, day_label=True):
        """The bounded form: per day, the times still to come as text, one run per hall
        (<span class="tl" data-hk="IMAX"><small>IMAX</small> 13:00 15:30</span>). No script: the cinema's name
        links to its page, where every time books. cinema.js makes each time a button whose ticket it fills
        from the city's slice."""
        out = []
        for d in sorted({s["date"] for s in shows}):
            ds = [s for s in shows if s["date"] == d and not self.is_past(s)]
            if not ds: continue
            lab = f'<span class="dl">{esc(L(T["today"] if d == self.today else T["tomorrow"] if d == self.tomorrow else (d, d), lang))}</span>' if day_label else ""
            keys = sorted(dict.fromkeys(self.hkey(s) for s in ds), key=lambda k: k != "Standard")
            runs = []
            for k in keys:
                hs = [s for s in ds if self.hkey(s) == k]
                ts = " ".join(sorted({s["time"] for s in hs}))
                if tag and k != "Standard":
                    runs.append(f'<span class="tl" data-hk="{esc(k)}"><small>{self.hall_html(hs[0], lang)}</small> {ts}</span>')
                else:
                    runs.append(f'<span class="tl">{ts}</span>')
            out.append(f'<div class="times" data-d="{d}">{lab}{"".join(runs)}</div>')
        return "".join(out)

    def live_halls(self, shows, hall):
        """The shows of every hall (`hall(s)` its key) that still has a time to come when the data was built:
        a hall whose times have all passed is dropped with its heading («THEATRE من 195.00» over nothing).
        Only the build's clock is known here: a hall whose last time passes later is the client's to hide."""
        live = {hall(s) for s in shows if not self.is_past(s)}
        return [s for s in shows if hall(s) in live]
