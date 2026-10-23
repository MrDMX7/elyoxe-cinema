"""«سينما» as an app (owner 2026-10-18): «إعادة تصميم… نفس الميلس كتطبيق: سهولة الاستخدام والـsmoothness والبساطة».

Two lists at the top, swipe between them like the Meylis tabs:
  الأفلام    genre chips (الكل، أكشن، كوميديا، رعب…) over a poster grid — the poster, the name, the runtime and the IMDb
             score (else the critics' score); a tap opens the film.
  السينمات   the city (or «الأقرب» from the phone's location, nearest first), the cinemas as cards; a tap opens the
             cinema: its films with their posters and showtimes, today or tomorrow.
The film page carries everything: the screen (trailer still), the facts, our verdict, the story, «اسأل الفيلم», and
where it shows — by city, cinema by cinema, every time a button that raises the ticket from the bottom.

Static pages (every film and every cinema is a real page for Google and for the back button), moved between with
the Meylis numbers: a page slides in from the side in 300 ms, back reverses it, a sheet rises from the bottom; the
next page is prerendered, so a tap is instant. One small script for what needs the phone: the swipe between the two
lists, the genre chips, location, the day switch, past times, the ticket and «اسأل الفيلم».

    python app/build_app.py --data data/latest.json --out out_app [--base /next/]
`--base` prefixes every link and asset (a preview at /next/ beside the live site); posters and data stay at the
site's root.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from site_kit import Kit, Halls, load_discounts  # noqa: E402

E = lambda s: html.escape(str(s if s is not None else ""), quote=True)  # noqa: E731
SITE = "https://cinema.elyoxe.com"
ASK_API = "https://fndms9v719.execute-api.ap-south-1.amazonaws.com/"

CITIES = [("dubai", "دبي"), ("abu-dhabi", "أبوظبي"), ("sharjah", "الشارقة"), ("al-ain", "العين"), ("ajman", "عجمان"),
          ("ras-al-khaimah", "رأس الخيمة"), ("fujairah", "الفجيرة"), ("umm-al-quwain", "أم القيوين")]
CITY = dict(CITIES)
INDIAN = {"Hindi", "Tamil", "Malayalam", "Telugu", "Kannada", "Punjabi", "Marathi", "Bengali"}
# the chips, in the order a person scans them; each matches a film by its genres (or its language)
# steps/content_warnings.py's keys in the page's words; DEATHS give part of the story away, so they sit behind a tap
FAMILY = {"sex": "مشاهد جنسية", "nudity": "عري", "sexual_assault": "اعتداء جنسي", "blood": "دم وعنف",
          "body_horror": "رعب جسدي", "torture": "تعذيب", "guns": "عنف بالسلاح", "jump_scares": "لقطات تخرّع فجأة",
          "ghosts": "أشباح", "possession": "مسّ", "demons": "شياطين", "drugs": "مخدرات", "alcohol": "شرب خمر",
          "smoking": "تدخين"}
DEATHS = {"child_dies": "يموت طفل", "animal_dies": "يموت حيوان"}
# the UAE rating in words — the official guide, first in «للعائلة» (2026-10-20: a cartoon rated G showed «عري», a
# community yes/no that says nothing of how strong the scene is)
AGES = {"G": "للكل", "PG": "للكل، مع إرشاد الأهل", "PG13": "من 13 سنة وفوق", "PG15": "من 15 سنة وفوق",
        "15+": "من 15 سنة وفوق", "18+": "من 18 سنة وفوق"}
TABS = [("cinemas", "السينمات", "seat"), ("films", "الأفلام", "film"), ("coming", "قريباً", "cal")]
DAYS_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
CHIPS = [("all", "الكل"), ("action", "أكشن"), ("comedy", "كوميديا"), ("horror", "رعب"), ("thriller", "إثارة"),
         ("drama", "دراما"), ("adventure", "مغامرة"), ("family", "عائلي"), ("scifi", "خيال"), ("romance", "رومانسي"),
         ("arabic", "عربي"), ("indian", "هندي"), ("english", "إنجليزي")]
GENRE_AR = {"action": "أكشن", "comedy": "كوميديا", "horror": "رعب", "thriller": "إثارة", "drama": "دراما",
            "adventure": "مغامرة", "family": "عائلي", "animation": "أنيميشن", "scifi": "خيال علمي", "fantasy": "فانتازيا",
            "romance": "رومانسي", "crime": "جريمة", "music": "موسيقى", "mystery": "غموض", "war": "حرب",
            "history": "تاريخي", "documentary": "وثائقي", "biography": "سيرة"}
LANG_AR = {"English": "إنجليزي", "Arabic": "عربي", "Hindi": "هندي", "Tamil": "تاميل", "Malayalam": "مالايالام",
           "Telugu": "تيلوغو", "Kannada": "كانادا", "Tagalog": "فلبيني", "Nepali": "نيبالي", "Punjabi": "بنجابي",
           "French": "فرنسي", "Korean": "كوري", "Japanese": "ياباني", "Urdu": "أوردو"}
VERDICT = {"yes": ("يستاهل", "y"), "mixed": ("بين بين", "m"), "skip": ("تجنّبه", "s")}
ASK_QS = ["شو نوع الفيلم؟", "يناسب العيال؟", "عن شو القصة؟", "شو يصير في النهاية؟"]

# ---- the English site (owner 2026-10-23): the same pages under /en/, every UI phrase through tr(); the data's own
# English (titles, cinema and chain names, halls, synopses, verdicts) comes from the Kit by LANG. LANG is set once per
# build by main() (one language per process; tests set it and reset it).
LANG = "ar"
EN = {
    # time and units
    "بالليل": "am", "الصبح": "am", "الظهر": "pm", "مساء": "pm", "ص": "am", "م": "pm", "د": "min", "درهم": "AED",
    # the frame
    "سينما": "Cinema", "سينما الإمارات": "UAE Cinemas", "الأقسام": "Sections", "رجوع": "Back", "بحث": "Search", "سكّر": "Close",
    "شارك": "Share", "احجز": "Book", "المزيد": "More", "السينمات": "Cinemas", "الأفلام": "Films", "قريباً": "Coming soon",
    "البطاقات والخصومات": "Cards & discounts", "أسعار التذاكر": "Ticket prices", "أسئلة": "Questions", "سينما من Elyoxe": "Cinema by Elyoxe",
    "سينما الإمارات: مواعيد أفلام اليوم في كل السينمات وأسعار التذاكر": "UAE cinemas: today's showtimes in every cinema, and ticket prices",
    "سينما الإمارات — مواعيد أفلام اليوم في كل السينمات وأسعار التذاكر": "UAE Cinemas — today's showtimes in every cinema, and ticket prices",
    "فيلم في": "films in", "سينما في دبي وأبوظبي والشارقة والعين وباقي الإمارات": "cinemas across Dubai, Abu Dhabi, Sharjah, Al Ain and the rest of the UAE",
    "المواعيد والأسعار والتذكرة الأرخص وأقرب عرض لك": "Showtimes, prices, the cheapest ticket and the show nearest you.",
    "أفلام اليوم في سينمات الإمارات": "Films showing today in UAE cinemas",
    # the home
    "أقرب سينما": "Nearest cinema", "كل المدن": "All cities", "سينماتي": "My cinemas", "فيلم اليوم": "films today", "المواعيد": "Showtimes",
    "سينما وحدة": "1 cinema", "سينمتين": "2 cinemas", "سينمات": "cinemas",
    "الأكثر عرضاً الليلة": "Most shown tonight", "يبدأ قريب منك": "Starting near you", "ما في عروض قريبة الحين": "No shows starting soon.",
    "فيلم أو سينما…": "Film or cinema…", "الأكثر عرضاً": "Most shown", "الأعلى تقييماً": "Best rated", "الأحدث": "Newest",
    "يبدأ خلال ساعتين": "Starts within 2 hours", "ما في أفلام بهالتصنيف اليوم": "No films in this genre today.", "ممتاز": "Top rated",
    "بكرة": "Tomorrow", "اليوم": "Today", "بعد يومين": "In 2 days", "بعد %d أيام": "In %d days",
    "ما في أفلام معلنة للأسابيع الياية": "No films announced for the coming weeks.",
    "الكل": "All", "أكشن": "Action", "كوميديا": "Comedy", "رعب": "Horror", "إثارة": "Thriller", "دراما": "Drama", "مغامرة": "Adventure",
    "عائلي": "Family", "خيال": "Sci-fi & fantasy", "رومانسي": "Romance", "عربي": "Arabic", "هندي": "Indian", "إنجليزي": "English",
    "أنيميشن": "Animation", "خيال علمي": "Sci-fi", "فانتازيا": "Fantasy", "جريمة": "Crime", "موسيقى": "Music", "غموض": "Mystery",
    "حرب": "War", "تاريخي": "History", "وثائقي": "Documentary", "سيرة": "Biography",
    "تاميل": "Tamil", "مالايالام": "Malayalam", "تيلوغو": "Telugu", "كانادا": "Kannada", "فلبيني": "Filipino", "نيبالي": "Nepali",
    "بنجابي": "Punjabi", "فرنسي": "French", "كوري": "Korean", "ياباني": "Japanese", "أوردو": "Urdu",
    "دبي": "Dubai", "أبوظبي": "Abu Dhabi", "الشارقة": "Sharjah", "العين": "Al Ain", "عجمان": "Ajman", "رأس الخيمة": "Ras Al Khaimah",
    "الفجيرة": "Fujairah", "أم القيوين": "Umm Al Quwain",
    "الاثنين": "Monday", "الثلاثاء": "Tuesday", "الأربعاء": "Wednesday", "الخميس": "Thursday", "الجمعة": "Friday", "السبت": "Saturday", "الأحد": "Sunday",
    "يناير": "January", "فبراير": "February", "مارس": "March", "أبريل": "April", "مايو": "May", "يونيو": "June", "يوليو": "July",
    "أغسطس": "August", "سبتمبر": "September", "أكتوبر": "October", "نوفمبر": "November", "ديسمبر": "December",
    # the film page
    "النقاد": "Critics", "الطاقم": "Cast & crew", "إخراج": "Directed by", "الإعلان": "Trailer", "وين يعرض": "Where it's showing",
    "أقرب عرض لك": "Nearest show to you", "خلصت عروض اليوم هني، شوف بكرة": "Today's shows here are over — see tomorrow.",
    "يستاهل": "Worth it", "بين بين": "Mixed", "تجنّبه": "Skip it",
    "للعائلة": "For families", "التصنيف في الإمارات": "UAE rating", "تحذيرات تحرق شوي": "Warnings that spoil a little",
    "فيه مشهد بعد النهاية، لا تطلع بدري": "There's a scene after the credits — don't leave early.", "ما فيه مشهد بعد النهاية": "No scene after the credits.",
    "عن النسخة الأصلية من الفيلم، والنسخة اللي تنعرض في الإمارات ممكن تكون مقصوصة": "About the original cut; the version shown in the UAE may be edited.",
    "من تقييمات جمهور": "From audience ratings on", "تقول إذا اللقطة موجودة، مب قد إيش قوية": "they say whether a scene is there, not how strong it is.",
    "مشاهد جنسية": "Sexual content", "عري": "Nudity", "اعتداء جنسي": "Sexual assault", "دم وعنف": "Blood & violence", "رعب جسدي": "Body horror",
    "تعذيب": "Torture", "عنف بالسلاح": "Gun violence", "لقطات تخرّع فجأة": "Jump scares", "أشباح": "Ghosts", "مسّ": "Possession",
    "شياطين": "Demons", "مخدرات": "Drugs", "شرب خمر": "Alcohol", "تدخين": "Smoking", "يموت طفل": "A child dies", "يموت حيوان": "An animal dies",
    "للكل": "All ages", "للكل، مع إرشاد الأهل": "All ages, parental guidance", "من 13 سنة وفوق": "13 and over", "من 15 سنة وفوق": "15 and over",
    "من 18 سنة وفوق": "18 and over",
    "اسأل الفيلم": "Ask the film", "اسأل": "Ask", "سؤالك": "Your question", "مثلاً: يناسب العيال؟": "e.g. Is it OK for kids?",
    "اسأل أي شي عن الفيلم، ونجاوبك من قصته ومعلوماته بس. اللي يحرق نخفيه لين تضغط": "Ask anything about the film; answers come from its story and facts only. Spoilers stay hidden until you tap.",
    "شو نوع الفيلم؟": "What kind of film is it?", "يناسب العيال؟": "Is it OK for kids?", "عن شو القصة؟": "What's the story?", "شو يصير في النهاية؟": "How does it end?",
    # titles and descriptions
    "اليوم في": "today in", "بكرة في سينمات الإمارات": "tomorrow in UAE cinemas", "مواعيد": "showtimes", "، من": ", from",
    "عرض اليوم في": "shows today in", "في سينمات الإمارات بكرة": "in UAE cinemas tomorrow", "، التذكرة من": ", tickets from",
    "فيلم اليوم ومواعيدها": "films today and their times", "أفلام بكرة ومواعيدها": "tomorrow's films and their times", "فيلم اليوم في": "films today at",
    "، أول عرض": ", first show", "وآخر عرض": "and last show", "المواعيد والأسعار والحجز": "Showtimes, prices and booking.", "أفلام": "Films at",
    "بكرة بمواعيدها وأسعارها": "tomorrow with times and prices.", "المواعيد والأسعار في سينمات الإمارات": "showtimes and prices in UAE cinemas",
    "الأفلام والمواعيد اليوم": "films and showtimes today", "اليوم وبكرة بمواعيدها وأسعارها": "today and tomorrow with times and prices",
    # the script's own lines (window.APP.t carries the ones it uses)
    "انحفظ الرابط": "Link copied", "انشالت من سينماتي": "Removed from my cinemas", "انضافت لسينماتي": "Added to my cinemas",
    "أقل من كيلو": "under 1 km", "كم": "km", "ما لقينا شي بهالاسم": "Nothing by that name.", "يبدأ الحين": "Starting now", "بعد": "in",
    "ما في فيلم يبدأ خلال ساعتين في": "No film starts within 2 hours in", "أقرب سينما لك": "Nearest cinemas to you",
    "لحظة، نحدد مكانك…": "One moment, finding you…", "ما قدرنا نعرف مكانك — اختار مدينتك": "We couldn't find your location — pick your city.",
    "في": "in", "أقل": "Less", "يخلص تقريباً": "ends around", "السعر في الشباك": "Price at the box office", "نفس الفيلم أرخص بـ": "Same film cheaper by ",
    "لحظة…": "One moment…", "وصلنا حد الأسئلة لليوم، جرّب بكرة": "We've hit today's question limit — try tomorrow.",
    "ما قدرنا نجاوب الحين، جرّب مرة ثانية": "Couldn't answer right now — try again.", "من قصة الفيلم": "From the film's story",
    "من معلومات الفيلم": "From the film's facts", "يحرق — اضغط إذا تبا تعرف": "Spoiler — tap if you want to know",
}
JS_KEYS = ["بالليل", "الصبح", "الظهر", "مساء", "درهم", "انحفظ الرابط", "انشالت من سينماتي", "انضافت لسينماتي", "أقل من كيلو", "كم", "الأفلام",
           "السينمات", "ما لقينا شي بهالاسم", "يبدأ الحين", "بعد", "د", "ما في فيلم يبدأ خلال ساعتين في", "ما في أفلام بهالتصنيف اليوم",
           "أقرب سينما لك", "لحظة، نحدد مكانك…", "ما قدرنا نعرف مكانك — اختار مدينتك", "الإعلان", "سكّر", "في", "أقل", "المزيد", "اليوم", "بكرة",
           "يخلص تقريباً", "إنجليزي", "عربي", "هندي", "تاميل", "مالايالام", "تيلوغو", "السعر في الشباك", "نفس الفيلم أرخص بـ", "لحظة…",
           "وصلنا حد الأسئلة لليوم، جرّب بكرة", "ما قدرنا نجاوب الحين، جرّب مرة ثانية", "من قصة الفيلم", "من معلومات الفيلم", "يحرق — اضغط إذا تبا تعرف"]


def tr(ar):
    """A UI phrase in the build's language. Untranslated: the Arabic, and a line on stderr (the test counts them)."""
    if LANG == "ar" or not re.search(r"[؀-ۿ]", ar):   # a Latin value (a language name) is already English
        return ar
    en = EN.get(ar)
    if en is None:
        print(f"app: untranslated: {ar!r}", file=sys.stderr)
        return ar
    return en


