"""Question pages (phase 2, A): /q/<slug>/ — a real search answered from today's data, only when the data answers
it: the number, its date, FAQPage JSON-LD and links to the pages that hold the evidence. Arabic at /q/, English
at /en/q/, indexable. /q/ lists them all.

  <format>-ticket-price-<city>    «كم سعر تذكرة IMAX في دبي؟» (and the regular hall: «…السينما العادية…»)
  <chain>-<hall>-ticket-price     «كم سعر تذكرة GOLD في فوكس؟» (a hall halls.yaml describes)
  <card>-at-<chain>               «هل فزعة تشتغل في فوكس؟» (an official rule for a confirmed card, any state)
  cheapest-cinema-<city>-tonight  «أرخص سينما في العين الليلة؟» (today's shows from 18:00)
  where-<format>                  «وين أقرب سينما فيها 4DX؟» (distances once the visitor shares a location)

A price is the cheapest live seat (price_history.show_price: never the prices.yaml fallback), on the first date
from today with the most of them; the answer says that date."""
import re
import statistics

from price_history import show_price
from site_kit import CITIES, CITY, L, P, ar_count, Page, Pages, Plugin, esc, human_date, money, num, rule_offer, rule_state, rule_terms

DIRS = ("q",)
HUB = ("أسئلة", "Questions")
# formats that mean the same thing at every chain (a chain's own hall names are asked per chain)
FORMATS = {"Standard": ("السينما العادية", "a regular cinema", "cinema"), "IMAX": ("IMAX", "IMAX", "imax"),
           "4DX": ("4DX", "4DX", "4dx"), "MX4D": ("MX4D", "MX4D", "mx4d"), "SCREENX": ("ScreenX", "ScreenX", "screenx"),
           "DOLBY": ("Dolby Cinema", "Dolby Cinema", "dolby")}
WHERE = ("IMAX", "4DX", "MX4D", "SCREENX", "DOLBY")
TONIGHT = "18:00"
SHOWS = ("عرض واحد", "عرضين", "عروض", "عرض")
CINES = ("سينما وحدة", "سينمتين", "سينمات", "سينما")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def register(site):
    qp = Questions(site)
    qs = qp.questions()
    pages = [Page(("q",), lang, lambda lang=lang: qp.hub(lang, qs)) for lang in ("ar", "en")]
    for q in qs:
        pages += [Page(("q", q["slug"]), lang, lambda lang=lang, q=q: qp.page_for(q, lang)) for lang in ("ar", "en")]
    return Plugin(pages=pages)


