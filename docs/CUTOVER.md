# «سينما» cutover runbook — elyoxe.com/cinema → cinema.elyoxe.com

Prepared 2026-09-27 (phase 1, Task 5a). **Nothing here has been run.** The cutover changes the live
production site; it waits for the owner's go after he has seen the preview at https://cinema.elyoxe.com.

What changes: the Fold starts running the phase-1 code (four runs a day at first, hourly from step 6; deploying an indexable build to the new
stack), the old `elyoxe.com/cinema*` and `/en/cinema*` URLs answer 301 to the same path on
`cinema.elyoxe.com`, the studio's robots.txt points at the new sitemap, and the old objects in the tools
bucket go.

Names used below:

| what | value |
|---|---|
| new stack / bucket / distribution | `elyoxe-cinema` / `elyoxe-cinema-574771023173` / `E1200YJEC3LL6I` (ap-south-1) |
| elyoxe.com distribution | `E2QY4WECG1P5WO` |
| tools bucket (old cinema objects) | output `Bucket` of stack `elyoxe-tools` (ap-south-1) |
| studio bucket (elyoxe.com robots.txt) | `elyoxe-574771023173` |
| Fold | `ssh root@100.92.45.87`, workspace at `/root/workspace` |

Timing: the Fold's cinema job runs at :10 of 06, 12, 18 and 23 (Asia/Dubai) until step 6. Start right
after one of those runs has finished (e.g. 12:40) so steps 1–5 have a quiet window of hours. Every step
below is ordered: do not start one until the previous step's check passes.

**Step 2 starts immediately after step 1's push — before the Fold's next scheduled run.** Once the merge
is on `origin/main`, the Fold's next :10 run pulls it and does step 2 by itself, unattended. Run step 2 by
hand straight away (its flock makes a scheduled run that lands mid-way skip), and go on to step 3 without
a gap: between steps 2 and 3 both hosts are indexable.

---

## 0. Before you start (laptop, `saas/cinema`)

```bash
cd ~/workspace/saas/cinema
git fetch origin
git status -sb                           # clean, on phase1, not behind origin/phase1
python -m pytest -q -p no:cacheprovider  # green
curl -s --compressed https://elyoxe.com/cinema/ -o /dev/null -w "%{http_code}\n"   # 200 (old site still live)
python infra/wire_redirect.py | tee ~/cinema-redirect-before.txt   # DRY RUN — keep this file: it holds the "before" function associations for the rollback
```

## 1. Merge phase1 into main (laptop) — the Fold stays on `main`

**Recommended: merge, keep the Fold on main.** `run.sh` pushes the Fold's verdict commits to
`origin main` (`git pull --rebase origin main`, `git push origin HEAD:main`); a Fold checked out on
`phase1` would pull phase1 but push its verdicts to main, and the two branches would drift apart with
every run. With the merge there is one branch again and nothing on the Fold changes shape.

```bash
git checkout main
git pull --ff-only origin main           # picks up the Fold's own chore(verdicts) commits
git merge --no-ff phase1 -m "phase 1: cinema.elyoxe.com (merge phase1)"
                                         # only verdicts/ can differ on main: take main's side on a conflict there
python -m pytest -q -p no:cacheprovider  # green on the merge
git push origin main
git checkout phase1                      # keep working on phase1 if more comes
```
Then go straight to step 2 (see Timing above).

Check: `git log origin/main --oneline -1` is the merge commit.

Rollback: `git revert -m 1 <merge sha> && git push origin main` (the Fold's next pull returns to the old
code; the old deploy still targets the tools bucket, which is untouched until step 8).

> Alternative (not recommended): on the Fold `git fetch && git checkout phase1`. It works for the deploy,
> but the verdict push in run.sh still goes to main — you would have to change run.sh and remember to
> merge later anyway.

## 2. First phase-1 run on the Fold: indexable build, deploy, history seed (Fold, foreground)