def sep():
    return ", " if LANG == "en" else "، "


def cityname(c):
    return tr(CITY[c]) if c in CITY else ""


def dirham():
    return DIRHAM.replace('aria-label="درهم"', f'aria-label="{tr("درهم")}"')
_PAREN = re.compile(r"\s*\((?:فلم|فيلم)[^)]*\)\s*$")


# ------------------------------------------------------------------ helpers
def title(k, fid):
    """The film's name in the build's language: the Arabic title without Wikipedia's «(فلم 2026)», else the English."""
    if LANG == "en":
        return k.films[fid].get("title") or _PAREN.sub("", k.ftitle(fid, "ar")).strip()
    return _PAREN.sub("", k.ftitle(fid, "ar")).strip()


def num(v):
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:.2f}".rstrip("0").rstrip(".")


def score(f):
    """(label, kind): IMDb first (the owner's ask), else the critics' Rotten Tomatoes score, else nothing."""
    if f.get("imdb_score"):
        return f"{float(f['imdb_score']):.1f}", "imdb"
    rt = (f.get("rt") or {}).get("critics")
    if rt is not None:
        return f"{int(rt)}%", "rt"
    return "", ""


def tags(f):
    g = set(f.get("genres") or [])
    out = set(g)
    if g & {"family", "animation"}:
        out.add("family")
    if g & {"scifi", "fantasy"}:
        out.add("scifi")
    if f.get("lang") == "Arabic":
        out.add("arabic")
    if f.get("lang") in INDIAN:
        out.add("indian")
    if f.get("lang") == "English":
        out.add("english")
    return out


