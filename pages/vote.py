"""pages/vote.py — /v/ «أي واحد؟» (W3-P4, MASTER-PLAN §2.12), new, noindex. The server renders only a bare
shell (no film or show data at all: nothing here can leak a card or a city); the 2-4 stubs the link names
are read from the URL's own fragment and drawn client-side (src/js/vote.js), because that fragment never
reaches this server, or any server (WhatsApp's own link preview never sees it either -- the message text
itself lists the options, §2.12).

noindex and out of the sitemap (`path=`, matching build.py's own rule: a page written with an explicit
`path` is never appended to site.urls, so it carries no lastmod and no hreflang pair)."""
import os

from site_kit import NOINDEX, L, P, Page, Pages, Plugin, esc

TITLE = ("أي واحد؟", "Which one?")
CSS = ()
LAZY_JS = ("vote",)
PAGE_CSS = {"vote": ("vote",)}
DIRS = ("v",)

T = {
    "ask": ("وين نروح؟", "Where to?"),
    "desc": ("رابط أرسله لك أحد من قروبك عشان تختارون العرض سوا.",
              "A link a friend sent so the group can pick a show together."),
    "empty": ("ما فهمنا الرابط. اطلب رابط جديد من اللي بعثه.", "This link didn't parse. Ask whoever sent it for a new one."),
    "resend": ("أرسل للقروب", "Send to the group"),
}


def register(site):
    p = VotePages(site)
    return Plugin(pages=[Page(("v",), lang, lambda lang=lang: p.vote_page(lang)) for lang in ("ar", "en")],
                  page_js={"vote": ("vote",)})


class VotePages(Pages):
    def vote_page(self, lang):
        title = L(TITLE, lang)
        desc = L(T["desc"], lang)
        body = (f'<section class="head wrap"><h1 class="pt">{esc(L(T["ask"], lang))}</h1></section>'
                f'<ul class="v-tray wrap" data-v-tray hidden></ul>'
                f'<p class="v-act wrap" data-v-act hidden><button type="button" class="btn ghost" data-v-resend>{esc(L(T["resend"], lang))}</button></p>'
                f'<p class="v-empty wrap" data-v-empty hidden>{esc(L(T["empty"], lang))}</p>')
        # never in the sitemap, so never a hreflang pair either -- an explicit `path` matching the default
        # location (site_kit.Kit.page: `if lang == "ar" and path is None: self.urls.append(parts)`)
        dest = os.path.join(self.out, *(["en"] if lang == "en" else []), "v", "index.html")
        return {"title": title, "desc": desc, "body": body, "kind": "vote", "nav": None,
                "robots": NOINDEX, "path": dest, "graph": []}
