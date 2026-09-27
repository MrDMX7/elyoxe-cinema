import json, pathlib
H = pathlib.Path(__file__).parent
F = json.load(open(H.parent / "mock_films.json", encoding="utf-8"))
SITE = "https://cinema.elyoxe.com"
G = {"action": "أكشن", "thriller": "إثارة", "adventure": "مغامرة", "crime": "جريمة", "horror": "رعب", "comedy": "كوميدي",
     "drama": "دراما", "family": "عائلي", "animation": "أنيميشن", "fantasy": "خيال", "scifi": "خيال علمي", "romance": "رومانسي", "sport": "رياضة"}
ICON = {
 "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>',
 "home": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 11 12 4l8 7v9h-5v-6H9v6H4z"/></svg>',
 "pin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 21s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/></svg>',
 "cal": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="5" width="16" height="15"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>',
 "play": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4v16l13-8z"/></svg>',
 "sliders": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>',
 "share": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12M7 8l5-5 5 5M5 14v6h14v-6"/></svg>',
}
def name(f): return f["ta"] or f["t"]
def poster(f): return SITE + f["p"].replace("-342", "-684")
def tile(f, price=None, tag=None):
    pr = f'<span class="num">{price}</span> درهم' if price else "السعر في الشباك"
    tg = f'<span class="tag">{tag}</span>' if tag else ""
    return f'<a class="tile" href="film.html"><div class="p" style="background-image:url({poster(f)});background-color:{f["col"]}">{tg}</div><div class="t">{name(f)}</div><div class="m">من {pr}</div></a>'
PR = ["33.60", "36.80", "33.60", "28.00", "33.60", "36.80", "30.00", "33.60", "36.80", "28.00", "33.60", "33.60"]
def top(active="home", solid=False):
    return f'''<header class="top{' solid' if solid else ''}"><a class="mark" href="home.html">سينما</a>
<nav class="links"><a href="home.html" {'aria-current="page"' if active=="home" else ''}>الرئيسية</a><a href="#">السينمات</a><a href="#">نازل قريب</a><a href="#">الأسعار والبطاقات</a></nav>
<div class="tools"><button class="icon" aria-label="بحث">{ICON["search"]}</button><button class="pill">العين</button><button class="pill">فزعة</button><a class="en" href="#">English</a></div></header>'''
TABS = f'''<nav class="tabs"><a aria-current="page" href="#">{ICON["home"]}الرئيسية</a><a href="#">{ICON["pin"]}السينمات</a><a href="#">{ICON["cal"]}نازل قريب</a><a href="#">{ICON["search"]}بحث</a></nav>'''
def page(body, title):
    return f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><link rel="stylesheet" href="mock.css"></head><body>{body}</body></html>'

by = {f["fid"]: f for f in F}
hb = by["heart-of-the-beast"]
yes = [f for f in F if f["v"] == "yes"]
fam = [f for f in F if f["fam"]]
arabic_row = [f for f in F if f["ta"]]
def strip(fs, n=12, tag=None, off=0): return '<div class="strip">' + "".join(tile(f, PR[(i + off) % len(PR)], tag) for i, f in enumerate(fs[:n])) + "</div>"
def row(title, fs, sub="", more="الكل", **k):
    s = f'<span class="sub">{sub}</span>' if sub else ""
    return f'<section class="row"><div class="row-h"><h2>{title}</h2>{s}<a href="#" style="margin-inline-start:auto">{more}</a></div>{strip(fs, **k)}</section>'
NEAR = [("heart-of-the-beast", "17:15", "بعد 25 د", "ستار الفوعة", "3.1 كم"), ("resident-evil", "17:30", "بعد 40 د", "ستار بوادي مول", "4.4 كم"),
        ("avengers-endgame-encore", "17:40", "بعد 50 د", "ڤوكس الجيمي مول", "2.2 كم"), ("spider-man-brand-new-day", "18:00", "", "ستار الفوعة", "3.1 كم"), ("the-odyssey", "18:15", "", "ستار بوادي مول", "4.4 كم")]
near = '<section class="row"><div class="row-h"><h2>يبدأ قريب منك</h2><span class="sub">العين، الحين 16:50</span></div><div class="strip">' + "".join(
    f'<a class="near" href="film.html"><div class="p" style="background-image:url({poster(by[fid])})"></div><div><div class="tm num">{tm}<small>{s}</small></div><div class="t">{name(by[fid])}</div><div class="c">{c}  <span class="num">{d}</span></div></div></a>'
    for fid, tm, s, c, d in NEAR) + "</div></section>"
