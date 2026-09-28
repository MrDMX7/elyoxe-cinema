"""The edges: the 404 and the service worker's offline page (pages/core.py's, moved as they were by W1-P1).
Owner in Wave 2: W2-P10 (MASTER-PLAN §6.2).

Methods of pages.core.CorePages: `self` is a Pages, which reads everything else (self.page, self.poster,
self.shows ...) through to the site."""
from site_kit import *  # noqa: F401,F403  (the names these pages were written against)


class EdgePages:
    # -------------------------------------------------- 404
    def not_found(self):
        body = (f'<section class="head wrap nf"><h1 class="pt">ما لقينا هالصفحة</h1>'
                f'<p class="lead">يمكن الفيلم نزل من السينما، أو الرابط تغيّر. <a href="/">الأفلام المعروضة اليوم</a>.</p>'
                f'<p class="lead" lang="en" dir="ltr">We couldn’t find this page. <a href="/en/">Films showing today, in English</a>.</p></section>'
                + self.slot("notfound.body", "ar"))   # the leader's rows (W1-P1's slot, W2-P2/W2-P10)
        self.page("ar", (), "ما لقينا هالصفحة — سينما", "الصفحة غير موجودة.", body, [], "404",
                  path=os.path.join(self.out, "404.html"), robots='<meta name="robots" content="noindex">')

    def offline(self):
        """The service worker's fallback when a page is not cached and there is no network: one self-contained
        file (its style inline, system fonts), so it looks right on the first offline hit with nothing cached."""
        page = """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ما في إنترنت — سينما</title><meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#0F0B0C"><meta name="color-scheme" content="dark">
<style>
body{margin:0;min-height:100vh;background:#0F0B0C radial-gradient(280px 220px at 70% 90px,rgba(122,22,38,.6),rgba(15,11,12,0)) no-repeat;color:#F1EAE0;
font:16px/1.7 "Readex Pro","Segoe UI",Tahoma,system-ui,sans-serif}
main{max-width:40rem;margin:0 auto;padding:48px 20px}
.m{font-weight:700;font-size:34px;color:#E2B659;text-decoration:none}
h1{font-size:36px;line-height:1.15;margin:40px 0 12px}
p{margin:0 0 14px;color:#C9BDAE}
a{color:#F1EAE0;text-decoration-color:#A89C8E;text-underline-offset:.2em}
[lang=en]{direction:ltr;text-align:left;font-size:14px;color:#A89C8E}
</style></head><body><main>
<a class="m" href="/">سينما</a>
<h1>ما في إنترنت الحين</h1>
<p>الصفحات اللي فتحتها قبل تشتغل بدون نت. ارجع لها، أو جرّب مرة ثانية لين يرجع الاتصال.</p>
<p><a href="/">الأفلام المعروضة اليوم</a></p>
<p lang="en">You are offline. Pages you opened before still work. <a href="/en/">Films today, in English</a>.</p>
</main></body></html>
"""
        # the board's cached rows (W1-P1's slot, W2-P2/W2-P10): self-contained markup, before the English line
        page = page.replace('<p lang="en">', self.slot("offline.body", "ar") + '<p lang="en">', 1)
        self.write(os.path.join(self.out, "offline.html"), page)
