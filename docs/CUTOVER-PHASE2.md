# «سينما» phase 2 release — merge `phase2` into `main`

Prepared 2026-09-27 (integration wave). **Nothing here has been run.** Merging is the release: the Fold's
cinema job pulls `main` at its next run (cron :10 of 06, 12, 18, 23 Asia/Dubai; hourly after the phase-1
step 6), runs the suite as its gate, refreshes, and deploys to https://cinema.elyoxe.com by itself.

What changes on the live site: people pages (`/people/<slug>/`), «نازل الخميس» (`/coming/`), «عربي وخليجي»
(`/arabic/`), events (`/events/`), question pages (`/q/<slug>/`), `/prices/` and `/boxoffice/`, `/kids/` and
`/summer/` (and `/eid/` in its window), hall maps and «باقي N مقعد» in the ticket, double features, mall
closing and snacks on cinema pages, compare / «شي يشبه» on film pages, three more links in the nav.

What changes in the bucket: the price history moves out of the site's bucket. It used to be
`s3://elyoxe-cinema-574771023173/state/price_history.jsonl`, which the distribution serves publicly (it answered
200 at `https://cinema.elyoxe.com/state/price_history.jsonl` on 2026-09-27). It now lives at
`s3://elyoxe-media-574771023173/cinema-state/price_history.jsonl` — a private bucket (public access blocked, no
bucket policy) that no CloudFront distribution uses as an origin, so **no infra or CloudFront change is needed**.
The first live run reads the old copy, merges it into the new object, and deletes the old copy only after the new
object holds all of it (`steps/history.py`; a failed read or upload keeps it). `deploy.sh` still excludes
`state/*` from its `--delete` passes, so nothing else removes it.

---

## 1. Pre-merge checks (laptop, `C:/Users/requi/cinema-phase2`, branch `phase2`)

```bash
git fetch origin
git status -sb                                  # clean, not behind origin/phase2
git log --oneline phase2..origin/main           # the Fold's own commits (verdicts) not yet in phase2
git merge origin/main                           # only if the line above printed anything; verdicts/: keep both
python -m pytest -q -p no:cacheprovider         # then: echo $?  -> 0   (no pipe: `| tail` hides the exit code)
```

The suite refuses the network (conftest.py): a green run proves no test depended on a live site.

Budgets (the suite checks the 150 KB rule and the 130 KB Dubai page on `data/latest.json`; this checks the target):

```bash
PREVIEW=1 python build.py
find out -name "*.html" -size +125k            # expect nothing, or only dubai/index.html (a phase-1 page, ~126 KB
                                               # at a busy morning; its size is fixed by the golden test)
```

Walk-through of the PREVIEW build — `python -m http.server 8767 --directory out`, then at 375 px and at desktop
width, one page of each type, Arabic and English:

| page | look for |
|---|---|
| `/people/<slug>/` (any from `ls out/people`) | name, 2-line bio with its Wikipedia link, «يعرض له الحين». Photos come from the bucket (`/posters/people/…`), so locally they show as broken images — live they load |
| `/coming/` | grouped by release Thursday, «بعد 4 أيام» countdowns, trailer links |
| `/arabic/`, `/events/` | lists, or an honest empty state (noindex) |
| `/q/` and two `/q/<slug>/` | numbers with their dates; an unanswerable question says so (noindex) |
| `/prices/`, `/boxoffice/` | tables; «زاد/نقص» hidden under 30 days of history |
| `/kids/`, `/summer/` | kids shows before 14:00; summer noindex outside July–August |
| a film page | the collapsed «فيلمين ورا بعض» (two per city), the compare box, no sideways scroll at 375 px |
| a cinema page (`/dubai/reel-dubai-mall/`) | mall closing time, snacks, double features, «باقي N مقعد» under times; open a ticket → the hall drawing and best seat |
| the phone nav | one row that scrolls sideways (7 links) |

## 2. Merge and push (laptop)

```bash
cd C:/Users/requi/workspace/saas/cinema               # main is checked out here (phase2 is the worktree)
git checkout main && git pull --ff-only origin main
git merge --no-ff phase2 -m "phase 2: people, coming, hubs, questions, seats, insights, seasons (merge phase2)"
                                                      # a conflict in verdicts/: take main's side (the Fold wrote it)
python -m pytest -q -p no:cacheprovider               # echo $? -> 0 on the merge itself
git push origin main
```

