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

## 2. Merge and push (laptop), then land it on the Fold

**Line endings first (final review C1).** `fixtures/sample_latest.json` and `src/og_make.py` (and 21 other blobs
committed with CRLF before `.gitattributes`) show as modified on both checkouts although only their line endings
differ. phase2 renormalizes exactly these paths, so `git merge` on the laptop and `git pull --ff-only` on the
Fold both abort ("Your local changes … would be overwritten"). Clear them — only after proving the diff is
line endings only; any other diff is real work: stop and look.

```bash
cd C:/Users/requi/workspace/saas/cinema               # main is checked out here (phase2 is the worktree)
git status --short                                    # expect only EOL-dirty tracked files (and untracked data/)
git diff --ignore-all-space --quiet && echo EOL-ONLY  # must print EOL-ONLY; if not, STOP
git checkout -- fixtures/sample_latest.json src/og_make.py   # or: git reset --hard origin/main (EOL-only proven)
git checkout main && git pull --ff-only origin main
git merge --no-ff phase2 -m "phase 2: people, coming, hubs, questions, seats, insights, seasons (merge phase2)"
                                                      # a conflict in verdicts/: take main's side (the Fold wrote it)
python -m pytest -q -p no:cacheprovider               # echo $? -> 0 on the merge itself
git push origin main
```

Then **immediately on the Fold** (between runs: check `data/.run.lock` is free and the time is not :10–:50
of 06/12/18/23 Asia/Dubai). The laptop's `data/price_history.jsonl` goes over first (final review M2: it holds
the laptop's real sampled days; the old public bucket copy is already gone, so without it the history starts
from zero):

```bash
# ssh lands inside the Debian chroot (cron reaches the same place through /data/local/debian-boot.sh -c)
scp C:/Users/requi/workspace/saas/cinema/data/price_history.jsonl \
    root@100.92.45.87:/root/workspace/saas/cinema/data/price_history.jsonl     # (or the phase2 worktree's copy)
ssh root@100.92.45.87 'cd /root/workspace/saas/cinema && TZ=Asia/Dubai date \
  && flock -n data/.run.lock true && git status --short \
  && git diff --ignore-all-space --quiet && echo EOL-ONLY \
  && git fetch -q origin && git reset --hard origin/main && git status -sb && free -m'
      # EOL-ONLY, then "## main...origin/main" clean on the merge commit; available >= 2000.
      # reset --hard leaves ignored/untracked data/ alone (price_history.jsonl, caches, .last_pages).
ssh root@100.92.45.87 '/root/workspace/automation/phone/run-job.sh cinema'
      # the cron wrapper (wake lock, memory wait) around run.sh, in the foreground -- never nohup
```

run.sh now stops on a failed `git pull` (final review M3): `FAILED: git pull …`, one notification, exit 7,
nothing deployed — instead of deploying the old code with a WARN. Manual check of that path: in a scratch
clone with no upstream (`git init`, copy run.sh, alerts.py, statefile.py), `bash run.sh` prints
`FAILED: git pull …` and exits 7; a second run stays quiet (already alerted).

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
`posters/people/` — all of them once (final review M2: the Fold has no `data/people_uploads.json` ledger yet, so
the ~198 WebPs the laptop's test run put there go up again; same URLs, small files, harmless);
mirrors ~110 coming-soon posters; starts `data/seatmaps.json`, `data/occupancy.json`, `data/people_cache.json`
on the Fold; and starts the price history in the media bucket. The "move" above no longer happens: phase 1's
`deploy.sh` (no `state/*` in its KEEP list) already deleted the old public copy on a `--delete` pass, and that copy
was only the laptop's Task-5 test data — so `health.steps.items.history` shows `"new": true` and no `legacy`
key. The history is the Fold's `data/price_history.jsonl` unioned with the bucket copy: copy the laptop's file
over before the first run (§2) or it starts from today. `health.json` has `steps.items.<name>.sec` for each step's time.
Cinema City has no coming-soon endpoint: `health.steps.items.coming.chains.cinemacity.ok` is false by design.

## 4. Verify live (after the first phase-2 deploy)

```bash
S=https://cinema.elyoxe.com
for p in / /en/ /coming/ /people/ /arabic/ /events/ /q/ /prices/ /boxoffice/ /kids/ /summer/ /eid/; do
  printf '%s %s\n' "$(curl -s --compressed -o /dev/null -w '%{http_code}' "$S$p")" "$p"; done
                                     # 200 for each (/people/ has no index page: 404 is expected there;
                                     # /eid/ is 404 outside its 10-day window; /summer/ is 200 but noindex
                                     # and absent from sitemap.xml outside July–August — final review I2)
curl -s --compressed -o /dev/null -w '%{http_code}\n' "$S/state/price_history.jsonl"   # 404 (was 200)
aws s3 ls s3://elyoxe-media-574771023173/cinema-state/                              # price_history.jsonl
aws s3 ls s3://elyoxe-cinema-574771023173/state/                                     # empty
ssh root@100.92.45.87 'cd /root/workspace/saas/cinema && python3 -c "import json;h=json.load(open(\"data/health.json\"));print({n:(r[\"ok\"],r.get(\"sec\")) for n,r in h[\"steps\"][\"items\"].items()})"'
                                     # every step ok (coming ok with cinemacity false inside); history shows "new": true (M2)
curl -s --compressed "$S/sitemap.xml" -o /tmp/sm.xml; grep -c "<loc>" /tmp/sm.xml   # ~740 (316 before)
```

/boxoffice/ on the first days (final review M4): titled «هالأسبوع» but it covers only the days sampled so far
(today + a partial tomorrow on day one); its span line says so. Cosmetic until 7 days accrue — not a bug.

Then open a busy film page and a cinema page on a phone: «باقي N مقعد» under a time starting within 3 hours,
the ticket's hall drawing, the collapsed double-features list.

## 5. Rollback

```bash
cd C:/Users/requi/workspace/saas/cinema
git checkout main && git pull --ff-only origin main
git revert -m 1 <the merge commit> --no-edit          # keeps the Fold's later verdict commits
git push origin main
# deploy.sh refuses a build under half of the last one (deploy.sh: pages*2 >= data/.last_pages). After phase 2
# .last_pages is ~744 and a phase-1 build is 316 pages, so the rollback deploy would exit 5 and phase 2 would
# stay live (final review I1). Reset the floor before the Fold's next run:
ssh root@100.92.45.87 'rm -f /root/workspace/saas/cinema/data/.last_pages'
ssh root@100.92.45.87 '/root/workspace/automation/phone/run-job.sh cinema'   # or wait for the next :10
```

The Fold's next run deploys the phase-1 build; `deploy.sh`'s `--delete` removes the phase-2 pages. The price history
stays in the media bucket (harmless; phase 1 never reads it) — but if the revert comes after the move, phase 1's
code has no history step, so nothing writes the old public copy back. The phase-2 state files on the Fold
(`data/seatmaps.json`, `occupancy.json`, `people_cache.json`, `price_history.jsonl`) are ignored by phase 1 and
can stay. Re-release later by reverting the revert.
