"""Money: the cards (each card, the matrix, the stubs of unconfirmed cards), the halls and /sources/
(pages/core.py's money family, moved as it was by W1-P1). Owner in Wave 2: W2-P9 (MASTER-PLAN §6.2).

Methods of pages.core.CorePages: `self` is a Pages, which reads everything else (self.page, self.poster,
self.shows ...) through to the site."""
from site_kit import *  # noqa: F401,F403  (the names these pages were written against)


class MoneyPages:
    def cards_strip(self, lang):
        gov = [c for c in self.cards if c.get("kind") == "gov"]
        bank = [c for c in self.cards if c.get("kind") != "gov"]
        a = lambda c: f'<a href="{P(lang, "cards", c["id"])}">{esc(c["name_ar"] if lang == "ar" else c["name_en"])}</a>'
        return (f'<section class="wrap cardsx"><h2>{"خصم بطاقتك في السينما" if lang == "ar" else "Your card at the cinema"}</h2>'
                f'<p class="lead">{"وين تنفع كل بطاقة، كم تخصم، وشروطها، ومتى تحققنا منها. نعرض بس الخصومات اللي أعلنتها السينما أو البطاقة نفسها." if lang == "ar" else "Where each card works, how much it takes off, the conditions and when we checked. Only discounts the cinema or the card issuer states themselves."}</p>'
                + (f'<p class="links"><span>{"حكومية" if lang == "ar" else "Government"}</span> {" ".join(a(c) for c in gov)}</p>' if gov else "")
                + (f'<p class="links"><span>{"بنوك" if lang == "ar" else "Banks"}</span> {" ".join(a(c) for c in bank)}</p>' if bank else "")
                + f'<p class="links more"><a href="{P(lang, "cards")}">{"كل البطاقات في جدول واحد" if lang == "ar" else "All cards in one table"}</a> <a href="{P(lang, "halls")}">{"القاعات المميزة، شو فيها؟" if lang == "ar" else "Premium halls, explained"}</a></p></section>')

    def sources(self, lang):
        rows = []
        for chain, ch in sorted(self.d.get("chains", {}).items()):
            at = parse_iso(ch["at"]) if ch.get("at") else None
            state = ("" if ch.get("ok", True) else f' <span class="stale">{"ما قدرنا نحدّث آخر مرة" if lang == "ar" else "last refresh failed"}</span>')
            rows.append(f'<li><b>{esc(self.h.chain_name(chain, lang))}</b> '
                        + (f'<span class="age" data-at="{esc(ch["at"])}">{esc(L(T["updated"], lang))} {esc(ago(at, self.now, lang))}</span>' if at else "")
                        + state + '</li>')
        return (f'<section class="wrap srcs"><h2>{"من وين الأسعار" if lang == "ar" else "Where the prices come from"}</h2>'
                f'<p class="hint">{"من نظام الحجز عند كل سينما: المواعيد كل ساعة، والسعر مرة باليوم لكل قاعة. إذا ما حصلنا السعر نكتب «السعر في الشباك»، وما نخمّن." if lang == "ar" else "From each chain’s booking system: showtimes every hour, prices once a day per hall. When we can’t read a price we say «price at the box office» — we never guess."}</p>'
                f'<ul class="chains">{"".join(rows)}</ul></section>')

    def sources_page(self):
        """/sources/: where the prices come from, and each chain's last refresh (was the home page's last section)."""
        for lang in ("ar", "en"):
            name = L(UI["s_sources"], lang)
            body = (f'<section class="head wrap">{self.crumbs(lang, (name, None))}<h1 class="pt">{esc(name)}</h1></section>'
                    + self.sources(lang).replace('<section class="wrap srcs"><h2>', '<section class="wrap srcs"><h2 class="vh">', 1)
                    + self.slot("sources.body", lang))   # «كيف نختار لك» (W1-P1's slot, W2-P2)
            title = ("من وين أسعار السينما — سينما" if lang == "ar" else "Where the cinema prices come from — Cinema")
            desc = ("الأسعار من نظام الحجز عند كل سينما، ومتى حدّثنا كل سلسلة آخر مرة." if lang == "ar"
                    else "Prices come from each chain’s booking system; when each chain was last refreshed.")
            self.page(lang, ("sources",), title, desc, body, [self.breadcrumb_ld(lang, (name, P(lang, "sources")))], "sources", nav="sources")

    # -------------------------------------------------- cards
    def example(self, chain, card, lang):
        """«تذكرة ستار العادية 42.00 33.60» (struck, then paid) from the cheapest priced seat this chain sells
        in a hall the card covers."""
        best = None
        for s in self.shows:
            if self.cinemas[s["cinema"]]["chain"] != chain: continue
            for p in s.get("prices") or []:
                a, _ = after(p["aed"], chain, s.get("hall") or "OTHER", card, self.rules, self.today, self.hkey(s), s["cinema"])
                if a is not None and (best is None or (s.get("hall") == "Standard", -p["aed"]) > (best[2].get("hall") == "Standard", -best[0])):
                    best = (p["aed"], a, s, p["seat"])
        if not best: return ""
        aed, a, s, seat = best
        hn = self.hname(s, lang)
        what = (f"تذكرة {self.h.chain_name(chain, lang)} {'العادية' if s.get('hall') == 'Standard' else hn} ({seat})" if lang == "ar"
                else f"A {self.h.chain_name(chain, lang)} {'Standard' if s.get('hall') == 'Standard' else hn} ticket ({seat})")
        pp = f' <small class="per">{esc(L(T["per_person"], lang))}</small>' if (rule_for(self.rules, chain, card) or {}).get("type") == "bogo" else ""
        return f'<p class="ex">{esc(what)} <s class="num">{money(aed)}</s> <b class="num">{money(a)}</b> <small>{esc(L(T["aed"], lang))}</small>{pp}</p>'

    def card_pages(self):
        chains = sorted({c["chain"] for c in self.cinemas.values()} | set(self.rules))
        for card in self.cards:
            cid = card["id"]
            for lang in ("ar", "en"):
                cn = card["name_ar"] if lang == "ar" else card["name_en"]
                body = f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, None))}'
                body += f'<h1 class="pt">{"خصم " + cn + " على السينما" if lang == "ar" else cn + " discounts at UAE cinemas"}</h1>'
                ok = [ch for ch in chains if rule_state(rule_for(self.rules, ch, cid), self.today) == "ok"]
                okn = ("، " if lang == "ar" else ", ").join(self.h.chain_name(ch, lang) for ch in ok)
                body += (f'<p class="lead">{(f"تنفع اليوم في: {okn}." if ok else f"ما لقينا خصم قائم لبطاقة {cn} في السينمات اليوم.") if lang == "ar" else (f"Works today at: {okn}." if ok else f"We found no current {cn} discount at UAE cinemas.")}'
                         f' {"كل سطر تحت فيه مصدره وتاريخ آخر فحص." if lang == "ar" else "Every line below carries its source and the date we checked it."}</p></section>')
                body += '<section class="wrap"><div class="rows cardrows">'
                faq = []
                for ch in chains:
                    r = rule_for(self.rules, ch, cid); st = rule_state(r, self.today)
                    if st == "unchecked": continue
                    body += self.card_row(card, ch, r, st, lang, label=self.h.chain_name(ch, lang))
                    if st == "ok": body += self.example(ch, cid, lang)
                    chn = self.h.chain_name(ch, lang)
                    q = f"هل خصم {cn} يشتغل في {chn}؟" if lang == "ar" else f"Does {cn} work at {chn}?"
                    if st == "ok":
                        a = (f"إيه، {rule_offer(r, lang)}" + (f" ({'، '.join(rule_terms(r, lang))})" if rule_terms(r, lang) else "") + f". تحققنا {r.get('checked')}." if lang == "ar"
                             else f"Yes, {rule_offer(r, lang)}" + (f" ({', '.join(rule_terms(r, lang))})" if rule_terms(r, lang) else "") + f". Checked {r.get('checked')}.")
                    elif st == "none_found":
                        a = (f"ما لقينا خصم {cn} في {chn} وقت آخر فحص ({r.get('checked')})." if lang == "ar" else f"We found no {cn} discount at {chn} when we last checked ({r.get('checked')}).")
                    elif st == "expired":
                        a = (f"كان في {rule_offer(r, lang)} لين {r.get('valid_until')}، والعرض انتهى." if lang == "ar" else f"There was {rule_offer(r, lang)} until {r.get('valid_until')}; it has ended.")
                    else: continue
                    faq.append((q, a))
                body += '</div></section>'
                if faq:
                    body += (f'<section class="wrap faq"><h2>{"أسئلة" if lang == "ar" else "Questions"}</h2>'
                             + "".join(f"<details><summary>{esc(q)}</summary><p>{dates(esc(a))}</p></details>" for q, a in faq) + '</section>')
                body += self.cards_strip(lang)
                title = (f"خصم {cn} على السينما — {okn or 'السينمات'}، كم توفّر؟" if lang == "ar" else f"{cn} cinema discount in the UAE — where it works and how much you save")
                desc = (f"وين ينفع خصم {cn} في سينمات الإمارات، كم يخصم، شروطه، وأمثلة على السعر قبل وبعد الخصم — من المصدر الرسمي وبتاريخ الفحص." if lang == "ar"
                        else f"Where the {cn} discount works at UAE cinemas, how much it takes off, its conditions and before/after prices — from the official source, dated.")
                graph = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
                         self.breadcrumb_ld(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, P(lang, "cards", cid)))]
                self.page(lang, ("cards", cid), title, desc, body, graph, "card", nav="cards")
        # index: every confirmed card × every chain
        for lang in ("ar", "en"):
            body = f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_cards"], lang), None))}'
            body += f'<h1 class="pt">{"خصومات السينما بالبطاقات" if lang == "ar" else "Cinema discounts by card"}</h1>'
            body += f'<p class="lead">{"كل بطاقة مقابل كل سلسلة، من المصدر الرسمي. الفراغ يعني ما لقينا خصم رسمي، مب إن السينما ترفض." if lang == "ar" else "Every card against every chain, from the official source. A blank means no official discount found — not that the cinema refuses it."}</p></section>'
            head = "".join(f'<th scope="col">{esc(self.h.chain_name(ch, lang))}</th>' for ch in chains)
            rows = ""
            for card in self.cards:
                cells = ""
                for ch in chains:
                    r = rule_for(self.rules, ch, card["id"]); st = rule_state(r, self.today)
                    txt = (f'<b class="num" dir="ltr">{"1+1" if r.get("type") == "bogo" else (f"{float(r.get("value") or 0):g} AED" if r.get("type") == "fixed" else f"{r.get("value", 0):g}%")}</b>') if st == "ok" else \
                          (f'<span class="nil">{esc(L(T["none_found"], lang))}</span>' if st == "none_found" else f'<span class="nil">{esc(L(T["expired"], lang))}</span>' if st == "expired" else "")
                    cells += f"<td>{txt}</td>"
                rows += f'<tr><th scope="row"><a href="{P(lang, "cards", card["id"])}">{esc(card["name_ar"] if lang == "ar" else card["name_en"])}</a></th>{cells}</tr>'
            # a phone (W2-P9, 2026-10-17): the matrix scrolled sideways and showed 2 of 7 columns, the rest cut mid-word;
            # one block per card instead — its best offer in gold and where it works, the matrix from 1024 px only
            body += (f'<section class="wrap"><div class="cph-l">{"".join(self.card_block(card, chains, lang) for card in self.cards)}</div>'
                     f'<div class="xwrap"><table class="matrix"><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
                     f'<p class="hint">{"1+1 = تذكرتين بسعر وحدة." if lang == "ar" else "1+1 = buy one, get one."}</p></section>')
            title = ("خصومات السينما في الإمارات — فزعة وإسعاد وعروض البنوك" if lang == "ar" else "UAE cinema discounts — Fazaa, Esaad and bank cards")
            desc = ("جدول واحد لكل خصومات السينما الرسمية في الإمارات: فزعة وإسعاد والبنوك، في فوكس وستار ونوفو وريل وروكسي وسيني رويال وسينما سيتي." if lang == "ar"
                    else "One table of every official UAE cinema discount: Fazaa, Esaad and banks, at VOX, Star, Novo, Reel, Roxy, Cine Royal and Cinemacity.")
            self.page(lang, ("cards",), title, desc, body, [self.breadcrumb_ld(lang, (L(UI["s_cards"], lang), P(lang, "cards")))], "cards", nav="cards")

    def card_block(self, card, chains, lang):
        """One card on a phone: its name (a link to its page), its best current offer in gold with the chains that give
        it, then every other chain's offer on one seat-grey line; a card with no current offer says so once."""
        cid = card["id"]; ar = lang == "ar"
        name = card["name_ar"] if ar else card["name_en"]
        offers = []   # (rank, offer text, chain name)
        for ch in chains:
            r = rule_for(self.rules, ch, cid)
            if rule_state(r, self.today) != "ok": continue
            v = float(r.get("value") or 0)
            rank = v if r.get("type") == "percent" else 50 if r.get("type") == "bogo" else 1   # percent by size, 1+1 as a half, a set price last
            offers.append((rank, rule_offer(r, lang), self.h.chain_name(ch, lang)))
        if not offers:
            best = f'<span class="nil">{esc(L(T["none_found"], lang))}</span>'; rest = ""
        else:
            offers.sort(key=lambda o: (-o[0], o[1], o[2]))
            top = offers[0][1]
            top_chains = [o[2] for o in offers if o[1] == top]
            glue = " و" if ar else " and "
            best = f'<b class="off">{dates(esc(top))}</b> <span class="in">{"في " if ar else "at "}{esc(("، " if ar else ", ").join(top_chains[:-1]) + (glue if len(top_chains) > 1 else "") + top_chains[-1])}</span>'
            others = [o for o in offers if o[1] != top]
            rest = f'<small class="cph-c">{dates(esc(("، " if ar else ", ").join(f"{o[2]} {o[1]}" for o in others)))}</small>' if others else ""
        return (f'<a class="cph" href="{P(lang, "cards", cid)}"><span class="cph-n">{esc(name)}</span>'
                f'<span class="cph-b">{best}</span>{rest}</a>')

    # -------------------------------------------------- halls
    def halls_page(self):
        for lang in ("ar", "en"):
            body = f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_halls"], lang), None))}'
            body += f'<h1 class="pt">{"القاعات المميزة في سينمات الإمارات" if lang == "ar" else "Premium cinema halls in the UAE"}</h1>'
            body += f'<p class="lead">{"كل سلسلة تسمّي قاعتها الغالية باسم. هني شو فيها فعلاً، وكم سعرها اليوم، ووين تلقاها." if lang == "ar" else "Every chain names its premium hall differently. Here is what is actually inside, what it costs today and where to find it."}</p></section>'
            faq = []
            for chain, c in self.h.y.items():
                body += f'<section class="wrap hchain"><h2>{esc(self.h.chain_name(chain, lang))}</h2><div class="halls">'
                for e in c.get("halls", []):
                    ss = [s for s in self.shows if self.cinemas[s["cinema"]]["chain"] == chain and self.hkey(s) == e["key"]]
                    ps = [p["aed"] for s in ss for p in s.get("prices") or [] if p.get("aed")]
                    where = sorted({s["cinema"] for s in ss})
                    rng = (f'{num(money(min(ps)))}' + (f' – {num(money(max(ps)))}' if max(ps) != min(ps) else "") + f' <small>{esc(L(T["aed"], lang))}</small>') if ps else ""
                    what = e.get("what_ar") if lang == "ar" else e.get("what_en")
                    conf = {"high": "", "medium": ("من مصدر غير رسمي" if lang == "ar" else "from a non-official source"),
                            "low": ("ما تأكدنا من التفاصيل" if lang == "ar" else "details not confirmed")}.get(e.get("confidence"), "")
                    hname = e.get("name") or e["key"]
                    latin = lang == "ar" and not ARABIC.search(hname)
                    body += (f'<div class="hall"><h3{" lang=\"en\"" if latin else ""}>{esc(hname)}</h3><p>{dates(esc(what))}'
                             + (f' <small class="weak">{esc(conf)}</small>' if conf else "")
                             + (f' <a class="src" href="{esc(e["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>' if e.get("source") else "") + '</p>'
                             + (f'<p class="rng">{"اليوم" if lang == "ar" else "Today"} {rng}</p>' if rng else "")
                             + (f'<p class="where">{"".join(f"<a href=\"{P(lang, self.cinemas[w]["city"], w)}\">{self.cname_html(w, lang)}</a>" for w in where)}</p>' if where else "")
                             + '</div>')
                    faq.append(((f"شو فيها قاعة {e.get('name') or e['key']} في {self.h.chain_name(chain, lang)}؟" if lang == "ar" else f"What is {e.get('name') or e['key']} at {self.h.chain_name(chain, lang)}?"), what))
                body += '</div></section>'
            title = ("قاعات السينما في الإمارات — GOLD وTHEATRE وIMAX وSUITES، شو الفرق وكم السعر؟" if lang == "ar" else "UAE premium cinema halls — GOLD, THEATRE, IMAX, SUITES: what’s the difference?")
            desc = ("شو الفرق بين قاعات فوكس جولد وثياتر وماكس، وستار سويتس، ونوفو سفن ستار، وروكسي بلاتينيوم، وريل دولبي، وكم سعرها اليوم." if lang == "ar"
                    else "The difference between VOX GOLD, THEATRE and MAX, Star Suites, Novo 7 Star, Roxy Platinum, Reel Dolby and more — and what they cost today.")
            graph = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq if a]},
                     self.breadcrumb_ld(lang, (L(UI["s_halls"], lang), P(lang, "halls")))]
            self.page(lang, ("halls",), title, desc, body, graph, "halls")

    def card_stubs(self):
        """A card listed in discounts.yaml with no confirmed discount today (homat) had a page on the old site;
        its old link (and the 301 onto this host) lands on a short noindex note and the way to every card,
        not a 404. Not in the sitemap, linked from nowhere."""
        confirmed = {c["id"] for c in self.cards}
        for card in self.disc.get("cards") or []:
            cid = card.get("id")
            if not cid or cid in confirmed or not FID.match(cid):
                continue
            for lang in ("ar", "en"):
                cn = card.get("name_ar") if lang == "ar" else card.get("name_en")
                cn = cn or cid
                body = (f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, None))}'
                        f'<h1 class="pt">{esc(cn)}</h1>'
                        f'<p class="lead">{"ما لقينا خصم مؤكد لهالبطاقة حالياً." if lang == "ar" else "We found no confirmed discount for this card right now."} '
                        f'<a href="{P(lang, "cards")}">{"كل خصومات البطاقات" if lang == "ar" else "Every card discount"}</a></p></section>')
                title = (f"{cn} — ما لقينا خصم مؤكد حالياً" if lang == "ar" else f"{cn} — no confirmed discount right now")
                self.page(lang, ("cards", cid), title, title, body, [], "card", nav="cards",
                          path=os.path.join(self.out, *(["en"] if lang == "en" else []), "cards", cid, "index.html"),
                          robots='<meta name="robots" content="noindex">')
