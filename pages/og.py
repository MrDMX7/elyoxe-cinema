"""Feature module (docs/PLUGINS.md): the per-film share image (steps/og.py renders it; roadmap #206)
and the film/cinema share buttons whose links keep the visitor's city+card (roadmap #82).

- `register` copies whichever PNGs steps/og.py left current in data/og/ into out/og/, and points
  each film page's og:image (Twitter falls back to it: src/page.html carries no separate
  twitter:image) at its own file via `site.og_override` (site_kit.py's one hook for this, kept to a
  single additive line — this module owns that hook, per the batch's file split).
- `slots` add a share link to the film page (`film.share`: the hero's «شارك», UI redesign Task 4) and the cinema page
  (`cinema.after_halls`): static markup, same shape as the ticket's own `[data-tk-share]` link
  (site_kit.py's `ticket()`); src/js/share.js (this module's `JS`) rewrites every `[data-share]`
  link's href with the visitor's own `?city=&card=` just before it is used, exactly like
  src/js/ticket.js already does for the ticket's share link.
"""
import os
import shutil
from urllib.parse import quote

from site_kit import ROOT, SITE, P, Plugin, esc, icon

CSS = ("og",)
JS = ("share",)
DIRS = ("og",)


def _share_link(site, lang, url, msg):
    """Same shape as the ticket's own share link (site_kit.py `ticket()`), so src/js/share.js can treat every
    `[data-share]` link the same way: `data-share-url` is what gets `?city=&card=` appended at click time."""
    wa = "https://wa.me/?text=" + quote(msg + "\n" + url, safe="")
    return (f'<p class="pshare"><a class="share" href="{esc(wa)}" rel="noopener" target="_blank" '
            f'data-share data-share-msg="{esc(msg)}" data-share-url="{esc(url)}">'
            f'{esc("أرسلها للقروب" if lang == "ar" else "Send to the group")}</a></p>')


def _film_slot(site, lang, fid):
    """The film hero's «شارك» (UI redesign Task 4): round r3 (owner report, too many controls before the
    schedule) turned it from a ghost button that shared directly into a ghost button that opens a small
    sheet (site_kit's own sheet(), the same component the header's pills use) with the actual actions inside:
    the WhatsApp/native-share link (`_share_link`'s shape: share.js appends the visitor's city and card, and
    uses the phone's share sheet when it has one) and, r3-seo, a second, plain download link for the day's
    Stories card (site.og_story_override, filled by `register` below from data["films"][fid]["og_story"], the
    1080x1920 sibling of the 1200x630 `og` field) — nothing new to click through, just the file, for a visitor
    who wants to post it themselves. Appends to site._sheets exactly as film_bar's own «⋯» sheet does (both
    reset and flushed once per page by site.page(), pages/_core/film.py's film_pages)."""
    f = site.films.get(fid) or {}
    if f.get("status") == "archived":
        return ""  # nothing left to share a live price for
    t, url = site.ftitle(fid, lang), SITE + P(lang, "film", fid)
    wa = "https://wa.me/?text=" + quote(t + "\n" + url, safe="")
    send = (f'<a class="btn ghost" href="{esc(wa)}" rel="noopener" target="_blank" data-share data-share-msg="{esc(t)}" '
            f'data-share-url="{esc(url)}">{icon("share")}{esc("أرسل" if lang == "ar" else "Send")}</a>')
    story = site.og_story_override.get((lang, fid))
    story_link = ""
    if story:
        # a download icon and «صورة ستوري»/"Story image", not the share icon and «ستوري إنستقرام»: the card
        # also serves TikTok, and the link saves a file rather than opening a share sheet (review fix)
        story_link = (f'<a class="btn ghost" href="{esc(story)}" download rel="noopener">{icon("download")}'
                      f'{esc("صورة ستوري" if lang == "ar" else "Story image")}</a>')
    body = f'<div class="sec share-opts">{send}{story_link}</div>'
    site._sheets.append(site.sheet("sheet-share", ("شارك", "Share"), body, lang))
    return (f'<button type="button" class="btn ghost" data-sheet-open="sheet-share" aria-haspopup="dialog">'
            f'{icon("share")}{esc("شارك" if lang == "ar" else "Share")}</button>')


def _cinema_slot(site, lang, cid):
    cn = site.cname(cid, lang)
    city = (site.cinemas.get(cid) or {}).get("city")
    if not city:
        return ""
    return _share_link(site, lang, SITE + P(lang, city, cid), cn)


def register(site):
    out_dir = os.path.join(ROOT, "data", "og")
    site.og_story_override = {}   # (lang, fid) -> full URL of the day's 1080x1920 Stories card, or absent
    for fid, f in site.films.items():
        og = f.get("og")
        if isinstance(og, dict):
            for lang, name in og.items():
                src_path = os.path.join(out_dir, name)
                if not os.path.isfile(src_path):
                    continue
                dest = os.path.join(site.out, "og", name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src_path, dest)
                site.og_override[(lang, ("film", fid))] = f"{SITE}/og/{name}"
        story = f.get("og_story")
        if isinstance(story, dict):
            for lang, name in story.items():
                src_path = os.path.join(out_dir, name)
                if not os.path.isfile(src_path):
                    continue
                dest = os.path.join(site.out, "og", name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src_path, dest)
                site.og_story_override[(lang, fid)] = f"{SITE}/og/{name}"

    return Plugin(slots={
        "film.share": lambda site, lang, fid: _film_slot(site, lang, fid),
        "cinema.after_halls": lambda site, lang, cid: _cinema_slot(site, lang, cid),
    })
