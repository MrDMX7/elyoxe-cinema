# «سينما» Phase 1 — the new site on cinema.elyoxe.com

Approved by the owner 2026-09-26 ("اعتمدناه، ابدأ ببناء المرحلة 1"). Visual reference: the canvas
https://claude.ai/artifact/RMPaFgCa5udRTtvx3FuzDn, row «هـ» (E-Home, E-Film, E-Desk-Home, E-Desk-Film).
Everything the current site does keeps working (all pages, ar + en, SEO, discounts, verdicts, refresh on the Fold).

## Identity (binding)
- Name «سينما» / "Cinema". Own identity, nothing from elyoxe.com's look (no Plex, no paper).
- Colors: night `#0F0B0C` (ground) · velvet `#7A1626` (glow behind headlines, the group button) · marquee gold
  `#E2B659` (prices, verdict word, selected state ONLY) · screen light `#F1EAE0` (text, ticket paper) ·
  seat grey `#A89C8E` (secondary text) · live green `#5FC9A0` ("starting now", switches ON — nothing else).
  Ticket ink `#1A1206`, ticket rule `#B9A987`.
- Type: **Markazi Text 700** for Arabic display (titles, film names, wordmark, verdict word); **Readex Pro**
  (300–600) for body, English, every number and time. Self-hosted woff2 subsets (OFL), `font-display: swap`.
- Brief rules: no facts strung with middle dots (tables or plain sentences), no all-caps, no numbered
  eyebrows, no arrows glued on links, no rounded boxes, no drop-shadow cards (the one exception: the hero
  poster's velvet glow). Poster is the hero. One signature moment: **prices reprice live when the card
  changes**, digits drawn on a flip-board; the "now" time uses the same flip tiles.
- Arabic RTL derived (logical properties); English mirror at `/en/`.

## Domain
- `https://cinema.elyoxe.com/` (ar) and `/en/`. Paths: `/<city>/`, `/<city>/<cinema>/`, `/film/<fid>/`,
  `/cards/<card>/`, `/halls/`, `/sitemap.xml`, `/data/…`, `/manifest.webmanifest`, `/sw.js`.
- New S3 bucket + CloudFront distribution + ACM cert (us-east-1) + Route53 alias in zone
  `Z092471334IO8THU6C3A9`. Old `elyoxe.com/cinema/*` and `/en/cinema/*` → 301 to the same path on the
  subdomain (CloudFront function on those two behaviors). robots.txt of the subdomain lists its sitemap.

## Features in phase 1 (numbers = the owner's list)
- Poster on every film (mirrored to our bucket as WebP 342w + 684w; dominant color extracted for the
  ambient glow). Missing poster → typographic tile in the film's color, never a broken image.
- Runtime and «يخلص تقريباً HH:MM» = start + chain ad offset (default 15 min, per chain in config) +
  the chain's own runtime (UAE cut). Always labelled «تقريباً».
- Two flows: film → cinemas → times → ticket sheet; cinema → films → times → ticket sheet. A time is a
  button; it opens the ticket (phone: bottom sheet; desktop: side panel) with seat classes, price before/
  after the chosen card, conditions, seats left when known, «احجز» deep link, «أرسلها للقروب» (Web Share
  API, WhatsApp fallback link).
- Nearest cinema: geolocation on request only; distances client-side from `cinemas.yaml` lat/lng (all 66
  must have coordinates); city auto-picked from the nearest cinema.
- (1) «الحين»: nearest show starting within 45 min, one tap. (2) «مع منو رايح؟» بروحي / ربعي / العائلة /
  العيال → filter+sort presets. (3) «يخلص قبل» time filter. Filters: genre, «عائلي» (G/PG/PG13),
  «للأطفال» (G/PG + animation/family). (7) Sort by price after the chosen card. (13) Language/subtitles
  per show. (15) Trailer on tap (YouTube nocookie embed, loaded only on click; id from the chain or
  Wikidata P1651). (28) «راعِ أوقات الصلاة» switch (off by default, saved): marks shows overlapping
  Maghrib/Isha and can hide them; times computed client-side with the adhan method already used by
  /tools (Dubai method + measured offsets). (29) «الوصول»: Google Maps / Waze to the cinema's coordinates.
  (12) PWA: manifest, icons, service worker (network-first HTML, cache-first assets, offline page).
- Cards: only cards with at least one confirmed (official) discount appear anywhere; third-party and
  unconfirmed rules are hidden.
- State (city, card, companions, ends-before, prayer switch, sort) persists in localStorage (try/catch).

## Data additions (refresh → latest.json)
Per film: `poster` (our URL), `poster_color`, `trailer` (youtube id), `genres` (en keys + ar labels),
`kids`/`family` flags derived from the UAE rating + genre. Per show: `lang`, `subs` when the chain gives
them, `ends` (HH:MM). Per cinema: `lat`, `lng`, `maps`. Per chain: `ad_offset_min`.

## Budgets
Mobile Lighthouse ≥ 90 on home and a film page; HTML ≤ 150 KB/page; JS ≤ 45 KB gz total; LCP image is
the first poster, preloaded, WebP. Keyboard focus visible; `prefers-reduced-motion` turns off the flip
animation and the sheet slide.