```bash
ssh root@100.92.45.87
debian                                    # the chroot shell
cd /root/workspace && git pull --ff-only  # the workspace (crontab edits arrive later, step 6)
cd saas/cinema
git pull --ff-only                        # now at the merge commit
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3                  # the interpreter run.sh will use
"$PY" -c "import PIL, boto3; print(PIL.__version__)"             # Pillow is installed (done 2026-09-26)
free -m                                   # available >= 2000 MB (or: python3 /root/workspace/automation/phone/guard.py)
unset PREVIEW
bash run.sh                               # foreground, never nohup: tests -> refresh -> posters --upload -> deploy
```

What this run does:
- `PREVIEW` is not set, so the build is **indexable**: no `noindex` meta, `robots.txt` = `Allow` + `Sitemap:
  https://cinema.elyoxe.com/sitemap.xml`.
- No `data/film_history.json` exists on the Fold yet: refresh.py **seeds it silently** (every current film
  recorded, no new-film alert, nothing archived). The log line reads `new films (seeded, no alert): …`.
- `posters.py --upload` uploads the Fold's mirrored WebPs (the first time: all of them — same names,
  harmless) before `deploy.sh`.
- `deploy.sh` syncs to `elyoxe-cinema-574771023173` and invalidates `E1200YJEC3LL6I` (never the old ones).

Checks (laptop):
```bash
B=$(curl -s --compressed https://cinema.elyoxe.com/); [[ "$B" == *noindex* ]] && echo "STILL NOINDEX" || echo "indexable ok"
curl -s --compressed https://cinema.elyoxe.com/robots.txt       # Allow + Sitemap line, no "Disallow: /"
curl -s --compressed https://cinema.elyoxe.com/sitemap.xml -o /dev/null -w "%{http_code}\n"   # 200
ssh root@100.92.45.87 'ls -la /root/workspace/saas/cinema/data/film_history.json'              # exists
```

Rollback: `PREVIEW=1 ./deploy.sh` from the laptop puts the noindex build back (the site stays reachable);
revert the merge (step 1) so the Fold's next run does not undo it.

## 3. Turn on the 301s (laptop)

```bash
python infra/wire_redirect.py            # dry run: function create+publish, two behaviors -> elyoxe-cinema-moved
python infra/wire_redirect.py --apply
aws cloudfront wait distribution-deployed --id E2QY4WECG1P5WO     # ~5 min
```

Rollback: set the `/cinema*` and `/en/cinema*` behaviors' `FunctionAssociations` back to the "before" value
saved in `~/cinema-redirect-before.txt` (get-distribution-config → edit → update-distribution with the
ETag), then `aws cloudfront delete-function --name elyoxe-cinema-moved --if-match <etag>` (the ETag from
`describe-function --name elyoxe-cinema-moved`). The old objects are still in the tools bucket until step 8,
so the old site serves again immediately.

## 4. Verify the 301s (laptop)

Old URLs go to the same path on the new host, with the query string kept; nothing else on elyoxe.com moves.

```bash
chk() { printf '%s  ->  ' "$1"; curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" "$1"; }
chk "https://elyoxe.com/cinema"                      # 301 https://cinema.elyoxe.com/
chk "https://elyoxe.com/cinema/"                     # 301 https://cinema.elyoxe.com/
chk "https://elyoxe.com/cinema/dubai/"               # 301 https://cinema.elyoxe.com/dubai/
chk "https://elyoxe.com/cinema/film/heart-of-the-beast/?card=fazaa&x=1"   # 301 .../film/heart-of-the-beast/?card=fazaa&x=1
chk "https://elyoxe.com/cinema/sitemap.xml"          # 301 https://cinema.elyoxe.com/sitemap.xml
chk "https://elyoxe.com/en/cinema/"                  # 301 https://cinema.elyoxe.com/en/
chk "https://elyoxe.com/en/cinema/al-ain/?q=1"       # 301 https://cinema.elyoxe.com/en/al-ain/?q=1
# an encoded query must come out byte for byte as it went in (CloudFront Functions may hand values over
# decoded; if the Location shows "a&b c" or "a&b%20c", wrap the values in encodeURIComponent in
# infra/redirect.js and re-run step 3):
chk "https://elyoxe.com/cinema/dubai/?q=a%26b%20c"   # 301 https://cinema.elyoxe.com/dubai/?q=a%26b%20c
chk "https://elyoxe.com/cinema/cards/homat/"         # 301 https://cinema.elyoxe.com/cards/homat/ -> 200, a noindex
                                                     # «ما لقينا خصم مؤكد» note linking /cards/ (no confirmed discount)
chk "https://elyoxe.com/"                            # 200 (studio untouched)
chk "https://elyoxe.com/tools/"                      # 200
chk "https://elyoxe.com/quran/"                      # 200
# follow one all the way:
curl -sL -o /dev/null -w "%{http_code} %{url_effective}\n" "https://elyoxe.com/cinema/dubai/"   # 200 https://cinema.elyoxe.com/dubai/
```
Pick a real film id from `https://cinema.elyoxe.com/sitemap.xml` if heart-of-the-beast has left.

