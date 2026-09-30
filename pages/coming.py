"""pages/coming.py (Task 2, design spec A): «نازل الخميس» — /coming/ (+ /en/), a grid of films the
chains have announced grouped by their release Thursday, with a countdown only for films that
have a real release date (undated films sit in their own "date to be announced" group).

Data: steps/coming.py's data["coming"][fid] = {"title","title_ar","release_date","poster",
"trailer","genres","chains"} -- these are NOT in `site.films` (they aren't showing yet), so this
page never calls site.poster()/site.film_tile() (those index self.films by fid); it renders its
own small card directly from the coming-soon record.

The nav key "thursday" re-points the built-in «نازل الخميس» header link (PLUGINS.md's nav table)
from the home page to here.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import re

from genres import GENRES, genre_keys
from normalize import film_fid
from site_kit import FILMS_AR, HOME_T, Emit, L, NavItem, P, Page, Pages, Plugin, ar_count, esc, hue, human_date, rel

TITLE = ("قريباً في السينما", "Coming soon")   # owner rename 2026-09-30 (site_kit.s_thursday_h matches; the
                                                # phone tab bar keeps the short «قريباً», no room for this at 344px)
CSS = ("coming",)
LAZY_JS = ()
DIRS = ("coming", "cal")

# «سلسلة» declines exactly like «سينما» (CINEMAS_AR in site_kit): one, two, 3-10 plural, 11+ singular-with-number.
CHAINS_AR = ("سلسلة وحدة", "سلسلتين", "سلاسل", "سلسلة")


def _thursday_of(iso_date: str) -> str:
    """The Thursday that opens the release week `iso_date` falls in (UAE releases land on Thursdays): Monday to
    Wednesday belong to the coming Thursday, Thursday to itself, and Friday to Sunday to the Thursday before --
    a Friday 2 October release opened with the 1 October slate, not the 8 October one."""
    d = dt.date.fromisoformat(iso_date)
    return (d + dt.timedelta(days=3 - d.weekday())).isoformat()


_RERELEASE = re.compile(r"-?re-?release$")


def _title_key(title: str) -> str:
    """normalize.film_fid's slug of the decoded title, without hyphens or a re-release tag: the
    chains' own spellings of one film ("Don&#39;t…", "Don't…", "Dont… (Telugu)") meet here."""
    return _RERELEASE.sub("", film_fid(html.unescape(title or ""))).replace("-", "")