class Questions(Pages):
    # -------------------------------------------------- the day each answer is about
    def priced(self, shows):
        """(date, [(show, price)]) for the date from today with the most live prices among `shows` (earliest on a tie)."""
        by = {}
        for s in shows:
            if s["date"] < self.today: continue
            p = show_price(s)
            if p is not None: by.setdefault(s["date"], []).append((s, p))
        if not by: return None, []
        d = max(sorted(by), key=lambda x: len(by[x]))   # the fullest read (a late-night run has few of today's)
        return d, by[d]

    def chain_of(self, s):
        return self.cinemas[s["cinema"]]["chain"]

    def cn(self, city, lang):
        return L(CITY[city], lang)

    def aed_text(self, x, lang):
        return f"{money(x)} درهم" if lang == "ar" else f"AED {money(x)}"

    # -------------------------------------------------- which questions the data answers
    def questions(self):
        qs = []
        for key, (_, _, sl) in FORMATS.items():
            for city, _, _ in CITIES:
                ss = [s for s in self.shows if self.cinemas[s["cinema"]].get("city") == city and self.hkey(s) == key]
                d, pr = self.priced(ss)
                if pr: qs.append({"kind": "price", "slug": f"{sl}-ticket-price-{city}", "key": key, "city": city, "date": d, "rows": pr})
        for chain, c in sorted(self.h.y.items()):
            for e in c.get("halls", []):
                if e["key"] in FORMATS: continue
                ss = [s for s in self.shows if self.chain_of(s) == chain and self.hkey(s) == e["key"]]
                d, pr = self.priced(ss)
                if pr: qs.append({"kind": "hall", "slug": f"{chain}-{slug(e['key'])}-ticket-price", "chain": chain, "hall": e, "date": d, "rows": pr})
        chains = {self.cinemas[cid]["chain"] for cid in self.cinemas}
        for card in self.cards:
            for chain in sorted(self.rules):
                r = self.rules[chain].get(card["id"])
                if r and chain in chains:
                    qs.append({"kind": "card", "slug": f"{slug(card['id'])}-at-{chain}", "card": card, "chain": chain, "rule": r})
        for city, _, _ in CITIES:
            ss = [s for s in self.shows if self.cinemas[s["cinema"]].get("city") == city and s["date"] == self.today and s["time"] >= TONIGHT]
            pr = [(s, p) for s in ss for p in [show_price(s)] if p is not None]
            if pr: qs.append({"kind": "tonight", "slug": f"cheapest-cinema-{city}-tonight", "city": city, "date": self.today, "rows": pr})
        for key in WHERE:
            cids = sorted({s["cinema"] for s in self.shows if self.hkey(s) == key}, key=lambda c: (self.cinemas[c].get("city") or "", c))
            if cids: qs.append({"kind": "where", "slug": f"where-{FORMATS[key][2]}", "key": key, "cids": cids})
        return qs

    # -------------------------------------------------- one question: (question, answer text, body html, evidence)
    def by_cinema(self, rows):
        """[(cid, cheapest price, the show, shows)] cheapest first."""
        out = {}
        for s, p in rows:
            b = out.setdefault(s["cinema"], [p, s, 0])
            if p < b[0]: b[0], b[1] = p, s
            b[2] += 1
        return sorted(((cid, p, s, n) for cid, (p, s, n) in out.items()), key=lambda r: (r[1], r[0]))

    def cin_rows(self, lang, ranked, limit=12):
        rows = ""
        for cid, p, s, n in ranked[:limit]:
            c = self.cinemas[cid]; code, _ = self.hall_code_label(s)
            rows += (f'<div class="row cin" data-cin="{esc(cid)}"{self.geo_attrs(c)}><a class="nm" href="{P(lang, c["city"], cid)}">{self.cname_html(cid, lang)}</a>'
                     f'<span class="sub"><span data-dist></span><bdi>{esc(self.hname(s, lang))}</bdi> '
                     f'{esc(ar_count(n, SHOWS)) if lang == "ar" else num(n) + (" show" if n == 1 else " shows")}</span>'
                     f'<span class="from">{("من " if lang == "ar" else "from ") + self.pcell(p, c["chain"], code, self.hkey(s), cid, None, lang)}</span></div>')
        return f'<div class="rows">{rows}</div>'

    def price_answer(self, q, lang, label, where):
        ar = lang == "ar"
        ranked = self.by_cinema(q["rows"])
        prices = [p for _, p in q["rows"]]
        cid, low, _, _ = ranked[0]
        med = round(statistics.median(prices), 2)
        day = human_date(q["date"], lang)
        nc = len(ranked)
        if ar:
            a = (f"يوم {day} أرخص تذكرة {label} {where} بـ{self.aed_text(low, lang)} في {self.cname(cid, lang)}، "
                 f"والوسيط {self.aed_text(med, lang)} على {ar_count(len(prices), SHOWS)} في {ar_count(nc, CINES)}. الأسعار من أنظمة الحجز وقبل خصم البطاقة.")
        else:
            a = (f"On {day} the cheapest {label} ticket {where} was {self.aed_text(low, lang)} at {self.cname(cid, lang)}; "
                 f"the median was {self.aed_text(med, lang)} across {len(prices)} show{'s' if len(prices) != 1 else ''} at {nc} cinema{'s' if nc != 1 else ''}. Prices from the booking systems, before any card discount.")
        return a, self.cin_rows(lang, ranked)

    def build_q(self, q, lang):
        ar = lang == "ar"
        k = q["kind"]
        ev = [(P(lang, "prices"), "مؤشر الأسعار" if ar else "The price index")]
        if k == "price":
            nm = FORMATS[q["key"]][0 if ar else 1]
            cn = self.cn(q["city"], lang)
            question = (f"كم سعر تذكرة {nm} في {cn}؟" if ar else
                        (f"How much is a cinema ticket in {cn}?" if q["key"] == "Standard" else f"How much is an {nm} ticket in {cn}?" if nm[0] in "AEIOU" else f"How much is a {nm} ticket in {cn}?"))
            label = ("السينما العادية" if ar else "regular-hall") if q["key"] == "Standard" else nm
            a, html_ = self.price_answer(q, lang, label, f"في {cn}" if ar else f"in {cn}")
            ev = [(P(lang, q["city"]), f"سينمات {cn} اليوم" if ar else f"Cinemas in {cn} today")] + ev + [(P(lang, "halls"), "القاعات" if ar else "The halls")]
        elif k == "hall":
            e, chn = q["hall"], self.h.chain_name(q["chain"], lang)
            nm = e.get("name") or e["key"]
            question = f"كم سعر تذكرة {nm} في {chn}؟" if ar else f"How much is a {nm} ticket at {chn}?"
            a, html_ = self.price_answer(q, lang, nm, f"في {chn}" if ar else f"at {chn}")
            what = e.get("what_ar") if ar else e.get("what_en")
            if what: html_ = f'<p class="hint">{esc(what)}</p>' + html_
            ev = [(P(lang, "halls"), "شو فيها القاعات" if ar else "What is in each hall")] + ev
        elif k == "card":
            card, r = q["card"], q["rule"]
            cname = card["name_ar"] if ar else card["name_en"]
            chn = self.h.chain_name(q["chain"], lang)
            question = f"هل {cname} تشتغل في {chn}؟" if ar else f"Does {cname} work at {chn}?"
            st = rule_state(r, self.today)
            checked = human_date(r.get("checked"), lang) if r.get("checked") else None
            chk = ((f" تحققنا يوم {checked}." if ar else f" Checked on {checked}.") if checked else "")
            if st == "ok":
                terms = rule_terms(r, lang)
                a = ((f"إيه، {cname} تعطيك {rule_offer(r, lang)} في {chn}" if ar else f"Yes: {cname} gives {rule_offer(r, lang)} at {chn}")
                     + ((" — " + ("، ".join(terms) if ar else "; ".join(terms))) if terms else "") + "." + chk)
            elif st == "expired":
                vu = human_date(r.get("valid_until"), lang)
                a = (f"لا حالياً: عرض {cname} في {chn} انتهى يوم {vu}." if ar else f"Not now: the {cname} offer at {chn} ended on {vu}.") + chk
            else:
                a = (f"ما لقينا خصم {cname} في {chn} في عروض السينما أو البطاقة." if ar else f"We found no {cname} discount at {chn} in the chain's or the card's offers.") + chk
            html_ = ""
            ev = [(P(lang, "cards", card["id"]), (f"خصم {cname} في كل السينمات" if ar else f"{cname} at every cinema"))]
            if r.get("source"): ev.append((r["source"], "المصدر" if ar else "Source"))
        elif k == "tonight":
            cn = self.cn(q["city"], lang)
            question = f"أرخص سينما في {cn} الليلة؟" if ar else f"Which is the cheapest cinema in {cn} tonight?"
            ranked = self.by_cinema(q["rows"])
            cid, low, s, _ = ranked[0]
            day = human_date(q["date"], lang)
            a = (f"الليلة ({day}، من الساعة 6 المسا) أرخص تذكرة في {cn} بـ{self.aed_text(low, lang)} في {self.cname(cid, lang)}، الساعة {s['time']}. الأسعار قبل خصم البطاقة."
                 if ar else f"Tonight ({day}, from 6 pm) the cheapest ticket in {cn} is {self.aed_text(low, lang)} at {self.cname(cid, lang)}, at {s['time']}. Prices before any card discount.")
            html_ = self.cin_rows(lang, ranked, 8)
            ev = [(P(lang, q["city"]), f"كل عروض {cn} اليوم" if ar else f"Every show in {cn} today")] + ev
        else:   # where
            nm = FORMATS[q["key"]][0 if ar else 1]
            question = f"وين أقرب سينما فيها {nm}؟" if ar else f"Where is the nearest {nm} cinema?"
            cids = q["cids"]
            names = ("؛ " if ar else "; ").join(self.cname(c, lang) for c in cids[:8]) + ("…" if len(cids) > 8 else "")
            day = human_date(self.today, lang)
            a = (f"يوم {day} كان فيه عروض {nm} في {ar_count(len(cids), CINES)}: {names}." if ar
                 else f"On {day} {nm} shows were on at {len(cids)} cinema{'s' if len(cids) != 1 else ''}: {names}.")
            rows = "".join(f'<div class="row cin" data-cin="{esc(c)}"{self.geo_attrs(self.cinemas[c])}><a class="nm" href="{P(lang, self.cinemas[c]["city"], c)}">{self.cname_html(c, lang)}</a>'
                           f'<span class="sub"><span data-dist></span>{esc(self.cn(self.cinemas[c]["city"], lang))}</span></div>' for c in cids)
            html_ = (f'<p class="near js-only"><button type="button" class="btn ghost" data-near>{"رتّبها من الأقرب لي" if ar else "Sort them by distance from me"}</button></p>'
                     f'<div class="rows">{rows}</div>')
            ev = [(P(lang, "halls"), "القاعات" if ar else "The halls")]
        return question, a, html_, ev

    # -------------------------------------------------- pages
    def page_for(self, q, lang):
        question, answer, html_, ev = self.build_q(q, lang)
        links = " ".join(f'<a href="{esc(h)}"' + (' rel="noopener" target="_blank"' if h.startswith("http") else "") + f'>{esc(t)}</a>' for h, t in ev)
        body = (f'<section class="head wrap">{self.crumbs(lang, (L(HUB, lang), P(lang, "q")), (question, None))}'
                f'<h1 class="pt">{esc(question)}</h1></section>'
                f'<section class="wrap qa"><p class="ans">{self.digits(answer)}</p>{html_}'
                f'<p class="links more ev">{links}</p></section>')
        graph = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": question,
                                                       "acceptedAnswer": {"@type": "Answer", "text": answer}}]},
                 self.breadcrumb_ld(lang, (L(HUB, lang), P(lang, "q")), (question, P(lang, "q", q["slug"])))]
        return {"title": question.rstrip("؟?") + (" — سينما" if lang == "ar" else " — Cinema"), "desc": answer[:300],
                "body": body + self.ticket_shell(), "graph": graph, "kind": "q", "nav": "q"}

    @staticmethod
    def digits(text):
        """escaped answer with each number isolated (an Arabic run must not reorder «55.00» or «20%»)."""
        return re.sub(r"(&#?\w+;)|(\d+(?:[.:]\d+)?%?)",
                      lambda m: m.group(1) or f'<span class="num" dir="ltr">{m.group(2)}</span>', esc(text))

    def hub(self, lang, qs):
        ar = lang == "ar"
        groups = [("price", "كم السعر؟" if ar else "How much?"), ("hall", "القاعات المميزة" if ar else "Premium halls"),
                  ("card", "البطاقات" if ar else "Cards"), ("tonight", "الليلة" if ar else "Tonight"), ("where", "وين ألقى؟" if ar else "Where?")]
        body = (f'<section class="head wrap">{self.crumbs(lang, (L(HUB, lang), None))}<h1 class="pt">{"أسئلة عن السينما في الإمارات" if ar else "Questions about UAE cinemas"}</h1>'
                f'<p class="lead">{esc("كل جواب من أرقام اليوم ومعه تاريخه، وما نكتب سؤال ما عندنا له جواب." if ar else "Every answer comes from today’s numbers with its date; a question we cannot answer is not here.")}</p></section>'
                f'<section class="wrap q-hub">')
        for kind, head in groups:
            items = [q for q in qs if q["kind"] == kind]
            if not items: continue
            body += f'<h2>{esc(head)}</h2><ul>' + "".join(f'<li><a href="{P(lang, "q", q["slug"])}">{esc(self.build_q(q, lang)[0])}</a></li>' for q in items) + '</ul>'
        body += '</section>'
        title = "أسئلة وأجوبة عن السينما في الإمارات — من أرقام اليوم" if ar else "UAE cinema questions, answered from today’s numbers"
        desc = ("كم سعر تذكرة IMAX، هل فزعة تشتغل في فوكس، أرخص سينما الليلة: أجوبة من أسعار وجداول السينمات اليوم." if ar
                else "What an IMAX ticket costs, whether Fazaa works at VOX, the cheapest cinema tonight: answered from today's prices and schedules.")
        return {"title": title, "desc": desc, "body": body, "kind": "q", "nav": "q",
                "graph": [self.breadcrumb_ld(lang, (L(HUB, lang), P(lang, "q")))]}