def hm(t):
    return t[:5]


DIRHAM_PATH = '<path d="M7.5 4v16h4.2c4.6 0 7.8-3.3 7.8-8s-3.2-8-7.8-8z" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round"/><path d="M3 10h18M3 14h18" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>'
DIRHAM = f'<svg class="aed" aria-label="{tr("درهم")}" role="img"><use href="#i-aed"/></svg>'


def t12(t):
    """«16:25» → («4:25», «مساء»); the small hours are «بالليل» (owner 2026-10-18: «بدال 16 نقول 4 مساء»)."""
    h, m = int(t[:2]), t[3:5]
    word = f"{tr('بالليل')}" if h < 4 else f"{tr('الصبح')}" if h < 12 else f"{tr('الظهر')}" if h == 12 else f"{tr('مساء')}"
    return f"{h % 12 or 12}:{m}", word


def ap(t):
    """The one-letter period for a small button: ص before noon, م after."""
    return f"{tr('ص')}" if 4 <= int(t[:2]) < 12 else f"{tr('م')}"


def runtime(f):
    r = f.get("runtime")
    if not r:
        return ""
    r = int(r)
    return f'<bdi dir="ltr" class="n">{r // 60}:{r % 60:02d}</bdi>' if r >= 60 else f'<bdi class="n">{r}</bdi> {tr("د")}'


ICONS = {"back": '<path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
         "pin": '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="9.5" r="2.5" fill="currentColor"/>',
         "star": '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.8z" fill="currentColor"/>',
         "play": '<path d="M8 5v14l11-7z" fill="currentColor"/>',
         "clock": '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
         "chat": '<path d="M5 5h14v10H9l-4 4z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
         "map": '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" fill="none" stroke="currentColor" stroke-width="2"/>',
         "film": '<rect x="4" y="5" width="16" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 9h16M4 15h16M9 5v14M15 5v14" stroke="currentColor" stroke-width="1.6"/>',
         "fwd": '<path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
         "cal": '<rect x="4" y="5.5" width="16" height="14.5" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 10.5h16M9 3.5v4M15 3.5v4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
         "search": '<circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M16 16l4.5 4.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
         "share": '<circle cx="18" cy="5" r="2.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="6" cy="12" r="2.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="18" cy="19" r="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8.2 10.8l7.6-4.4M8.2 13.2l7.6 4.4" fill="none" stroke="currentColor" stroke-width="2"/>',
         "staro": '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.8z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
         "sort": '<path d="M4 7h16M7 12h10M10 17h4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
         "close": '<path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
         "seat": '<path d="M6 11V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v4M4 11h16v5H4zM6 16v3M18 16v3" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>'}

ICONS["aed"] = DIRHAM_PATH
SPRITE = '<svg hidden xmlns="http://www.w3.org/2000/svg">' + "".join(f'<symbol id="i-{k}" viewBox="0 0 24 24">{v}</symbol>' for k, v in ICONS.items()) + "</svg>"


def svg(name):
    """An icon by reference: the page's sprite (SPRITE, once after <body>) holds the drawing."""
    assert name in ICONS, name
    return f'<svg width="20" height="20" aria-hidden="true"><use href="#i-{name}"/></svg>'