## 5. Robots and sitemaps

- **cinema.elyoxe.com** — nothing to do: step 2's indexable build writes `robots.txt` with
  `Sitemap: https://cinema.elyoxe.com/sitemap.xml`.
- **elyoxe.com** (studio) — its robots.txt still lists `Sitemap: https://elyoxe.com/cinema/sitemap.xml`
  (live now, a hand upload; after step 3 that URL is a 301). Point it at the new sitemap:
  - Source: `web/elyoxe/site/scripts/postbuild.mjs`. Commit **c401bdd** ("postbuild: robots.txt lists
    the tools, quran and cinema sitemaps") is **not pushed** — `web/elyoxe` main is ahead of origin by 7
    and behind by 1, with another session's uncommitted `dawa` work in the tree. Do not push it as is.
    Change the sibling list so cinema names its own host:
    ```js
    const siblingSitemaps = ["tools", "quran"].map((p) => `Sitemap: ${site}/${p}/sitemap.xml\n`).join("")
      + "Sitemap: https://cinema.elyoxe.com/sitemap.xml\n";
    ```
    commit that by path (`git commit -- site/scripts/postbuild.mjs`) after `git pull --rebase` in
    web/elyoxe, and let the studio's own deploy publish it (pushing web/elyoxe = deploying the studio —
    only when that repo's owner session is ready).
  - Now, without waiting for a studio deploy (the live file is a hand upload anyway):
    ```bash
    printf 'User-agent: *\nAllow: /\nSitemap: https://elyoxe.com/sitemap.xml\nSitemap: https://elyoxe.com/tools/sitemap.xml\nSitemap: https://elyoxe.com/quran/sitemap.xml\nSitemap: https://cinema.elyoxe.com/sitemap.xml\n' > /tmp/robots.txt
    aws s3 cp /tmp/robots.txt s3://elyoxe-574771023173/robots.txt --content-type "text/plain; charset=utf-8" --cache-control "public, max-age=300"
    aws cloudfront create-invalidation --distribution-id E2QY4WECG1P5WO --paths /robots.txt
    curl -s --compressed https://elyoxe.com/robots.txt
    ```
- Search Console: add the `cinema.elyoxe.com` property (DNS TXT in zone `Z092471334IO8THU6C3A9`) and
  submit its sitemap; in the elyoxe.com property the old /cinema URLs will drain as 301s.

Rollback: re-upload the previous robots.txt (the four-line version with `/cinema/sitemap.xml`).

## 6. Hourly schedule (workspace + Fold)

**Not on cutover day.** Keep the Fold on four runs a day until the hourly-safety fixes (resume-only raw
reuse, canonical-fid history, the 5-day archive clock, state-change alerts; commit "fix: hourly-safe
refresh…") have run in production for a full day: `data/raw/.run.json` absent between runs, every chain
line in `cinema.log` without `(resumed)` on a normal run, `data/alert_state.json` present, no repeated
`سينما ⚠` for the same condition. Then flip the `CINEMA_HOURLY_AT_CUTOVER` line:

In `automation/phone/crontab`, the line under the `CINEMA_HOURLY_AT_CUTOVER` marker becomes hourly
(the phase-1 daily price cache keeps seat-map calls to once per cinema × hall × date; run.sh's flock skips
an overlapping run):

```diff
-10 6,12,18,23 * * * /data/local/debian-boot.sh -c "/root/workspace/automation/phone/run-job.sh cinema" >> /data/local/tmp/elyoxe-cron.log 2>&1
+10 * * * * /data/local/debian-boot.sh -c "/root/workspace/automation/phone/run-job.sh cinema" >> /data/local/tmp/elyoxe-cron.log 2>&1
```
Also update the comment above it (drop the marker, say "hourly since <date>").

```bash
# laptop: commit by path in the workspace, wsync pushes it (or git push)
git -C ~/workspace commit -m "cron: cinema hourly (phase-1 cutover)" -- automation/phone/crontab && git -C ~/workspace push
# Fold:
ssh root@100.92.45.87
cd /root/workspace && git pull --ff-only && bash automation/phone/install-cron.sh   # prints crond's real pid
grep cinema /data/data/com.termux/files/usr/var/spool/cron/root                      # "10 * * * *"
```
Check at the next :10 + ~15 min: `tail -n 30 /data/data/com.termux/files/usr/var/log/elyoxe/cinema.log`
ends with `== cinema run done`, and `https://cinema.elyoxe.com/` shows the new "updated" age.

Rollback: restore the four-times line, commit, pull on the Fold, `install-cron.sh` again.

## 7. Watch one day

- 24 runs, no failure notifications (`سينما ✗`); `data/health.json` all ok; a new film (if any) gives one
  `سينما 🎬` notification, never a storm; a standing condition (a chain's prices degraded all day, a busy
  phone) notifies once when it starts and once when it clears (`data/alert_state.json`).
- `data/price_cache.json` grows once per day per cinema × hall × date, not per run.
- Lighthouse spot check on the indexable build (SEO ≥ 95 now that `is-crawlable` passes).

## 8. Delete the old objects from the tools bucket (only after step 4 verified; a day later is fine)

After the 301s the `/cinema*` and `/en/cinema*` behaviors answer at the edge before the origin, so the
objects under `cinema/` and `en/cinema/` in the tools bucket are dead weight. The trailing slash matters:
it must not match `cinemas…` or anything of /tools and /quran.

```bash
TB=$(aws cloudformation describe-stacks --region ap-south-1 --stack-name elyoxe-tools \
       --query "Stacks[0].Outputs[?OutputKey=='Bucket'].OutputValue" --output text)
aws s3 ls "s3://$TB/" --region ap-south-1                       # see the top level: tools/ quran/ cinema/ en/ ...
aws s3 rm "s3://$TB/cinema/"    --recursive --region ap-south-1 --dryrun | tail -3
aws s3 rm "s3://$TB/en/cinema/" --recursive --region ap-south-1 --dryrun | tail -3
# the dry runs list only cinema/... and en/cinema/... keys -> run both again without --dryrun
aws s3 ls "s3://$TB/tools/" --region ap-south-1 | head -3       # still there
curl -s -o /dev/null -w "%{http_code}\n" https://elyoxe.com/tools/   # 200
```
(The old /cinema* → tools-bucket wiring script was deleted from the repo in the merge, so nothing can
re-point those behaviors at the tools bucket and undo the 301s.)

Rollback: none needed for the redirect (the edge answers without the origin). To bring the old site back
entirely you would undo step 3 and redeploy the old main build (`git checkout <pre-merge sha> -- deploy.sh`
+ build) into the tools bucket — so do step 8 only once the new site has run cleanly for a day.

## 9. Close out

- `docs/ROADMAP.md` / the SDD ledger: phase 1 cut over on <date>.
- Memory: the Fold now runs cinema hourly from main; the old paths are 301s.
