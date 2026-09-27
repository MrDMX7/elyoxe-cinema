# «سينما» UI redesign — design («كأنك داخل Netflix»)

**Owner's request (2026-09-27):** «احس واجهة الموقع مب clean، اريدها احترافية واسطورية كانك داخل net flix، ماريد حشو خاصيات بطريقة مب حلوة، خل كل شي منظم ونظيف والصفحة تكون سينمائية وسهلة الاستخدام وبنفس الوقت لا تفرط بالميزات والخصائص اللي سويناها».
**Approved:** the mockup in `ui-mock/` (screens `phone-*.png`, `desk-*.png`; source `mock.css` + `gen.py`) — owner: «حلو».

## Principle
Nothing is deleted; everything moves to its natural place. The page leads with films, not controls. Identity is unchanged (night/velvet/gold/screen/seat/live tokens, Markazi Text + Readex Pro, no radius, no shadow cards except the hero poster's velvet glow, no middle-dot strings, no numbering of non-sequences, logical properties, Western digits, «عندي» not «معي»).

## Global chrome (every page)
- **Header, one line:** «سينما» mark · desktop links (الرئيسية، السينمات، نازل قريب، الأسعار والبطاقات) · search icon · **city pill** («العين ▾») · **card pill** («فزعة ▾», or «بطاقتي ▾» when none) · English link (desktop). Transparent gradient over a hero, solid `--night` + bottom rule once scrolled (and always on pages without a hero).
- The pills open a **sheet** (phone: bottom sheet; desktop: side panel): city list (all 7 cities, plus «قريب مني» geolocation) and card list (confirmed cards only, grouped gov/bank, the bank `<select>` goes away into this list). Choosing reprices the page exactly as today's state does (same storage keys, same events).
- **Phone tab bar: four** — الرئيسية، السينمات، نازل قريب، بحث (search opens the existing overlay). Icons + label.
- **Footer:** mark + links: السينمات، البطاقات والخصومات، من وين الأسعار (sources/freshness page), أسئلة، الناس (people index), English. Freshness per chain moves to the sources page.

## Home
1. **Billboard** (78vh, min 520, max 820): full-bleed **backdrop frame from the film's trailer** (see Backdrops), gradients to night at bottom and toward the text side. Eyebrow «الأكثر عرضاً في <city> الليلة», title (Markazi 64/96), verdict (gold verdict word + 2-line clamp), facts (RT, runtime, rating, genres — spaced, no dots), CTA: primary light button «الأوقات والأسعار  من <after-card price>», ghost «الإعلان» (existing trailer modal). Rotates among the city's top 5 (6 s, pauses on hover/focus/reduced-motion; indicator lines). No-JS: first film, static.
2. **«يبدأ قريب منك»** row (today's «الحين»/nearest feature): cards = small poster, time, «بعد N د» in live green, title, cinema + distance. Needs location or city; without either it shows the city's next starts.
3. **Poster rows** (horizontal scroll-snap, arrow buttons on desktop hover): الأكثر عرضاً الليلة · يستاهل · أرخص لك الليلة (after card) · للعائلة · نازل الخميس (from coming) · آخر فرصة (ending) · عربي · plus existing seasonal/hub rows if any. Each row has «الكل» linking to its page/filtered grid. Rows with < 4 films are skipped.
4. **Tile:** poster (2:3), title one line, «من <price> درهم» (gold number) or «السعر في الشباك». Optional corner tag (velvet) only for «الخميس»/«آخر أسبوع»/«جديد». Desktop hover: tile lifts a little and shows a small panel below with verdict word + next time (no layout shift).
5. **«كل الأفلام» grid** (3 cols phone, 7 desktop) with two chips: **«تصفية»** (opens the filter sheet; badge = number of active filters) and **sort** chip. The filter sheet holds everything that is today on the page: genre, «مع منو رايح؟», «لازم يخلص قبل», language, sort, prayer switch, and a result button «اعرض N فيلم» + «مسح».
6. Removed from home (moved): cities grid → city sheet + /cinemas/; cards list → card sheet + cards page; chain freshness → sources page.

## Film page
1. **Hero:** trailer backdrop, desktop poster at the side with the velvet glow, title (AR) + English title and year, verdict (3-line clamp, «المزيد» expands), facts, actions: الإعلان · شارك · قارن · (existing «ذكّرني»/alert if present).
2. **Sticky day bar** directly under the header: day tabs (اليوم/بكرة/weekday + date), the selected in gold.
3. **Schedule first:** per cinema, nearest first: name, distance, «الخريطة»; time buttons show time, hall, price after card; past shows faded; «يبدأ بعد N د» on the next one. City sections beyond the chosen city collapse to «N سينمات ثانية في <city>» / other cities under a disclosure.
4. **Ticket:** choosing a time → phone: a bottom dock (price after card, time/cinema/hall, «التفاصيل والحجز») that opens the existing ticket sheet; desktop: the existing ticket as a sticky side panel (empty state: «اختر وقت»). All existing ticket content (seats table, terms, share, Maps/Waze, seat map) stays.
5. **Tabs** below: عن الفيلم (synopsis, facts dl, archive note) · الطاقم · شي يشبه · فيلمين ورا بعض · قارن. No-JS: tabs are anchor links to sections stacked in that order.
6. The repeated «أنا في … وعندي» block is removed (header pills own city/card). Companions/prayer controls live in the home filter sheet; on the film page prayer is a switch inside the day bar overflow («⋯») sheet.

## Other pages
City, cinema, cards, halls, coming, seasons, hubs, people, insights, questions, venue pages keep their content but adopt the new chrome, tiles and section headings; any page-top control rows are replaced by the header pills.

## Backdrops (new data step)
`steps/backdrops.py`: for each showing film with a trailer and no cached backdrop: yt-dlp ≤720p video-only, ffmpeg samples 16 frames between 12%–80%, crop letterbox, score each frame (reject: mean luma < 35 or > 200; burned subtitles/title cards = high edge density in the bottom 22% or centred text band; low colourfulness) and keep the best; write WebP 1280w and 640w to `posters/bd-<fid>-<hash>-{1280,640}.webp`, record in `data/backdrops.json` (fid → files, source trailer id, frame time). Cached forever per trailer id; failures cached for 7 days. Fallback when none: today's poster-based `.bd`. Runs on the Fold inside run.sh (one heavy process; foreground; resumable because each film is cached as it completes; cap 8 new films per run).

## Budgets and checks
HTML ≤ 150 KB/page, JS ≤ 45 KB gz, Lighthouse mobile ≥ 90 home + film, 375 px with no horizontal scroll (measured with a real mobile viewport — Playwright `isMobile`, not headless Chrome's 500 px minimum), reduced motion honoured, focus visible, `npm`-free build, existing pytest + golden tests updated, JS/Python discount parity stays green.