# ------------------------------------------------------------------ the app
class App:
    def __init__(self, data, disc, halls, out, base, live=False):
        # live: the main site — the old URLs (/film/<fid>/, /<city>/<cinema>/), open to search engines, written over the
        # old build's own pages in out/ (deploy.sh runs build.py first; its other pages stay: cards, prices, English…)
        self.live = live
        # the Arabic synopsis lives in intel/<fid>.json (filmintel, item 232); the old site attaches it at build time
        try:
            import filmintel
            for fid, f in (data.get("films") or {}).items():
                rec = filmintel.read(fid) or {}
                if not f.get("synopsis_ar") and rec.get("by") in ("claude", "hand") and isinstance(rec.get("synopsis_ar"), str):
                    f["synopsis_ar"] = rec["synopsis_ar"].strip()
        except Exception as e:  # noqa: BLE001 - no synopsis is a page without one, never a failed build
            print("app: synopses not attached:", e)
        self.k = Kit(data, disc, halls, out)
        self.d, self.out, self.base = data, out, base.rstrip("/") + "/"
        self.pfx = "/en" if (live and LANG == "en") else ""   # the live English site's URL prefix
        k = self.k
        self.shows = [s for s in k.shows if s["date"] in (k.today, k.tomorrow)]
        self.count = {}
        for s in self.shows:
            self.count[s["film"]] = self.count.get(s["film"], 0) + 1
        self.films = sorted((fid for fid in k.showing if self.count.get(fid)), key=lambda f: (-self.count[f], title(k, f)))
        self.cins = sorted({s["cinema"] for s in self.shows})
        # today's shows that already started (refresh.carry_past_today): greyed on the film and cinema pages only,
        # cleaned like the Kit cleans its own shows; they never count, rank or make a page of their own
        self.past = []
        for s in data.get("past_today") or []:
            if s.get("date") != k.today or s.get("cinema") not in k.cinemas or s.get("film") not in k.films:
                continue
            s = dict(s)
            if s.get("book") and not re.match(r"^https?://", str(s["book"])): s["book"] = None
            if s.get("ends") and not re.match(r"^\d{2}:\d{2}$", str(s["ends"])): s["ends"] = None
            if isinstance(s.get("subs"), (list, tuple)): s["subs"] = "+".join(str(x) for x in s["subs"] if x) or None
            self.past.append(s)
        self.people = data.get("people") or {}
        self.css_name = self.js_name = None
        self._ld, self._og = [], None
        self.fresh()

    def u(self, *parts):
        if self.live and parts and parts[0] == "f":
            return f"{self.pfx}/film/{parts[1]}/"
        if self.live and parts and parts[0] == "c":
            return f"{self.pfx}/{self.k.cinemas[parts[1]].get('city')}/{parts[1]}/"
        return self.base + "/".join(parts) + ("/" if parts else "")

    def chain(self, cid):
        return self.k.h.chain_name(self.k.cinemas[cid]["chain"], LANG)

    def mark(self, cid, cls=""):
        """The chain's own app icon (app/logos/<chain>.webp, owner 2026-10-19) in its square; the coloured name
        tile when a chain has none."""
        ch, name = self.k.cinemas[cid]["chain"], self.chain(cid)
        src = self.logos.get(ch)
        inner = f'<img src="{E(src)}" alt="{E(name)}" width="64" height="64" decoding="async">' if src else E(name)
        return f'<span class="cc-logo{" " + cls if cls else ""}{" img" if src else ""} ch-{E(ch)}">{inner}</span>'

    def cname(self, cid):
        """«فوكس — الجيمي مول» → the mall alone on a card under its chain («الجيمي مول»)."""
        n = self.k.cname(cid, LANG)
        return n.split(" — ", 1)[1] if " — " in n else n

    def poster(self, fid, w=342, cls="pst", eager=False):
        f = self.k.films[fid]
        pc = E(f.get("poster_color") or "#3a302a")
        if not f.get("poster"):
            return f'<span class="{cls} np" style="--pc:{pc}"><b>{E(title(self.k, fid))}</b></span>'
        src = f["poster"] if w <= 342 or not f.get("poster_2x") else f["poster_2x"]
        ss = f' srcset="{E(f["poster"])} 342w, {E(f["poster_2x"])} 684w" sizes="(min-width:900px) 200px, 46vw"' if f.get("poster_2x") and cls == "pst" else ""
        lazy = "" if eager else ' loading="lazy"'
        return f'<span class="{cls}" style="--pc:{pc}"><img src="{E(src)}"{ss} width="342" height="513" alt="" decoding="async"{lazy}></span>'

    def fresh(self):
        self._rows, self._seats, self._seat_i, self._cins = [], [], {}, set()

    def table(self):
        if not self._rows:
            return ""
        cins = {c: [self.cname(c), self.k.cinemas[c].get("city") or "", self.k.cinemas[c]["chain"], self.chain(c)] for c in sorted(self._cins)}
        j = json.dumps({"r": self._rows, "s": self._seats, "c": cins}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        return f'<script type="application/json" id="shows">{j}</script>'

    # -------- what search engines and shares read (live)
    def alt(self, path):
        if not self.live:
            return ""
        bare = path[3:] if path.startswith("/en/") else path
        return (f'<link rel="alternate" hreflang="ar" href="{E(SITE + bare)}"><link rel="alternate" hreflang="en" href="{E(SITE + "/en" + bare)}">'
                f'<link rel="alternate" hreflang="x-default" href="{E(SITE + bare)}">')

    def ld(self):
        if not self._ld:
            return ""
        g = json.dumps({"@context": "https://schema.org", "@graph": self._ld}, ensure_ascii=False).replace("</", "<\\/")
        return f'<script type="application/ld+json">{g}</script>'

    def spec(self):
        if self.live:
            pats = [f"{self.pfx}/film/*", self.pfx + "/"] + [f"{self.pfx}/{c}/*" for c, _ in CITIES]
        else:
            pats = [f"{self.base}f/*", f"{self.base}c/*", self.base]
        return json.dumps({"prerender": [{"where": {"href_matches": pats}, "eagerness": "moderate"}]})

    def footer(self):
        """The rest of the site, one quiet line at the end: nothing lost, nothing in the way."""
        links = ([("/cards/", tr("البطاقات والخصومات")), ("/prices/", tr("أسعار التذاكر")), ("/coming/", tr("قريباً")), ("/q/", tr("أسئلة")), ("/en/", "English")]
                 if LANG == "ar" else [("/en/cards/", tr("البطاقات والخصومات")), ("/en/prices/", tr("أسعار التذاكر")), ("/en/coming/", tr("قريباً")), ("/en/q/", tr("أسئلة")), ("/", "العربية")])
        return '<footer class="foot">' + "".join(f'<a href="{h}">{t}</a>' for h, t in links) + f'<small>{tr("سينما من Elyoxe")}</small></footer>'

    # -------- page frame
    def page(self, path, ttl, desc, body, kind, head_extra="", canon=None):
        canon = SITE + path if self.live else (canon or (SITE + path))
        if kind != "home":
            body += self.tabbar({"film": "films", "cinema": "cinemas"}.get(kind))
        body = body + (self.footer() if self.live else "")
        doc = f"""<!doctype html>
<html lang="{LANG}" dir="{"ltr" if LANG == "en" else "rtl"}" data-kind="{kind}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(ttl)}</title><meta name="description" content="{E(desc)}">
{"" if self.live else '<meta name="robots" content="noindex">'}<link rel="canonical" href="{E(canon)}">{self.alt(path)}
<meta property="og:title" content="{E(ttl)}"><meta property="og:description" content="{E(desc)}"><meta property="og:type" content="website">
<meta property="og:url" content="{E(canon)}"><meta property="og:image" content="{E(self._og or SITE + f'/assets/og-{LANG}.png')}"><meta name="twitter:card" content="summary_large_image">
<meta property="og:locale" content="{"en_AE" if LANG == "en" else "ar_AE"}"><meta property="og:site_name" content="{tr('سينما الإمارات')}">{'<meta name="robots" content="max-image-preview:large">' if self.live else ''}
<link rel="manifest" href="/manifest.webmanifest">{self.ld()}
<meta name="theme-color" content="#F3EEE6" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#17120F" media="(prefers-color-scheme: dark)"><meta name="color-scheme" content="light dark">
<link rel="icon" href="/assets/icon.svg" type="image/svg+xml">
<link rel="preload" href="{self.base}assets/fonts/plex-ar-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{self.base}assets/fonts/plex-ar-700.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{self.base}assets/{self.css_name}">{head_extra}
<script type="speculationrules">{self.spec()}</script>
<script>(function(){{addEventListener("pagereveal",function(e){{var t=e.viewTransition,a=window.navigation&&navigation.activation;if(t&&a&&a.from&&a.entry&&a.navigationType==="traverse"&&a.entry.index<a.from.index)document.documentElement.dataset.nav="pop";else if(t)document.documentElement.dataset.nav="push";if(t)t.finished.finally(function(){{delete document.documentElement.dataset.nav}})}});addEventListener("pageswap",function(e){{var t=e.viewTransition,a=e.activation;if(t&&a&&a.navigationType==="traverse"&&a.entry&&a.from&&a.entry.index<a.from.index)document.documentElement.dataset.nav="pop";else if(t)document.documentElement.dataset.nav="push"}})}})()</script>
</head><body>{SPRITE}{body}{self.table()}
<div class="scrim" data-scrim hidden></div><div class="toast" data-toast role="status" hidden></div>
<script>window.APP={{base:"{self.base}",lang:"{LANG}",ask:"{ASK_API}",today:"{self.k.today}",tomorrow:"{self.k.tomorrow}",logos:{json.dumps(self.logos)},cities:{json.dumps({c: cityname(c) for c, _ in CITIES}, ensure_ascii=False)},t:{json.dumps({k: EN[k] for k in JS_KEYS} if LANG == "en" else {}, ensure_ascii=False)}}}</script>
<script src="{self.base}assets/{self.js_name}" defer></script>
</body></html>"""
        if LANG == "en":
            doc = doc.replace("، ", ", ")
        p = os.path.join(self.out, *[x for x in path.replace(self.base, "", 1).split("/") if x], "index.html")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(doc)

    def tabbar(self, on=None, home=False):
        """The bottom bar (owner 2026-10-19): السينمات · الأفلام · قريباً. On the home its buttons turn the pager; on a
        film or cinema page they are links back to that tab (/#films …)."""
        out = []
        for i, (key, label, icon) in enumerate(TABS):
            inner = svg(icon) + "<span>" + tr(label) + "</span>"
            if home:
                sel = "true" if key == on else "false"
                cls = ' class="on"' if key == on else ""
                out.append('<button type="button" role="tab" data-tab="%d" aria-selected="%s"%s>%s</button>' % (i, sel, cls, inner))
            else:
                cls = ' class="on" aria-current="page"' if key == on else ""
                out.append('<a href="%s#%s"%s>%s</a>' % (self.base, key, cls, inner))
        role = ' role="tablist"' if home else ""
        return f'<nav class="tabbar" aria-label="{tr("الأقسام")}"%s>%s</nav>' % (role, "".join(out))

    def bar(self, ttl, back=True, right=""):
        b = (f'<a class="pg-back" href="{self.base}" data-back aria-label="{tr("رجوع")}">{svg("back")}</a>' if back else "<span></span>")
        return f'<header class="pgbar">{b}<h1>{E(ttl)}</h1>{right or "<span></span>"}</header>'

    def share_btn(self, text):
        """«شارك» (owner 2026-10-22): the phone's share sheet with the page's own title and link; no share sheet (a
        desktop), the link is copied and a toast says so."""
        return f'<button type="button" class="pg-act" data-share="{E(text)}" aria-label="{tr("شارك")}">{svg("share")}</button>'

    # -------- home
    def tile(self, fid):
        k, f = self.k, self.k.films[fid]
        sc, kind = score(f)
        meta = []
        if f.get("runtime"):
            meta.append(f'<span class="m-rt">{svg("clock")}{runtime(f)}</span>')
        if sc:
            meta.append(f'<span class="m-sc {kind}">{svg("star") if kind == "imdb" else ""}<b>{E(sc)}</b>{"<small>IMDb</small>" if kind == "imdb" else "<small>" + tr("النقاد") + "</small>"}</span>')
        age = f'<i class="age">{E(f["rating"])}</i>' if f.get("rating") else ""
        # the sort keys (owner 2026-10-22): shows, a 0-100 score (IMDb ×10, else the critics' %), the release day
        imdb, rt = f.get("imdb_score"), (f.get("rt") or {}).get("critics")
        scn = float(imdb) * 10 if imdb else (float(rt) if rt is not None else 0)
        top = f'<i class="top">{tr("ممتاز")}</i>' if scn >= 75 else ""
        return (f'<a class="tile" href="{self.u("f", fid)}" data-fid="{E(fid)}" data-g="{E(" ".join(sorted(tags(f))))}" data-n="{self.count.get(fid, 0)}" '
                f'data-sc="{scn:g}" data-rel="{E(f.get("released") or "")}">'
                f'<span class="tp">{self.poster(fid)}{age}{top}</span>'
                f'<span class="tt">{E(title(k, fid))}</span><span class="tm">{"".join(meta)}</span></a>')

    def ccard(self, cid):
        c = self.k.cinemas[cid]
        n = len({s["film"] for s in self.shows if s["cinema"] == cid and s["date"] == self.k.today})
        lat, lng = c.get("lat"), c.get("lng")
        geo = f' data-lat="{lat:.5f}" data-lng="{lng:.5f}"' if lat is not None and lng is not None else ""
        return (f'<a class="ccard" href="{self.u("c", cid)}" data-city="{E(c.get("city") or "")}" data-cid="{E(cid)}"{geo}>'
                + self.mark(cid) +
                f'<span class="cc-b"><b>{E(self.cname(cid))}</b><small>{E(cityname(c.get("city")))}'
                f'<span class="cc-km" data-km></span></small></span>'
                f'<span class="cc-n"><b>{n}</b><small>{tr("فيلم اليوم")}</small></span>'
                f'<span class="fav" data-fav="{E(cid)}" role="button" tabindex="0" aria-label="{tr("سينماتي")}" aria-pressed="false">{svg("staro")}{svg("star")}</span></a>')

    def billboard(self):
        """«الشاشة» from the live site, smaller: tonight's five most-shown films that have a trailer still, a card each,
        swiped sideways; the name, two facts and one button."""
        k = self.k
        top = [f for f in self.films if (k.films[f].get("backdrop") or {}).get("w640")][:5]
        if not top:
            return ""
        slides = []
        for i, fid in enumerate(top):
            f = k.films[fid]; bd = f["backdrop"]
            sc, kind = score(f)
            facts = " · ".join(x for x in [runtime(f), E(f.get("rating") or ""), (f"★ {sc}" if kind == "imdb" else "")] if x)
            lazy = "" if i == 0 else ' loading="lazy"'
            pri = ' fetchpriority="high"' if i == 0 else ""
            slides.append(f'<a class="bb" href="{self.u("f", fid)}" style="--pc:{E(f.get("poster_color") or "#3a302a")}">'
                          f'<img src="{E(bd["w640"])}" srcset="{E(bd["w640"])} 640w, {E(bd.get("w1280") or bd["w640"])} 1280w" sizes="(min-width:900px) 860px, 92vw" alt=""{lazy}{pri}>'
                          f'<span class="bb-t"><small>{tr("الأكثر عرضاً الليلة")}</small><b>{E(title(k, fid))}</b><i>{facts}</i></span></a>')
        dots = "".join(f'<i{" class=\"on\"" if i == 0 else ""}></i>' for i in range(len(top)))
        return f'<section class="bill"><div class="bb-row" data-bill>{"".join(slides)}</div><div class="bb-dots" data-dots>{dots}</div></section>'

    def soon_board(self):
        """«يبدأ قريب منك» from the live site: three rows, the flip clock, the visitor's city. The page carries today's
        times compactly (#soon) and the script picks the next three in the city."""
        k = self.k
        cins = sorted({s["cinema"] for s in self.shows if s["date"] == k.today})
        ci = {c: i for i, c in enumerate(cins)}
        fi = {f: i for i, f in enumerate(self.films)}
        rows = []
        for s in self.shows:
            if s["date"] != k.today or s["film"] not in fi:
                continue
            pr = [p["aed"] for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
            rows.append([ci[s["cinema"]], fi[s["film"]], hm(s["time"]), float(num(min(pr))) if pr else 0])
        data = {"c": [[c, self.cname(c), k.cinemas[c].get("city") or "", k.cinemas[c]["chain"], self.chain(c)] for c in cins],
                "f": [[f, title(k, f), k.films[f].get("poster") or ""] for f in self.films], "r": rows, "d": k.today}
        j = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        return (f'<section class="soon" data-soon><h2>{tr("يبدأ قريب منك")} <span data-soon-city></span></h2><div class="sb" data-soon-rows></div><template id="aed">{dirham()}</template>'
                f'<p class="empty sm" data-soon-none hidden>{tr("ما في عروض قريبة الحين")}.</p></section>'
                f'<script type="application/json" id="soon">{j}</script>')

    def coming(self):
        """«قريباً»: the films the chains list as coming (data["coming"]), by release day, poster and genre; a tap plays
        the trailer when there is one."""
        import datetime as _dt
        k, today = self.k, self.k.today
        horizon = (_dt.date.fromisoformat(today) + _dt.timedelta(days=75)).isoformat()
        items = [(fid, c) for fid, c in (self.d.get("coming") or {}).items()
                 if c.get("poster") and today < str(c.get("release_date") or "") <= horizon and fid not in self.count]
        items.sort(key=lambda x: (x[1]["release_date"], (x[1].get("title") or "").lower()))
        labels = dict(CHIPS)
        out, day = [], None
        for fid, c in items[:72]:
            if c["release_date"] != day:
                if day is not None:
                    out.append("</div>")
                day = c["release_date"]
                dd = _dt.date.fromisoformat(day)
                n = (dd - _dt.date.fromisoformat(today)).days
                rel = f"{tr('بكرة')}" if n == 1 else f"{tr('بعد يومين')}" if n == 2 else (f"{tr('بعد %d أيام')}" % n if n <= 10 else "")
                out.append('<h3 class="cday">%s %d %s%s</h3><div class="grid">' % (
                    tr(DAYS_AR[dd.weekday()]), dd.day, tr(MONTHS_AR[dd.month - 1]), ' <small>%s</small>' % rel if rel else ""))
            g = [tr(labels[t]) for t in sorted(tags({"genres": [x.lower() for x in c.get("genres") or []]})) if t in labels and t != "all"][:2]
            name = c.get("title_ar") or c.get("title") or fid
            img = '<span class="pst"><img src="%s" width="342" height="513" alt="" loading="lazy" decoding="async"></span>' % E(c["poster"])
            play = '<i class="cplay">%s</i>' % svg("play") if c.get("trailer") else ""
            inner = '<span class="tp">%s%s</span><span class="tt">%s</span><span class="tm">%s</span>' % (img, play, E(name), E(sep().join(g)))
            if c.get("trailer"):
                out.append('<button type="button" class="tile ct" data-trailer="%s">%s</button>' % (E(c["trailer"]), inner))
            else:
                out.append('<div class="tile ct">%s</div>' % inner)
        if day is not None:
            out.append("</div>")
        return "".join(out) or f'<p class="empty">{tr("ما في أفلام معلنة للأسابيع الياية")}.</p>'

    def home(self, path=None, merged=True):
        k = self.k
        chips = []
        for key, label in CHIPS:
            if key == "all" or any(key in tags(k.films[f]) for f in self.films):
                chips.append(f'<button type="button" class="chip{" on" if key == "all" else ""}" data-chip="{key}">{tr(label)}</button>')
            if key == "all":
                chips.append(f'<button type="button" class="chip soon2h" data-chip="soon2h">{svg("clock")}{tr("يبدأ خلال ساعتين")}</button>')
        grid = "".join(self.tile(f) for f in self.films)
        # السينمات (owner 2026-10-19): «أقرب سينما», then the cities; a city opens its cinemas
        per_city = {}
        for c in self.cins:
            per_city[k.cinemas[c].get("city")] = per_city.get(k.cinemas[c].get("city"), 0) + 1
        def howmany(n):
            if LANG == "en":
                return "1 cinema" if n == 1 else f"{n} cinemas"
            return f"{tr('سينما وحدة')}" if n == 1 else f"{tr('سينمتين')}" if n == 2 else f"%d {tr('سينمات')}" % n if n <= 10 else f"%d {tr('سينما')}" % n
        rows = "".join('<button type="button" class="crow" data-city="%s"><b>%s</b><small>%s</small>%s</button>'
                       % (c, cityname(c), howmany(per_city[c]), svg("fwd")) for c, _ in CITIES if per_city.get(c))
        cards = "".join(self.ccard(c) for c in sorted(self.cins, key=lambda c: (k.cinemas[c].get("city") or "", self.cname(c))))
        # the search index (owner 2026-10-22): every showing film and cinema, by their Arabic and English names
        idx = {"f": [[fid, title(k, fid), k.films[fid].get("title") or "", k.films[fid].get("poster") or "", self.u("f", fid)] for fid in self.films],
               "c": [[c, self.cname(c), k.cname(c, "en"), self.chain(c), cityname(k.cinemas[c].get("city")), k.cinemas[c]["chain"], self.u("c", c)]
                     for c in self.cins]}
        idx_js = json.dumps(idx, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        search = (f'<button type="button" class="th-btn" data-search-open aria-label="{tr("بحث")}">{svg("search")}</button>'
                  f'<div class="srch" data-search hidden><div class="srch-bar"><input type="search" data-search-in placeholder="{tr("فيلم أو سينما…")}" '
                  f'autocomplete="off" enterkeyhint="search" aria-label="{tr("بحث")}"><button type="button" class="th-btn" data-search-close aria-label="{tr("سكّر")}">{svg("close")}</button></div>'
                  f'<div class="srch-out" data-search-out></div></div><script type="application/json" id="idx">{idx_js}</script>')
        sort = f'<button type="button" class="chip sort" data-sort-open>{svg("sort")}<span data-sort-label>{tr("الأكثر عرضاً")}</span></button>'
        sort_menu = ('<div class="menu" data-sort-menu hidden>' + "".join(
                    f'<button type="button" data-sort="{key}"{" class=\"on\"" if key == "n" else ""}>{label}</button>'
                    for key, label in (("n", f"{tr('الأكثر عرضاً')}"), ("sc", f"{tr('الأعلى تقييماً')}"), ("rel", f"{tr('الأحدث')}"))) + "</div>")
        body = f"""<div class="app">
<header class="tophead"><a class="brand" href="{self.base}">{tr('سينما')}</a><p class="th-t" data-tab-title>{tr('السينمات')}</p>{search}</header>
<h1 class="sr-only">{tr('سينما الإمارات: مواعيد أفلام اليوم في كل السينمات وأسعار التذاكر')}</h1>
<main class="pager" data-pager>
<section class="pane" data-key="cinemas" aria-label="{tr('السينمات')}">
<button type="button" class="nearbtn" data-near>{svg("pin")}{tr('أقرب سينما')}</button><p class="geo-msg" data-geo-msg hidden></p>
<div class="favs" data-favs hidden><h2>{tr('سينماتي')}</h2><div class="clist" data-favlist></div></div>
<div class="cities" data-cities>{rows}</div>
<div class="cv" data-cv hidden><button type="button" class="cv-back" data-cv-back>{svg("back")}{tr('كل المدن')}</button><h2 data-cv-title></h2></div>
<div class="clist" data-clist hidden>{cards}</div></section>
<section class="pane" data-key="films" aria-label="{tr('الأفلام')}">{(self.billboard() + self.soon_board()) if merged else ""}<div class="chips" data-chips>{sort}{"".join(chips)}</div>{sort_menu}
<div class="grid" data-grid>{grid}</div><p class="empty" data-none hidden>{tr('ما في أفلام بهالتصنيف اليوم')}.</p></section>
<section class="pane" data-key="coming" aria-label="{tr('قريباً')}">{self.coming()}</section>
</main>{self.tabbar("cinemas", home=True)}</div>"""
        import datetime as _dt
        dd = _dt.date.fromisoformat(k.today)
        nf, nc = len(self.films), len(self.cins)
        self._ld = [{"@type": "WebSite", "name": f"{tr('سينما الإمارات')}", "url": SITE + "/", "inLanguage": LANG},
                    {"@type": "ItemList", "name": f"{tr('أفلام اليوم في سينمات الإمارات')}", "itemListOrder": "https://schema.org/ItemListOrderDescending",
                     "numberOfItems": nf, "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": SITE + self.u("f", fid), "name": title(k, fid)}
                                                               for i, fid in enumerate(self.films[:20])]}]
        self.page(path or self.base, f"{tr('سينما الإمارات — مواعيد أفلام اليوم في كل السينمات وأسعار التذاكر')}",
                  f"{nf} {tr('فيلم في')} {nc} {tr('سينما في دبي وأبوظبي والشارقة والعين وباقي الإمارات')}، {tr(DAYS_AR[dd.weekday()])} {dd.day} {tr(MONTHS_AR[dd.month - 1])}. "
                  f"{tr('المواعيد والأسعار والتذكرة الأرخص وأقرب عرض لك')}.", body, "home")
        self._ld = []

    # -------- shows → time buttons
    def times(self, shows):
        out = []
        for s in sorted(shows, key=lambda s: (s["date"], s["time"] < "04:00", s["time"])):   # 00:45 is that night's last show
            pr = [p["aed"] for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
            hk = self.k.hkey(s)
            hall = self.k.hname(s, LANG) if hk != "Standard" else ""
            # the ticket's details live once per page in #shows (a table, not 600 bytes of attributes per button):
            # [day, time, ends, hall, booking url, language, seat-list index]; seat lists are shared in #seats
            seats = [[p["seat"], p["aed"]] for p in sorted(s.get("prices") or [], key=lambda p: p.get("aed") or 0) if (p.get("aed") or 0) > 0]
            sk = json.dumps(seats, ensure_ascii=False)
            if sk not in self._seat_i:
                self._seat_i[sk] = len(self._seats); self._seats.append(seats)
            self._rows.append([s["date"], hm(s["time"]), s.get("ends") or "", hall, self.k.book_url(s), s.get("lang") or "", self._seat_i[sk], s["cinema"]])
            self._cins.add(s["cinema"])
            out.append(f'<button type="button" class="tbtn" data-d="{s["date"]}" data-t="{hm(s["time"])}" data-i="{len(self._rows) - 1}">'
                       f'<b>{t12(hm(s["time"]))[0]}<sup>{ap(s["time"])}</sup></b>{f"<small>{E(hall)}</small>" if hall else ""}{f"<i>{num(min(pr))}{dirham()}</i>" if pr else ""}</button>')
        return "".join(out)

    def dayswitch(self):
        k = self.k
        has = {s["date"] for s in self.shows}
        btn = lambda d, lab, on: f'<button type="button" class="seg{" on" if on else ""}" data-day="{d}">{lab}</button>' if d in has else ""
        return f'<div class="segs" data-days>{btn(k.today, tr("اليوم"), True)}{btn(k.tomorrow, tr("بكرة"), k.today not in has)}</div>'

    # -------- film page
    def family(self, f):
        """«للعائلة» (owner 2026-10-20): the content flags and the end-credits answer from Does the Dog Die? — the
        original cut, which the line says — with the credit its terms ask for. Nothing known: no section."""
        c = f.get("content") or {}
        flags = [tr(FAMILY[k]) for k in c.get("flags") or [] if k in FAMILY]
        deaths = [tr(DEATHS[k]) for k in c.get("flags") or [] if k in DEATHS]
        cr = c.get("credits")
        if not flags and not deaths and cr is None:
            return ""
        out = [f'<section class="sec fam"><h2>{tr("للعائلة")}</h2>']
        if f.get("rating") in AGES:
            out.append(f'<p class="fam-age">{tr("التصنيف في الإمارات")} <b dir="ltr">{E(f["rating"])}</b>: {tr(AGES[f["rating"]])}</p>')
        if cr is not None:
            out.append(f'<p class="fam-cr">{tr("فيه مشهد بعد النهاية، لا تطلع بدري") + "." if cr else tr("ما فيه مشهد بعد النهاية") + "."}</p>')
        if flags:
            out.append('<ul class="fam-f">' + "".join(f"<li>{E(x)}</li>" for x in flags) + "</ul>")
        if deaths:
            out.append(f'<details class="fam-sp"><summary>{tr("تحذيرات تحرق شوي")}</summary><ul class="fam-f">'
                       + "".join(f"<li>{E(x)}</li>" for x in deaths) + "</ul></details>")
        link = f'<a href="{E(c["url"])}" target="_blank" rel="noopener nofollow">Does the Dog Die</a>' if c.get("url") else "Does the Dog Die"
        out.append(f'<p class="fam-src">{tr("عن النسخة الأصلية من الفيلم، والنسخة اللي تنعرض في الإمارات ممكن تكون مقصوصة")}. '
                   f'{tr("من تقييمات جمهور")} {link}: {tr("تقول إذا اللقطة موجودة، مب قد إيش قوية")}.</p></section>')
        return "".join(out)

    def film(self, fid):
        self.fresh()
        k, f = self.k, self.k.films[fid]
        t = title(k, fid)
        sc, kind = score(f)
        bd = (f.get("backdrop") or {})
        still = bd.get("w1280") if bd.get("w1280") else None
        hero_bg = f'<img class="fh-still" src="{E(bd.get("w640") or still)}" srcset="{E(bd.get("w640"))} 640w, {E(still)} 1280w" sizes="100vw" alt="" fetchpriority="high">' if still else ""
        chips = []
        if f.get("runtime"):
            chips.append(f'<span>{svg("clock")}{runtime(f)}</span>')
        if f.get("rating"):
            chips.append(f'<span class="age2">{E(f["rating"])}</span>')
        if sc:
            chips.append(f'<span class="sc {kind}">{svg("star") if kind == "imdb" else ""}<b>{E(sc)}</b>{"IMDb" if kind == "imdb" else tr("النقاد")}</span>')
        if f.get("lang"):
            chips.append(f'<span>{E(tr(LANG_AR.get(f["lang"], f["lang"])))}</span>')
        genres = sep().join(tr(GENRE_AR[g]) for g in (f.get("genres") or []) if g in GENRE_AR)
        vd = f.get("verdict") or {}
        vw = VERDICT.get(vd.get("verdict"))
        vtext = re.sub(r"\s*\((?:فلم|فيلم)\s*\d{4}\)", "", vd.get(LANG) or "")
        verdict = (f'<div class="verdict v-{vw[1]}"><b>{tr(vw[0])}</b><p>{E(vtext)}</p></div>' if vw and vtext else "")
        syn = (f.get("synopsis_en") if LANG == "en" else f.get("synopsis_ar")) or ""
        syn_en = "" if syn else (f.get("synopsis_en") or "")
        about = (f'<section class="about" data-about><p class="syn clamp" data-clamp>{E(syn)}</p><button type="button" class="more" data-more hidden>{tr("المزيد")}</button></section>' if syn else
                 f'<section class="about" data-about><p class="syn clamp" lang="en" dir="ltr" data-clamp>{E(syn_en)}</p><button type="button" class="more" data-more hidden>{tr("المزيد")}</button></section>' if syn_en else "")
        cast = []
        for q in (f.get("cast") or [])[:8]:
            p = self.people.get(q) if isinstance(q, str) else None
            if p and (p.get("name_en") or p.get("name_ar")):
                cast.append(E(p.get("name_en") or p.get("name_ar")))
        crew = (f'<section class="sec"><h2>{tr("الطاقم")}</h2><p class="crew">{"" if not f.get("director") else tr("إخراج") + " <b lang=en>" + E(f["director"]) + "</b><br>"}'
                f'{"<span lang=en>" + sep().join(cast) + "</span>" if cast else ""}</p></section>' if cast or f.get("director") else "")
        trailer = (f'<button type="button" class="btn ghost" data-trailer="{E(f["trailer"])}">{svg("play")}{tr("الإعلان")}</button>' if f.get("trailer") else "")
        ask = (f'<button type="button" class="btn ghost" data-ask-open>{svg("chat")}{tr("اسأل الفيلم")}</button>')
        # where it shows: city tabs (the visitor's own first, script), each city its cinemas and their times
        shows = [s for s in self.shows + self.past if s["film"] == fid]
        cities = [c for c, _ in CITIES if any(k.cinemas[s["cinema"]].get("city") == c for s in shows)]
        sched = ""
        for c in cities:
            blocks = ""
            for cid in sorted({s["cinema"] for s in shows if k.cinemas[s["cinema"]].get("city") == c}, key=self.cname):
                cs = [s for s in shows if s["cinema"] == cid]
                cc = k.cinemas[cid]
                geo = f' data-lat="{cc["lat"]:.5f}" data-lng="{cc["lng"]:.5f}"' if cc.get("lat") is not None and cc.get("lng") is not None else ""
                blocks += (f'<div class="cblock" data-cin="{E(cid)}"{geo}><a class="cb-h" href="{self.u("c", cid)}">{self.mark(cid, "sm")}'
                           f'<b>{E(self.cname(cid))}</b><span class="cc-km" data-km></span></a><div class="times">{self.times(cs)}</div></div>')
            sched += f'<div class="city" data-city="{c}" hidden>{blocks}</div>'
        ctabs = "".join(f'<button type="button" class="chip" data-ctab="{c}">{cityname(c)}</button>' for c in cities)
        where = (f'<section class="sec where"><h2>{tr("وين يعرض")}</h2>{self.dayswitch()}<div class="chips" data-ctabs>{ctabs}</div>{sched}'
                 f'<p class="empty" data-past hidden>{tr("خلصت عروض اليوم هني، شوف بكرة")}.</p></section>') if shows else ""
        body = f"""<div class="pg film">{self.bar(t, right=self.share_btn(t + " — " + tr("سينما الإمارات")))}
<section class="fhero" style="--pc:{E(f.get('poster_color') or '#3a302a')}">{hero_bg}<div class="fh-in">{self.poster(fid, cls="pst big vt", eager=True)}
<div class="fh-t"><h2 class="ft">{E(t)}</h2>{f'<p class="fte" lang="en" dir="ltr">{E(f["title"])}{" · " + str(f["year"]) if f.get("year") else ""}</p>' if f.get("title") and f.get("title") != t else ""}
<div class="fchips">{"".join(chips)}</div>{f'<p class="fg">{genres}</p>' if genres else ""}</div></div></section>
<div class="acts">{trailer}{ask}</div>
{about}<section class="nearest" data-nearest hidden><h2>{tr('أقرب عرض لك')}</h2><div data-nearest-row></div></section>
{verdict}{self.family(f)}{where}{crew}
<section class="sec ask" data-ask data-fid="{E(fid)}" data-lang="{LANG}"><h2>{tr('اسأل الفيلم')}</h2><p class="lead">{tr('اسأل أي شي عن الفيلم، ونجاوبك من قصته ومعلوماته بس. اللي يحرق نخفيه لين تضغط')}.</p>
<form class="ask-f" data-ask-form><input name="q" maxlength="240" autocomplete="off" enterkeyhint="send" placeholder="{tr('مثلاً: يناسب العيال؟')}" aria-label="{tr('سؤالك')}"><button class="btn velvet" type="submit">{tr('اسأل')}</button></form>
<div class="chips wrap">{"".join(f'<button type="button" class="chip" data-ask-q="{tr(q)}">{tr(q)}</button>' for q in ASK_QS)}</div><div class="ask-out" data-ask-out></div></section>
</div>{self.sheet()}"""
        mv = {"@type": "Movie", "name": t, "url": SITE + self.u("f", fid), "inLanguage": LANG}
        if f.get("title") and f["title"] != t: mv["alternateName"] = f["title"]
        if f.get("poster_2x") or f.get("poster"): mv["image"] = SITE + (f.get("poster_2x") or f.get("poster"))
        if f.get("runtime"): mv["duration"] = f"PT{int(f['runtime'])}M"
        if f.get("rating"): mv["contentRating"] = f["rating"]
        if f.get("genres"): mv["genre"] = [tr(GENRE_AR[g]) for g in f["genres"] if g in GENRE_AR]
        if f.get("director"): mv["director"] = {"@type": "Person", "name": f["director"]}
        if f.get("synopsis_ar") or f.get("synopsis_en"): mv["description"] = (f.get("synopsis_ar") or f.get("synopsis_en"))[:300]
        self._ld = [mv, {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": f"{tr('سينما')}", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": t, "item": SITE + self.u("f", fid)}]}]
        # the next shows as ScreeningEvent (today first, then tomorrow; 24 at most), in site_kit's one shape
        live_shows = sorted((x for x in shows if x in self.shows), key=lambda x: (x["date"], x["time"] < "04:00", x["time"]))
        self._ld += [k.screening_ld(x, LANG) for x in live_shows[:24]]
        self._og = SITE + (f.get("poster_2x") or f.get("poster")) if (f.get("poster_2x") or f.get("poster")) else None
        today_shows = [x for x in live_shows if x["date"] == k.today]
        ncin = len({x["cinema"] for x in today_shows})
        prices = [p["aed"] for x in today_shows for p in (x.get("prices") or []) if (p.get("aed") or 0) > 0]
        cities = [cityname(c) for c, _ in CITIES if any(k.cinemas[x["cinema"]].get("city") == c for x in today_shows)]
        when = f"{tr('اليوم في')} {ncin} {('cinema' if ncin == 1 else 'cinemas') if LANG == 'en' else 'سينما'}" if ncin else f"{tr('بكرة في سينمات الإمارات')}"
        ttl = f"{t} — {tr('مواعيد')} {when}" + (f"{tr('، من')} {int(min(prices))} {tr('درهم')}" if prices else "") + (f" | {tr('سينما الإمارات')}" if ncin else "")
        desc = (f"{t}: {len(today_shows)} {tr('عرض اليوم في')} {'، '.join(cities[:4])}" + (f"{tr('، التذكرة من')} {int(min(prices))} {tr('درهم')}" if prices else "") + ". "
                if today_shows else f"{t} {tr('في سينمات الإمارات بكرة')}. ") + (syn or syn_en or "")[:120]
        self.page(self.u("f", fid), ttl, desc, body, "film", canon=f"{SITE}/film/{fid}/")
        self._ld, self._og = [], None

    # -------- cinema page
    def cinema(self, cid):
        self.fresh()
        k, c = self.k, self.k.cinemas[cid]
        shows = [s for s in self.shows + self.past if s["cinema"] == cid]
        films = sorted({s["film"] for s in shows}, key=lambda f: (-self.count.get(f, 0), title(k, f)))
        rows = ""
        for fid in films:
            f = k.films[fid]
            sc, kind = score(f)
            meta = " · ".join(x for x in [runtime(f), E(f.get("rating") or ""), (("★ " + sc + " IMDb") if kind == "imdb" else (f"{tr('النقاد')} " + sc)) if sc else ""] if x)
            rows += (f'<div class="frow" data-fid="{E(fid)}"><a class="fr-p" href="{self.u("f", fid)}">{self.poster(fid, cls="pst sm")}</a>'
                     f'<div class="fr-b"><a class="fr-t" href="{self.u("f", fid)}">{E(title(k, fid))}</a><p class="fr-m">{meta}</p>'
                     f'<div class="times">{self.times([s for s in shows if s["film"] == fid])}</div></div></div>')
        ll = f'{c["lat"]},{c["lng"]}' if c.get("lat") is not None else ""
        maps = f"https://www.google.com/maps/dir/?api=1&destination={ll}" if ll else (c.get("maps") or "")
        waze = f"https://waze.com/ul?ll={ll}&navigate=yes" if ll else ""
        name = f"{self.chain(cid)} — {self.cname(cid)}"
        body = f"""<div class="pg cinema">{self.bar(name, right=self.share_btn(name + " — " + tr("المواعيد")))}
<section class="chead">{self.mark(cid, "lg")}<div><h2>{E(self.cname(cid))}</h2>
<p>{E(cityname(c.get("city")))}</p></div><button type="button" class="fav big" data-fav="{E(cid)}" aria-label="{tr('سينماتي')}" aria-pressed="false">{svg("staro")}{svg("star")}</button></section>
<div class="acts">{f'<a class="btn ghost" href="{E(maps)}" target="_blank" rel="noopener">{svg("map")}Google Maps</a>' if maps else ""}{f'<a class="btn ghost" href="{E(waze)}" target="_blank" rel="noopener">{svg("map")}Waze</a>' if waze else ""}</div>
<section class="sec">{self.dayswitch()}<div class="films">{rows}</div><p class="empty" data-past hidden>{tr('خلصت عروض اليوم هني، شوف بكرة')}.</p></section>
</div>{self.sheet()}"""
        th = {"@type": "MovieTheater", "name": name, "url": SITE + self.u("c", cid)}
        if c.get("address"): th["address"] = c["address"]
        if c.get("lat") is not None: th["geo"] = {"@type": "GeoCoordinates", "latitude": c["lat"], "longitude": c["lng"]}
        live_shows = sorted((x for x in shows if x in self.shows), key=lambda x: (x["date"], x["time"] < "04:00", x["time"]))
        self._ld = [th, {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": f"{tr('سينما')}", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": cityname(c.get("city")), "item": SITE + self.pfx + "/#cinemas"},
            {"@type": "ListItem", "position": 3, "name": name, "item": SITE + self.u("c", cid)}]}]
        self._ld += [k.screening_ld(x, LANG) for x in live_shows[:24]]
        today_shows = [x for x in live_shows if x["date"] == k.today]
        nf = len({x["film"] for x in today_shows})
        prices = [p["aed"] for x in today_shows for p in (x.get("prices") or []) if (p.get("aed") or 0) > 0]
        ts = [x["time"] for x in today_shows]
        ttl = f"{name} — {nf} {tr('فيلم اليوم ومواعيدها')}" if nf else f"{name} — {tr('أفلام بكرة ومواعيدها')}"
        desc = (f"{nf} {tr('فيلم اليوم في')} {name}{tr('، أول عرض')} {t12(hm(ts[0]))[0]} {t12(hm(ts[0]))[1]} {tr('وآخر عرض')} {t12(hm(ts[-1]))[0]} {t12(hm(ts[-1]))[1]}"
                + (f"{tr('، التذكرة من')} {int(min(prices))} {tr('درهم')}" if prices else "") + f". {tr('المواعيد والأسعار والحجز')}." if ts
                else f"{tr('أفلام')} {name} {tr('بكرة بمواعيدها وأسعارها')}.")
        self.page(self.u("c", cid), ttl, desc, body, "cinema", canon=f"{SITE}/{c.get('city')}/{cid}/")
        self._ld = []

    # -------- the ticket sheet (one per page, filled by the script)
    def sheet(self):
        return f"""<template id="aed">{dirham()}</template><section class="sheet" data-sheet role="dialog" aria-modal="true" aria-labelledby="tk-film" hidden>
<div class="grab" data-grab></div><div class="tk"><div class="tk-top"><div><p class="tk-cin" data-tk-cin></p><h3 id="tk-film" data-tk-film></h3><p class="tk-when" data-tk-when></p></div>
<div class="tk-time"><small data-tk-day></small><b data-tk-time></b></div></div>
<table class="tk-seats"><tbody data-tk-seats></tbody></table>
<a class="btn velvet wide" data-tk-book target="_blank" rel="noopener nofollow">{tr('احجز')}</a>
<div class="tk-row"><button type="button" class="btn ghost" data-tk-share>{svg("share")}{tr('شارك')}</button><button type="button" class="btn ghost" data-tk-close>{tr('سكّر')}</button></div></div></section>"""

    # -------- assets
    def assets(self):
        a = os.path.join(self.out, "assets")
        os.makedirs(os.path.join(a, "fonts"), exist_ok=True)
        for fn in os.listdir(os.path.join(HERE, "fonts")):
            if fn.endswith(".woff2"):
                shutil.copy(os.path.join(HERE, "fonts", fn), os.path.join(a, "fonts", fn))
        css = open(os.path.join(HERE, "app.css"), encoding="utf-8").read().replace("__BASE__", self.base)
        js = open(os.path.join(HERE, "app.js"), encoding="utf-8").read()
        self.css_name = f"app.{hashlib.sha1(css.encode()).hexdigest()[:10]}.css"
        self.js_name = f"app.{hashlib.sha1(js.encode()).hexdigest()[:10]}.js"
        open(os.path.join(a, self.css_name), "w", encoding="utf-8").write(css)
        self.logos = {}                          # chain -> its icon, content-hashed like the rest of assets/
        os.makedirs(os.path.join(a, "logos"), exist_ok=True)
        for fn in sorted(os.listdir(os.path.join(HERE, "logos"))):
            if fn.endswith(".webp"):
                raw = open(os.path.join(HERE, "logos", fn), "rb").read()
                name = f"{fn[:-5]}.{hashlib.sha1(raw).hexdigest()[:10]}.webp"
                open(os.path.join(a, "logos", name), "wb").write(raw)
                self.logos[fn[:-5]] = f"{self.base}assets/logos/{name}"
        open(os.path.join(a, self.js_name), "w", encoding="utf-8").write(js)

    def run(self):
        if not self.live:                       # the preview owns its folder; live writes over the old build's pages only
            shutil.rmtree(self.out, ignore_errors=True)
        os.makedirs(self.out, exist_ok=True)
        self.assets()
        self.home()
        if os.environ.get("APP_SAMPLE") and not self.live:
            self.home(self.base + "sample/", merged=True)
        for fid in self.films:
            self.film(fid)
        for cid in self.cins:
            self.cinema(cid)
        return 1 + len(self.films) + len(self.cins)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "latest.json"))
    ap.add_argument("--discounts", default=os.path.join(ROOT, "discounts.yaml"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out_app"))
    ap.add_argument("--base", default="/")
    ap.add_argument("--live", action="store_true", help="the main site: old URLs, indexable, over out/'s old pages")
    ap.add_argument("--lang", default="ar", choices=("ar", "en"), help="the site's language (en: under /en/ when --live)")
    a = ap.parse_args()
    data = json.load(open(a.data, encoding="utf-8"))
    global LANG
    LANG = a.lang
    base = ("/en/" if a.lang == "en" else "/") if a.live else a.base
    app = App(data, load_discounts(a.discounts), Halls(os.path.join(ROOT, "halls.yaml")), a.out, base, live=a.live)
    n = app.run()
    print(f"app: {n} pages -> {a.out} (base {app.base})")


if __name__ == "__main__":
    main()