Best time: right after a scheduled run has finished (e.g. 12:40), so the first phase-2 run is the next :10 and
you can watch it — or start it by hand on the Fold (`bash run.sh`, foreground; its flock makes an overlapping
scheduled run skip).

## 3. The first run on the Fold — what to expect

Measured 2026-09-27. The laptop numbers are a real `python refresh.py` of this branch (no verdicts, bucket off);
the Fold numbers are its own cinema.log for the phase-1 code now on `main`.

| | laptop, phase 2 | Fold, phase 1 (log) |
|---|---|---|
| test suite (run.sh gate) | 3 min 36 s (561 tests) | — (the phase-1 suite also waited ~1 min on coming-soon feeds; gone now) |
| first run of the day (price sampling) | 35 min 38 s: chains 28 min, steps 6 min 48 s | 24–31 min per run, 06:10 → 06:34 |
| a later run (daily price cache warm) | 8 min 12 s: chains 6 min 30 s, steps 1 min 32 s | 9 min 19 s (12:10 → 12:19) |
| steps, first run | occupancy 241 s · people 152 s · coming 15 s · events/history/last_chance < 1 s | — |
| steps, warm | occupancy 74 s · coming 15 s · people 3 s | — |
| PREVIEW build | 18 s, 744 pages | — |

The phase-2 steps are bounded: people stops at 300 s (the rest waits in `data/people_cache.json` for the next
run), the occupancy sampler at 240 s (+45 s for a last request), ≤ 60 requests per chain. So a phase-2 run on the
Fold is at most ~11 minutes longer than a phase-1 run: the worst first run ≈ 31 + 11 + the suite ≈ 45–50 minutes,
inside the hour. Under hourly cron a run that is still going makes the next one skip (`flock -n` in run.sh) —
no overlap, no double deploy.

The first run also: fetches ~122 people from Wikidata/Wikipedia (≈125 requests) and uploads their photos to
`posters/people/` (the laptop's test run already uploaded 198 files there on 2026-09-27, so most are skipped);
mirrors ~110 coming-soon posters; starts `data/seatmaps.json`, `data/occupancy.json`, `data/people_cache.json`
on the Fold; moves the price history (above). `health.json` has `steps.items.<name>.sec` for each step's time.
Cinema City has no coming-soon endpoint: `health.steps.items.coming.chains.cinemacity.ok` is false by design.

## 4. Verify live (after the first phase-2 deploy)

```bash
S=https://cinema.elyoxe.com
for p in / /en/ /coming/ /people/ /arabic/ /events/ /q/ /prices/ /boxoffice/ /kids/ /summer/; do
  printf '%s %s\n' "$(curl -s --compressed -o /dev/null -w '%{http_code}' "$S$p")" "$p"; done
                                     # 200 for each (/people/ has no index page: 404 is expected there)
curl -s --compressed -o /dev/null -w '%{http_code}\n' "$S/state/price_history.jsonl"   # 404 (was 200)
aws s3 ls s3://elyoxe-media-574771023173/cinema-state/                              # price_history.jsonl
aws s3 ls s3://elyoxe-cinema-574771023173/state/                                     # empty
ssh root@100.92.45.87 'cd /root/workspace/saas/cinema && python3 -c "import json;h=json.load(open(\"data/health.json\"));print({n:(r[\"ok\"],r.get(\"sec\")) for n,r in h[\"steps\"][\"items\"].items()})"'
                                     # every step ok (coming ok with cinemacity false inside); history shows "legacy": "moved"
curl -s --compressed "$S/sitemap.xml" -o /tmp/sm.xml; grep -c "<loc>" /tmp/sm.xml   # ~740 (316 before)
```

Then open a busy film page and a cinema page on a phone: «باقي N مقعد» under a time starting within 3 hours,
the ticket's hall drawing, the collapsed double-features list.

## 5. Rollback

```bash
cd C:/Users/requi/workspace/saas/cinema
git checkout main && git pull --ff-only origin main
git revert -m 1 <the merge commit> --no-edit          # keeps the Fold's later verdict commits
git push origin main
```

The Fold's next run deploys the phase-1 build; `deploy.sh`'s `--delete` removes the phase-2 pages. The price history
stays in the media bucket (harmless; phase 1 never reads it) — but if the revert comes after the move, phase 1's
code has no history step, so nothing writes the old public copy back. The phase-2 state files on the Fold
(`data/seatmaps.json`, `occupancy.json`, `people_cache.json`, `price_history.jsonl`) are ignored by phase 1 and
can stay. Re-release later by reverting the revert.