bill = f'''<section class="bill"><img class="bd" src="hero-heart.jpg" alt="">
<div class="bill-in"><div class="eyebrow">الأكثر عرضاً في العين الليلة</div><h1>قلب الوحش</h1>
<p class="verdict"><b>يستاهل.</b> براد بيت مع كلبه أودين في رحلة نجاة بأدغال ألاسكا، والنقاد يوصفونه من أحسن أفلام David Ayer.</p>
<div class="facts"><span class="rt num">Rotten Tomatoes 88%</span><span><span class="num">120</span> دقيقة</span><span>PG13</span><span>أكشن، إثارة</span></div>
<div class="cta"><a class="btn main" href="film.html">الأوقات والأسعار <span class="num">من 33.60</span></a><button class="btn ghost">{ICON["play"]}الإعلان</button></div></div>
<div class="dots"><i class="on"></i><i></i><i></i><i></i><i></i></div></section>'''
all_grid = '<section class="all"><div class="all-h"><h2>كل الأفلام <span class="num" style="font-family:var(--body);font-size:15px;color:var(--seat)">66</span></h2>' \
    f'<button class="chip">{ICON["sliders"].replace("<svg","<svg width=16 height=16")}تصفية</button><button class="chip">الترتيب: الأقرب وقتاً</button></div>' \
    '<div class="grid">' + "".join(tile(f, PR[i % 12]) for i, f in enumerate(F[:21])) + "</div></section>"
foot = '<footer class="foot"><span class="mark">سينما</span><a href="#">السينمات</a><a href="#">البطاقات والخصومات</a><a href="#">من وين الأسعار</a><a href="#">أسئلة</a><a href="#">English</a></footer>'
home_body = top() + "<main>" + bill + near + row("الأكثر عرضاً الليلة", F, sub="") + row("يستاهل", yes, sub="حكمنا من تقييمات النقاد والجمهور", off=3) \
    + row("أرخص لك الليلة", F[4:], sub="بعد خصم فزعة", off=6) + row("للعائلة", fam, off=2) + row("نازل الخميس", F[12:], tag="الخميس", more="كل القادم") \
    + row("آخر فرصة", F[14:], tag="آخر أسبوع", off=5) + row("عربي", arabic_row, off=1) + all_grid + "</main>" + foot + TABS
(H / "home.html").write_text(page(home_body, "سينما"), encoding="utf-8")

sheet = '''<div class="scrim"></div><aside class="sheet"><div class="grab"></div><h3>تصفية</h3>
<div class="sec"><div class="l">النوع</div><div class="opts"><button class="chip on">الكل</button><button class="chip">أكشن</button><button class="chip">رعب</button><button class="chip">كوميدي</button><button class="chip">عائلي</button><button class="chip">دراما</button><button class="chip">أنيميشن</button><button class="chip">خيال علمي</button></div></div>
<div class="sec"><div class="l">مع منو رايح؟</div><div class="opts"><button class="chip">بروحي</button><button class="chip on">العيال</button><button class="chip">الربع</button><button class="chip">الأهل</button></div></div>
<div class="sec"><div class="l">لازم يخلص قبل</div><div class="opts"><button class="chip">10 الليل</button><button class="chip on">12 الليل</button><button class="chip">ما يهم</button></div></div>
<div class="sec"><div class="l">اللغة</div><div class="opts"><button class="chip on">الكل</button><button class="chip">إنجليزي</button><button class="chip">عربي</button><button class="chip">هندي</button><button class="chip">مليالم</button></div></div>
<div class="sec"><div class="l">الترتيب</div><div class="opts"><button class="chip on">الأقرب وقتاً</button><button class="chip">الأرخص</button><button class="chip">الأعلى تقييماً</button><button class="chip">الأقرب مكاناً</button></div></div>
<div class="sec"><label class="sw">لا تعرض عروض وقت الصلاة<i></i></label></div>
<div class="go"><button class="btn ghost">مسح</button><button class="btn main">اعرض 23 فيلم</button></div></aside>'''
(H / "home-sheet.html").write_text(page(home_body + sheet, "سينما"), encoding="utf-8")

def times(ts, sel=None, gone=0, soon=None):
    out = []
    for i, (t, h, p) in enumerate(ts):
        cls = "tb" + (" gone" if i < gone else "") + (" sel" if t == sel else "") + (" soon" if t == soon else "")
        out.append(f'<button class="{cls}"><span class="h num">{t}</span><span class="k">{h}</span><span class="pr num">{p}</span></button>')
    return '<div class="times">' + "".join(out) + "</div>"
