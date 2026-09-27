# «سينما» Phase 3 — Batch A Implementation Plan (speed, sharing, trust)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship roadmap items 237, 206, 82, 203, 204, 138, 81 (+ /people/ index) and the ops fix that unblocks hourly refresh, as one small release.

**Architecture:** Same pipeline; features added as pages/ and steps/ plug-ins (docs/PLUGINS.md), client modules under src/js, one infra function for geolocation. Work on branch `phase3a` in a separate worktree; release = merge to main (docs/CUTOVER-PHASE2.md merge route).

**Tech Stack:** Python 3.13, Pillow, vanilla JS, CloudFront Functions, pytest + node tests.

**Spec:** docs/ROADMAP.md (item numbers) + docs/superpowers/specs/2026-09-26-phase1-design.md (identity) + 2026-09-27-phase2-design.md (rules).

## Global Constraints
- «هـ» identity, Western digits, no invented numbers, «تقريباً» on estimates, confirmed discounts only, ar + /en/, HTML ≤150 KB/page (target ≤125), JS main bundle ≤45 KB gz (features lazy when large), Lighthouse mobile ≥90 on home and a film page.
- No tracking; location/IP never stored or sent to third parties.
- Commits end with "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"; never commit to main directly.

---
### Task A1: Ops — failure state and hourly
run.sh / run-job.sh: an ongoing, already-alerted failure records status=degraded (not ok) and sends one reminder per day while it lasts; tests. Hourly cron flip only after this lands AND a full day of phase-2 runs are clean (controller does the flip).

### Task A2: City from the network (237)
A same-origin endpoint (CloudFront Function or the tools' /api/ip pattern) that returns the viewer's UAE city (from CloudFront viewer geolocation) or nothing; the client uses it only when no city is saved; never logged. Infra script dry-run first, then apply on the cinema distribution only.

### Task A3: Sharing (206, 82)
Per-film Open Graph image (1200×630 PNG, Pillow, poster + title + «من X درهم الليلة في <المدينة الأكثر عروضاً>» + date) rebuilt each run, cached by content hash; og:image per film page (ar/en). Share links carry ?city=&card= and the page applies them (without overwriting a user's saved choice silently — ask once).

### Task A4: Feel (203, 204, 138)
Speculation Rules (prerender on hover/touchstart for same-origin film/cinema links, moderate eagerness, excluded when data-saver or reduced data), View Transitions (poster → film hero, cross-document, with reduced-motion off-switch), PWA manifest shortcuts (الحين، نازل الخميس، قائمتي).

### Task A5: Search (81) + /people/ index
Client search over a compact index (films ar/en titles + common Arabic/English transliterations, cinemas, malls, people) with fuzzy matching tolerant of Arabic letter variants (ا/أ/إ/آ، ة/ه، ى/ي) and typos; results as you type; «/» shortcut on desktop; /people/ and /en/people/ index pages (A–Z / ا–ي, showing now first).