def _edits(a: str, b: str) -> int:
    """Levenshtein distance (the titles are short; a plain two-row table is enough)."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _same_title(a: str, b: str) -> bool:
    """One film under two spellings (final review M1: "The Legendaires"/"The Legendaries"): the same
    key, or at most 2 edits apart when both keys are 10+ letters long and carry the same numbers
    (so "Golmaal 4"/"Golmaal 5" and short titles like "Wake"/"Make" never fold)."""
    ka, kb = _title_key(a), _title_key(b)
    if ka == kb:
        return bool(ka)
    if min(len(ka), len(kb)) < 10 or re.findall(r"\d+", ka) != re.findall(r"\d+", kb):
        return False
    return _edits(ka, kb) <= 2


def fold_near_duplicates(coming: dict) -> list:
    """[(fid, film)] with near-identical titles on the same release date merged into one card: the
    spelling most chains use (then the shorter fid) names it, chains and genres are the union, and
    poster/trailer come from whichever entry has them. Titles are HTML-unescaped once for display."""
    groups: list[list] = []
    for fid, f in sorted(coming.items()):
        for g in groups:
            if g[0][1].get("release_date") == f.get("release_date") and _same_title(g[0][1]["title"], f["title"]):
                g.append((fid, f))
                break
        else:
            groups.append([(fid, f)])
    out = []
    for g in groups:
        g.sort(key=lambda kv: (-len(kv[1].get("chains") or []), len(kv[0]), kv[0]))
        fid, base = g[0]
        f = dict(base, title=html.unescape(base["title"]),
                 title_ar=html.unescape(base["title_ar"]) if base.get("title_ar") else base.get("title_ar"))
        f["chains"] = sorted({c for _, x in g for c in (x.get("chains") or [])})
        f["genres"] = [x for _, m in g for x in (m.get("genres") or [])]
        for k in ("poster", "trailer", "title_ar"):
            if not f.get(k):
                f[k] = next((m[k] for _, m in g if m.get(k)), f.get(k))
        out.append((fid, f))
    return out


def genre_labels(raw, lang) -> list:
    """The chains' raw genre words through genres.py's vocabulary; a word it does not know is left
    out (never printed in English on the Arabic page, never shown as «أخرى»)."""
    return [GENRES[k][0 if lang == "ar" else 1] for k in genre_keys(raw or []) if k != "other"]


def _ics_esc(s) -> str:
    return str(s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _ics_fold(line: str) -> str:
    """RFC 5545 §3.1: no content line over 75 octets, continued by CRLF + one leading space (src/js/plan.js's
    planFold is its twin) -- folded on UTF-8 bytes, never inside a multi-byte character."""
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    out, start, limit = [], 0, 75
    while start < len(b):
        end = min(start + limit, len(b))
        while end > start and end < len(b) and (b[end] & 0xC0) == 0x80:
            end -= 1
        out.append(b[start:end].decode("utf-8"))
        start = end
        limit = 74
    return "\r\n ".join(out)


def register(site):
    p = ComingPages(site)
    return Plugin(
        pages=[Page(("coming",), lang, lambda lang=lang: p.coming_page(lang)) for lang in ("ar", "en")] + [Emit(p.cal_ics)],
        data={"data/coming.json": lambda: {fid: f for fid, f in (site.d.get("coming") or {}).items()}},
        nav=[NavItem("thursday", href=lambda lang: P(lang, "coming"))],
        slots={"home.after_board": lambda site, lang, **ctx: ComingPages(site)._band(lang)})


class ComingPages(Pages):
    def _groups(self):
        """{thursday-iso|None: [(fid, film), ...]} sorted by date, undated (None) group last."""
        coming = self.d.get("coming") or {}
        groups: dict = {}
        for fid, f in fold_near_duplicates(coming):
            key = _thursday_of(f["release_date"]) if f.get("release_date") else None
            groups.setdefault(key, []).append((fid, f))
        for key in groups:
            groups[key].sort(key=lambda kv: kv[1]["title"])
        return dict(sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0] or "")))

    def _countdown(self, release_date, lang):
        days = (dt.date.fromisoformat(release_date) - self.now.date()).days
        if days < 0:
            return ""
        if days == 0:
            return "اليوم" if lang == "ar" else "Today"
        if days == 1:
            return "بكرة" if lang == "ar" else "Tomorrow"
        return ("بعد " + ar_count(days, ("يوم", "يومين", "أيام", "يوم"))) if lang == "ar" else f"In {days} days"

    def _card(self, fid, f, lang):
        pc = hue(fid)
        img = (f'<span class="cs-p img" style="--pc:{pc}"><img src="{esc(rel(f["poster"]))}" alt="" loading="lazy" width="200" height="300"></span>'
               if f.get("poster") else f'<span class="cs-p" style="--pc:{pc}"><span class="cs-t">{esc(f["title"])}</span></span>')
        title_ar = f.get("title_ar")
        titles = (f'<span class="cs-n">{esc(f["title"])}</span>' + (f'<bdi class="cs-ar">{esc(title_ar)}</bdi>' if title_ar and lang == "ar" else "")
                  if lang == "en" or not title_ar else f'<span class="cs-n">{esc(title_ar)}</span><bdi class="cs-ar" lang="en">{esc(f["title"])}</bdi>')
        sep = "، " if lang == "ar" else ", "
        meta = sep.join(genre_labels(f.get("genres"), lang)[:2])
        # the countdown prints once, in the week's own heading (--dim), never on a card (§2.6): 111 gold
        # countdowns was the thing being fixed
        chains = sep.join(self.h.chain_name(c, lang) for c in sorted(f.get("chains") or []))
        trailer = (f'<a class="cs-yt" href="https://www.youtube-nocookie.com/embed/{esc(f["trailer"])}" '
                   f'data-trailer="{esc(f["trailer"])}" rel="noopener" target="_blank">'
                   f'{"الإعلان" if lang == "ar" else "Trailer"}</a>') if f.get("trailer") else ""
        return (f'<li class="cs-card">{img}<div class="cs-info">{titles}'
                + (f'<span class="cs-meta">{esc(meta)}</span>' if meta else "")
                + (f'<span class="cs-chains">{esc(chains)}</span>' if chains else "")
                + (f'<div class="cs-act">{trailer}</div>' if trailer else "") + '</div></li>')

    def _week_summary(self):
        """The nearest dated release week (today or later): (thursday-iso, [(fid, film)...]), or (None, [])
        when every announced film still reads "date to be announced". The masthead's and the home band's
        one real number (§2.6): never a fabricated screen count, only what the chains themselves gave.
        Floored on the current release week's own Thursday (`_thursday_of(self.today)`), not on
        `self.today` itself -- on Friday/Saturday `self.today` is already past this week's Thursday, so
        a literal `key >= self.today` skipped the live week and jumped to next Thursday (fix round,
        review Important #5)."""
        floor = _thursday_of(self.today)
        for key, items in self._groups().items():
            if key and key >= floor:
                return key, items
        return None, []

    def _mast_lines(self, lang):
        """(word, headline, intro|None): the masthead's paper marquee content (§2.6), templated from data so
        the copy stays factual across weeks and passes the dialect gate once. `intro` names the week's lead
        title (the most chains announcing it) and how many chains carry it -- real numbers only, never a
        per-cinema screen count we were never given."""
        key, items = self._week_summary()
        word = "الخميس" if lang == "ar" else "Thursday"
        if not key:
            return word, None, None
        n = len(items)
        count_s = ar_count(n, FILMS_AR) if lang == "ar" else (f"{n} film" if n == 1 else f"{n} films")
        headline = f"{human_date(key, lang)}، {count_s}" if lang == "ar" else f"{human_date(key, lang)}, {count_s}"
        lead_fid, lead = max(items, key=lambda kv: len(kv[1].get("chains") or []))
        chains_n = len(lead.get("chains") or [])
        intro = None
        if chains_n:
            lead_title = lead.get("title_ar") if lang == "ar" and lead.get("title_ar") else lead["title"]
            chains_s = ar_count(chains_n, CHAINS_AR) if lang == "ar" else (f"{chains_n} chain" if chains_n == 1 else f"{chains_n} chains")
            intro = (f"أكبر نزلة: {lead_title}، معلنة عند {chains_s}." if lang == "ar"
                     else f"Biggest opener: {lead_title}, announced by {chains_s}.")
        return word, headline, intro

    def _masthead(self, lang):
        """The /coming/ page's own paper marquee (§2.6): «الخميس» in Markazi at 96/160 px, the date+count
        line, the templated intro, and «الأحكام تنزل من الخميس للسبت» once. Under 240 px on a phone: one big
        word plus three short lines, no card grid inside it."""
        word, headline, intro = self._mast_lines(lang)
        if not headline:
            return ""
        note = "الأحكام تنزل من الخميس للسبت." if lang == "ar" else "Verdicts land Thursday to Saturday."
        # the .ics subscribe link (§2.6, cal_ics below): iPhone-only, because Android's Google Calendar
        # can't subscribe by a plain URL. `hidden` by default; a tiny inline check reveals it only on
        # iPhone/iPad, never announced to anyone else (review Important #7 -- the file was correct and
        # deployed, just never linked from this page).
        ics = "تابع الخميس بالتقويم" if lang == "ar" else "Subscribe to Thursdays"
        return ('<div class="cs-mast paper lit">'
                f'<p class="cs-mast-w">{esc(word)}</p>'
                f'<p class="cs-mast-d">{esc(headline)}</p>'
                + (f'<p class="cs-mast-i">{esc(intro)}</p>' if intro else "")
                + f'<p class="cs-mast-n">{esc(note)}</p>'
                + f'<p class="cs-mast-ics" hidden><a href="/cal/thursday.ics">{esc(ics)}</a></p>'
                + '<script>(function(d){if(/iPhone|iPad/.test(navigator.userAgent)){'
                + 'd=document.currentScript.previousElementSibling;if(d)d.hidden=false}})()</script>'
                + '</div>')

    def _band(self, lang):
        """home.after_board (§1.2 #2, §2.6): the compact Thursday band, only in the two live phases
        (Kit.week_phase: «wed-eve» from Wed 18:00, «thu-sat» through Sat 23:59) -- Sunday to Wednesday
        the «نازل الخميس» row carries the same news instead (pages/_core/home.py's own week_phase gate)."""
        if self.week_phase(self.now) not in ("wed-eve", "thu-sat"):
            return ""
        word, headline, _ = self._mast_lines(lang)
        if not headline:
            return ""
        return (f'<a class="cs-band paper lit" href="{esc(P(lang, "coming"))}">'
                f'<span class="cs-band-w">{esc(word)}</span><span class="cs-band-d">{esc(headline)}</span>'
                f'<span class="all-l">{esc(L(HOME_T["all"], lang))}</span></a>')

    def cal_ics(self):
        """/cal/thursday.ics (§2.6, iPhone-only channel: Android's Google Calendar can't subscribe by URL) --
        one VEVENT per known Thursday (today or later), release-day 10:00 Asia/Dubai (the same marker time
        R3's per-film «نبّهني» uses, src/js/plan.js), naming the week's openers and how many have a verdict
        yet. deploy.sh (W2-P7's own pass) serves it as text/calendar, 300 s cache, never immutable."""
        events = []
        for key, items in self._groups().items():
            if not key or key < self.today:
                continue
            titles = [f.get("title_ar") or f["title"] for _, f in items]
            summary = "قريباً في السينما: " + "، ".join(titles[:3]) + (f" و{len(titles) - 3} غيرها" if len(titles) > 3 else "")
            known = [(f.get("verdict") or {}).get("verdict") for _, f in items if (f.get("verdict") or {}).get("verdict") not in (None, "unknown")]
            desc = "الحكم بعده" if not known else f"{len(known)} من {len(items)} صدر حكمهم"
            dt_ = key.replace("-", "")
            events += ["BEGIN:VEVENT", f"UID:{key}-thursday@cinema.elyoxe.com",
                       f"DTSTAMP:{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')}Z",
                       f"DTSTART;TZID=Asia/Dubai:{dt_}T100000", f"DTEND;TZID=Asia/Dubai:{dt_}T110000",
                       f"SUMMARY:{_ics_esc(summary)}", f"DESCRIPTION:{_ics_esc(desc)}", "END:VEVENT"]
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Elyoxe//Cinema//AR", "CALSCALE:GREGORIAN",
                 f"X-WR-CALNAME:{_ics_esc('قريباً في السينما')}",
                 "BEGIN:VTIMEZONE", "TZID:Asia/Dubai", "BEGIN:STANDARD", "DTSTART:19700101T000000",
                 "TZOFFSETFROM:+0400", "TZOFFSETTO:+0400", "END:STANDARD", "END:VTIMEZONE",
                 *events, "END:VCALENDAR"]
        text = "\r\n".join(_ics_fold(l) for l in lines) + "\r\n"
        self.write(os.path.join(self.out, "cal", "thursday.ics"), text)

    def coming_page(self, lang):
        title = L(TITLE, lang)
        desc = ("الأفلام النازلة قريباً في سينمات الإمارات، حسب أسبوع نزولها." if lang == "ar"
                else "Films announced by UAE cinema chains, grouped by the week they open.")
        head = (f'<section class="head wrap">{self.crumbs(lang, (title, None))}<h1 class="pt">{esc(title)}</h1>'
                f'<p class="lead">{esc(desc)}</p></section>' + self._masthead(lang))
        groups = self._groups()
        sections = []
        for key, items in groups.items():
            if key:
                heading = human_date(key, lang)
                cd = self._countdown(key, lang)
            else:
                heading = "التاريخ لاحقاً" if lang == "ar" else "Date to be announced"
                cd = ""
            cd_html = f'<p class="cs-cd">{esc(cd)}</p>' if cd else ""
            cards = "".join(self._card(fid, f, lang) for fid, f in items)
            sections.append(f'<section class="wrap cs-week"><h2>{esc(heading)}</h2>{cd_html}<ul class="cs-grid">{cards}</ul></section>')
        if sections:
            body = head + "".join(sections)
        else:
            empty = "ما عندنا أفلام نازلة قريباً معروفة الحين." if lang == "ar" else "Nothing announced by the chains yet."
            body = head + f'<section class="wrap"><p class="empty">{esc(empty)}</p></section>'
        graph = [self.breadcrumb_ld(lang, (title, P(lang, "coming")))]
        return {"title": title, "desc": desc, "body": body, "kind": "coming", "nav": "thursday", "graph": graph}
