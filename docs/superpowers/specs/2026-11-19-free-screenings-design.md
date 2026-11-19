# «عروض مجانية»: free and community film screenings (2026-11-19)

**Asked:** the owner approved it from a list of ideas («حلو نشتغل عليه»), then «Yes, start».
**Live at:** `/free/` and `/en/free/`.

## What it is

The page lists films shown free, or for a small fee, outside the chains:
- park and beach cinemas;
- museums and universities;
- festivals.

Each card shows:
- the time (12-hour);
- the title and venue;
- the emirate;
- an entry tag: «ببلاش», a price in AED, or «الدخول في الرابط»;
- «بالتسجيل» when the organiser asks you to book;
- a link to the organiser's own page.

The cards are grouped by day. A run of days, such as a festival month, comes first. Chips filter the cards by emirate in place. The page opens on the visitor's saved city when that city has screenings.

## Where it comes from

`steps/free_screenings.py` runs on every refresh. It reads four sources with plain requests, no browser:

| Source | Read from | Kept |
|---|---|---|
| JLT Cinema Under the Stars | the page's HTML (the whole season line-up) | every Saturday, free |
| NYU Abu Dhabi Arts Center | `events.ppeventslist.en.upcoming.json`, then each event page | `event_type` Screening. Venue from the event page (it can be off campus); «not ticketed» means free |
| Cinema Akil | `/api/films` | only sessions where every price is 0 |
| Alserkal Avenue | the events page (Webflow), then each event page | cards labelled «Film Screening». Time from «Open Hours» |

`free_screenings.yaml` holds what no script can read, entered by hand from the organiser's own page. Each entry has a `checked` date.
- **Pages that block scripts:** Louvre Abu Dhabi, and Dubai Holding's «Movie Under the Stars» in 17 communities.
- **Yearly festivals:** for example, Emirati Film Month at the Cultural Foundation.
- **Instagram-only programmes.**

**When a source fails:** it keeps its last good items from the previous `latest.json` while they are still to come.

**What gets dropped:** anything past its last day, or more than 75 days out.

## The survey behind the sources (2026-11-19)

19 sources and 5 aggregator calendars were checked by fetching them. None has an iCal feed or the Events Calendar plugin.

- **Read automatically:** the four above.
- **Plain readers, but off-season now** (to add when their next season is announced): Jameel Arts Centre (WordPress REST `whats-on` with a films category; the date is only on the event page), Sharjah Art Foundation (HTML list labelled Film / Free), Goethe-Institut (RSS for the whole Gulf; the event pages 403 to scripts).
- **Hand list:** Louvre Abu Dhabi, Dubai Holding communities, Expo City Winter City, Cultural Foundation festivals, Manarat Al Saadiyat Cinema Space, the Korean Cultural Center, The Culturist, Institut français, the EU and Italian film festivals, and the Sharjah children's film festival.
- **Aggregators** (Visit Dubai, Visit Abu Dhabi JSON, Visit Sharjah, Platinumlist, Time Out): none lists film screenings well. They are only useful as alerts.
- **Gap:** Ajman, Umm Al Quwain and Fujairah have nothing found. Ras Al Khaimah has only the EU film festival in June.

## Where it shows

- **Home:** a row at the top of the «قريباً» tab, with the count.
- **Footer:** the first link on every page of the app design.
- **Sitemap:** `pages/free.py`, both languages, only while there is something on the page.
- **Structured data:** JSON-LD `Event` for each item, with `isAccessibleForFree` when free.

## Tests

- `tests/test_free_screenings.py`: each reader against the sources' own responses of 2026-11-19 (`tests/fixtures/free/`), the hand list's fields, the merge and its carry-over, and JSON safety.
- `tests/test_free_page.py`: the page in Arabic and English, the home row and footer, the sitemap rule, and the filter script.
