"""The ticket: the server-drawn ticket and its shell, the show it opens on, the directions line (site_kit.Kit's
ticket helpers, moved as they were by W1-P1). Owner in Wave 2: W2-P3 (MASTER-PLAN §6.2).

A mixin of site_kit.Kit: `self` is the site. Imported by site_kit after its helpers are defined."""
from site_kit import *  # noqa: F401,F403  (the helpers these methods were written against)


class TicketKit:
    def ticket_shell(self):
        return '<aside class="ticket" id="ticket" data-ticket hidden></aside>'

    def ticket(self, s, lang, hidden=False):
        """The ticket for one show, server-rendered (no-script visitors see the prices); cinema.js refills it
        for whichever time is tapped: phone = bottom sheet, desktop = side panel."""
        cid, chain = s["cinema"], self.cinemas[s["cinema"]]["chain"]
        code, _ = self.hall_code_label(s); hk = self.hkey(s); asof = self.table_date(s)
        hidden = " hidden" if hidden else ""
        day = L(T["today"] if s["date"] == self.today else T["tomorrow"] if s["date"] == self.tomorrow else (s["date"], s["date"]), lang)
        lines = []
        if hk != "Standard": lines.append(f'<span class="tk-h">{self.hall_html(s, lang)}</span>')
        if s.get("ends"): lines.append(f'<span>{esc(L(T["ends"], lang).format(t=s["ends"]))}</span>')
        lg = s.get("lang") or self.films[s["film"]].get("lang")
        if lg:
            ln = lang_words(lg, lang)
            sb = lang_words(s["subs"], lang) if s.get("subs") else ""
            lines.append(f'<span>{esc(ln)}{("، ترجمة " + esc(sb) if lang == "ar" else ", " + esc(sb) + " subtitles") if sb else ""}</span>')
        seats = "".join(f'<tr><th scope="row"{" lang=\"en\"" if lang == "ar" and not ARABIC.search(p["seat"]) else ""}><bdi>{esc(p["seat"])}</bdi></th>'
                        f'<td>{self.pcell(p["aed"], chain, code, hk, cid, asof, lang)}</td></tr>'
                        for p in sorted((p for p in s.get("prices") or [] if (p.get("aed") or 0) > 0), key=lambda p: p["aed"]))
        seats = seats or f'<tr><td colspan="2">{self.box(lang)}</td></tr>'
        ftitle, cn = self.ftitle(s["film"], lang), self.cname(cid, lang)
        msg = f'{L(T["in_cinema"], lang).format(film=ftitle, cinema=cn)}، {day} {s["time"]}' if lang == "ar" else f'{L(T["in_cinema"], lang).format(film=ftitle, cinema=cn)}, {day} {s["time"]}'
        share = "https://wa.me/?text=" + quote(msg + "\n" + SITE + P(lang, "film", s["film"]), safe="")
        # the show's own booking page, else the chain's site (never the previous show's link)
        book = (f'<a class="book" href="{esc(self.book_url(s))}" rel="noopener nofollow" target="_blank" data-tk-book data-book="{esc(s.get("book") or "")}">'
                f'{esc(L(T["book_at"], lang).format(chain=self.h.chain_name(chain, lang)))}</a>')
        left = s.get("seats_left")
        left = f'<p class="tk-left" data-tk-seats>{esc(seats_left(int(left), lang))}</p>' if isinstance(left, int) and left > 0 else '<p class="tk-left" data-tk-seats hidden></p>'
        return (f'<aside class="ticket" id="ticket" data-ticket data-show="{self.sid(s)}" data-cin="{esc(cid)}" data-chain="{esc(chain)}"'
                f' role="dialog" aria-labelledby="tk-cin"{hidden}>'
                f'<div class="tk-top"><div class="tk-main"><p class="tk-cin" id="tk-cin" data-tk-cin>{self.cname_html(cid, lang)}</p>'
                f'<p class="tk-film" data-tk-film{self.title_attr(s["film"], lang)}>{esc(ftitle)}</p>'
                f'<p class="tk-when" data-tk-when>{"".join(lines)}</p>{left}</div>'
                f'<div class="tk-stub"><span data-tk-day>{esc(day)}</span><b dir="ltr" data-tk-time>{esc(s["time"])}</b></div></div>'
                f'<table class="tk-seats"><tbody data-tk-rows>{seats}</tbody></table>'
                # «كم بتكلفني الطلعة؟» (R4 §298): the ticket-count stepper and its total after the card — script-only
                # (the stepper itself needs a tap; a no-script visitor already has each seat's own price above),
                # so cinema.js draws its rows and total entirely; this is only its slot, always in the same place
                f'<div class="tk-qty" data-tk-qty hidden></div>'
                f'<p class="tk-terms" data-tk-terms hidden></p><p class="tk-go" data-tk-go>{self.directions(self.cinemas[cid], lang)}</p>'
                f'<p class="vh" data-tk-live aria-live="polite"></p>'
                f'<div class="tk-act">{book}<a class="share" href="{esc(share)}" rel="noopener" target="_blank" data-tk-share data-share="{esc(msg)}">{esc(L(T["share"], lang))}</a>'
                f'{self.slot("ticket.actions", lang, show=s)}</div>'
                f'<button type="button" class="tk-x js-only" data-tk-close aria-label="{"سكّر" if lang == "ar" else "Close"}"></button></aside>')

    def first_city_show(self, shows, cities):
        """The next show in the city the page shows first (Dubai, the script's default, when it is there)."""
        order = (["dubai"] if "dubai" in cities else []) + [c for c in cities if c != "dubai"]
        for c in order:
            n = self.next_show([s for s in shows if self.cinemas[s["cinema"]].get("city") == c])
            if n: return n
        return self.next_show(shows)

    def next_show(self, shows):
        """The first show still to come when the data was built (priced first), else the first at all."""
        hhmm = self.now.strftime("%H:%M")
        key = lambda s: (s["date"], s["time"])
        up = sorted((s for s in shows if (s["date"], s["time"]) >= (self.today, hhmm)), key=key)
        pool = up or sorted(shows, key=key)
        return next((s for s in pool if s.get("prices")), pool[0] if pool else None)

    def directions(self, c, lang):
        """«الوصول»: Google Maps and Waze to the cinema's coordinates (or its maps link)."""
        if c.get("lat") is not None and c.get("lng") is not None:
            ll = f'{float(c["lat"])},{float(c["lng"])}'
            g, w = f"https://www.google.com/maps/dir/?api=1&destination={ll}", f"https://waze.com/ul?ll={ll}&navigate=yes"
        else:
            m = c.get("maps") if SAFE_URL.match(str(c.get("maps") or "")) else None
            g, w = m or ("https://www.google.com/maps/search/?api=1&query=" + quote(c.get("name") or "")), None
        out = f'<a href="{esc(g)}" rel="noopener" target="_blank" lang="en">Google Maps</a>'
        if w: out += f'{"، " if lang == "ar" else ", "}<a href="{esc(w)}" rel="noopener" target="_blank" lang="en">Waze</a>'
        return f'<span class="go" data-go>{"الاتجاهات:" if lang == "ar" else "Directions:"} {out}</span>'