C = [("ستار الفوعة", "3.1 كم", [("16:00", "ATMOS", "33.60"), ("17:15", "SUITES", "84.00"), ("18:00", "ATMOS", "33.60"), ("18:45", "عادي", "33.60"), ("19:15", "SUITES", "84.00"), ("20:00", "ATMOS", "33.60"), ("21:15", "SUITES", "84.00"), ("22:00", "ATMOS", "33.60")], 0, "17:15"),
     ("ڤوكس الجيمي مول", "2.2 كم", [("15:15", "عادي", "46.00"), ("16:30", "THEATRE", "195.00"), ("17:40", "عادي", "46.00"), ("19:00", "THEATRE", "195.00"), ("20:10", "عادي", "46.00"), ("21:30", "THEATRE", "195.00"), ("22:30", "عادي", "46.00")], 2, None),
     ("ستار بوادي مول", "4.4 كم", [("17:00", "PREMIUM", "46.20"), ("18:00", "عادي", "33.60"), ("19:00", "SUITES", "84.00"), ("20:00", "عادي", "33.60"), ("21:00", "SUITES", "84.00"), ("21:30", "PREMIUM", "46.20"), ("22:00", "عادي", "33.60")], 0, None)]
def sched(sel=None):
    return "".join(f'<div class="cin"><div class="cin-h"><h3>{n}</h3><span class="d num">{d}</span><a href="#">الخريطة</a></div>{times(ts, sel, g, s)}</div>' for n, d, ts, g, s in C) \
        + '<p class="more">4 سينمات ثانية في العين</p>'
fhero = f'''<section class="fhero"><img class="bd" src="hero-heart2.jpg" alt=""><div class="fhero-in"><div class="poster" style="background-image:url({poster(hb)})"></div><div>
<h1>قلب الوحش</h1><div class="en-t">Heart of the Beast  <span class="num">2026</span></div>
<p class="verdict"><b>يستاهل.</b> براد بيت مع كلبه أودين في رحلة نجاة بأدغال ألاسكا، وقلب الوحش ياب بتقييم نقاد 88%. النقاد يوصفونه من أحسن أفلام David Ayer، وقصة الإنسان والكلب توّجع القلب بصدق.</p>
<div class="facts"><span class="rt num">Rotten Tomatoes 88%  الجمهور 96%</span><span><span class="num">120</span> دقيقة</span><span>PG13</span><span>أكشن، إثارة، مغامرة</span></div>
<div class="cta"><button class="btn ghost">{ICON["play"]}الإعلان</button><button class="btn ghost">{ICON["share"]}شارك</button><button class="btn ghost">قارن</button></div></div></div></section>'''
bar = '<div class="bar"><button class="day on"><b>اليوم</b>الأحد 27</button><button class="day"><b>بكرة</b>الاثنين 28</button><button class="day"><b>الثلاثاء</b>29</button><button class="day"><b>الأربعاء</b>30</button><button class="day"><b>الخميس</b>1</button></div>'
ticket = '''<aside class="ticket"><div class="k">تذكرتك</div><div class="h num">17:15</div><div style="font-size:14px;margin-block:6px 12px">ستار الفوعة، SUITES</div>
<div class="rw"><span>السعر</span><span class="num">105.00</span></div><div class="rw"><span>فزعة 20%، من الشباك فقط</span><span class="num">−21.00</span></div>
<div class="rw" style="border:0;align-items:baseline"><span>لكل شخص</span><span class="tot num">84.00</span></div>
<a class="btn main" href="#">احجز من موقع ستار</a><div class="alt"><a href="#">الخريطة</a><a href="#">Waze</a><a href="#">شارك التذكرة</a><a href="#">المقاعد</a></div></aside>'''
tabsx = '<nav class="tabsx"><a class="on" href="#">عن الفيلم</a><a href="#">الطاقم</a><a href="#">شي يشبه</a><a href="#">فيلمين ورا بعض</a><a href="#">قارن</a></nav>'
about = '''<section class="about"><p>جندي قوات خاصة متقاعد يمشي 58 ميلاً في براري ألاسكا مع كلبه الحربي بعد ما طاحت طيارتهم المائية.</p>
<dl class="kv"><dt>المخرج</dt><dd>David Ayer</dd><dt>البطولة</dt><dd>Brad Pitt، J. K. Simmons، Anna Lambe</dd><dt>اللغة</dt><dd>إنجليزي، ترجمة عربي</dd><dt>في الإمارات</dt><dd>7 سلاسل، 555 عرض هالأسبوع</dd></dl></section>'''
film_body = top("film", solid=True) + "<main>" + fhero + bar + f'<div class="lay"><div>{sched("17:15")}</div>{ticket}</div>' + tabsx + about + "</main>" + foot
(H / "film.html").write_text(page(film_body, "قلب الوحش"), encoding="utf-8")
dock = '<div class="dock"><div><div class="h num">84.00 <span style="font-size:13px;font-weight:400">درهم</span></div><div class="s">17:15 ستار الفوعة، SUITES، بعد فزعة</div></div><a class="btn" href="#">التفاصيل والحجز</a></div>'
(H / "film-sel.html").write_text(page(film_body + dock, "قلب الوحش"), encoding="utf-8")
print("ok")
