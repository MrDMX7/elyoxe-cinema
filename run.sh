#!/usr/bin/env bash
# run.sh — one scheduled refresh of «سينما»: pull → refresh.py → deploy.sh → tell the owner if anything is off.
#
# Runner: the Fold (residential IP; the chains' booking APIs are read from there). cron calls it through the
# workspace's job wrapper, which adds the wake lock, the memory wait and a notification on success/failure:
#   10 * * * *  /data/local/debian-boot.sh -c "/root/workspace/automation/phone/run-job.sh cinema"
# Hourly at :10 is the owner's ruling (Task 6), on since 2026-09-27. Prices sample at most once per cinema x hall x date per day
# (data/price_cache.json), so the extra runs cost showtime/listing calls only.
# By hand, in the foreground:  bash run.sh [--force]   (arguments go to refresh.py)
#
# Exit: 0 = deployed (possibly with degraded chains). $DEGRADED_RC (78) = DEGRADED — a failure
#   (tests/pull/refresh/deploy/memory-wait) that was already alerted and is STILL going on: nothing
#   new deployed, logged as DEGRADED, and the owner is told at once (item 291, 2026-09-30 -- a
#   freeze confirmed two runs in a row is no longer news that waits) then reminded at most once
#   every 6 hours while it lasts (ruling, docs/RULINGS.md:37, raised from once/calendar-day: that
#   let a freeze starting just after midnight go ~24h between reminders) -- run-job.sh's
#   state/<job>.state must record "degraded" (not
#   "ok") for this exit code, never silently exit 0 for an ongoing failure. NOT plain 2: run-job.sh
#   already used 2 for its own "unknown job name" fallback before this convention existed, so this
#   script and run-job.sh's finish() must agree on the SAME dedicated code (78) or a mistyped job
#   name would get silently read as "degraded" instead of "failed" (review finding, Task A1 round
#   1). Any other non-zero = a FRESH failure just alerted, nothing deployed (6 = the test suite
#   failed on the pulled code, 7 = git pull failed, 3 = deploy.sh failed; the live site is left as
#   it was).
# Notifications (final review I3): on a CHANGE of state only -- alerts.py keeps data/alert_state.json and
# says whether a condition just started (notify), just cleared (notify once) or is still the same (quiet).
# run-job.sh keeps this job quiet on success (QUIET_OK).
set -uo pipefail
# DEGRADED_RC must match run-job.sh's own constant of the same name -- see that file's comment
# for why 78 and not 2 (docs/RULINGS.md:37).
DEGRADED_RC=78
# The whole body is one brace group ending in exit: bash parses it completely before running, so a
# `git pull` that rewrites this file mid-run cannot make bash read the new bytes at the old offset.
{
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
# Test seams (final review C2): CINEMA_LOG_DIR / CINEMA_ENV_SH point the log and the notify mechanism
# elsewhere. tests/test_degraded_state.py runs this script for real and MUST set both (a temp dir and a
# no-op env file) -- otherwise a test run on the Fold would append to the production cinema.log and
# send real notifications to the owner. Guard: under pytest (PYTEST_CURRENT_TEST is inherited by every
# subprocess a test starts) without both overrides, refuse before touching any log or sourcing anything.
if [ -n "${PYTEST_CURRENT_TEST:-}" ] && { [ -z "${CINEMA_LOG_DIR:-}" ] || [ -z "${CINEMA_ENV_SH:-}" ]; }; then
  echo "run.sh: refusing to run under pytest without CINEMA_LOG_DIR and CINEMA_ENV_SH (would write the real log / notify the owner)" >&2
  exit 64
fi
LOG_DIR="${CINEMA_LOG_DIR:-/data/data/com.termux/files/usr/var/log/elyoxe}"
[ -d "$LOG_DIR" ] || LOG_DIR="$HERE/data"
LOG="$LOG_DIR/cinema.log"
mkdir -p "$(dirname "$LOG")" data
exec > >(while IFS= read -r l; do printf '[%s] %s\n' "$(date '+%F %T')" "$l"; done | tee -a "$LOG") 2>&1

# notify <title> <body> <id> — the workspace mechanism (termux-env.sh → notify.py); never fails the run.
ENV_SH="${CINEMA_ENV_SH:-/root/workspace/automation/phone/termux-env.sh}"
if [ -f "$ENV_SH" ]; then . "$ENV_SH"; fi
# Without `notify` (the laptop: no termux-env.sh) a real run mails the owner instead (tools/notify_mail.py, SES) —
# two freezes went unseen because the laptop could only print «notify (unavailable)» (2026-10-17). The test
# sandbox always sets CINEMA_ENV_SH, so under pytest this branch is never taken and nothing is ever mailed.
note() {
  if declare -F notify >/dev/null; then notify "$@" >/dev/null 2>&1 || echo "notify failed: $1"
  elif [ -z "${CINEMA_ENV_SH:-}" ] && [ -f "$HERE/tools/notify_mail.py" ]; then
    if "${PY:-python3}" "$HERE/tools/notify_mail.py" "$1" "$2" 2>>"$HERE/data/notify_mail.err"; then echo "notify (mail): $1 — $2"
    else echo "notify (unavailable, mail failed): $1 — $2"; fi
  else echo "notify (unavailable): $1 — $2"; fi
}
# alert <alerts.py args> — prints the notification body when a condition starts or clears, else nothing
alert() { "${PY:-python3}" alerts.py "$@" 2>/dev/null || true; }
# since_of <key> — the ISO "since" time alerts.py recorded for a still-bad condition, or "".
# alerts.py's own CLI has no query for this (it only prints a message on start/clear), so this reads
# its state file directly -- read-only, never writes it.
since_of() {
  "${PY:-python3}" - "$1" <<'PYEOF' 2>/dev/null
import json, sys
try:
    d = json.load(open("data/alert_state.json", encoding="utf-8"))
    print(d.get(sys.argv[1], {}).get("since", ""))
except Exception:
    print("")
PYEOF
}
# write_marker_atomic <path> <content> — never leaves a half-written marker behind (tmp + mv,
# same convention as statefile.py's write_json_atomic; these markers are polled across runs, so a
# killed run must not leave one truncated).
write_marker_atomic() { printf '%s\n' "$2" > "$1.tmp.$$" && mv -f "$1.tmp.$$" "$1"; }
# remind_once <key> <message> — item 291 (2026-09-30): a freeze is confirmed the moment a condition
# is STILL bad on the run right after the fresh alert (fail()'s DEGRADED branch below never calls
# this on the first, fresh occurrence — only from the second run in a row onward), so the first call
# here always fires "at once" (no marker yet). After that, at most one notification per 6 hours
# while the condition stays bad (data/.reminded-<key> holds the epoch seconds of the last one) — not
# once per calendar day, which used to let a freeze that started just after midnight run up to ~24h
# between reminders (a real 20-hour freeze went unnoticed this way).
remind_once() {
  local key="$1" msg="$2" now_ts marker last_ts elapsed=999999
  now_ts=$(TZ=Asia/Dubai date +%s)
  marker="$HERE/data/.reminded-$key"
  last_ts=$(cat "$marker" 2>/dev/null)
  case "$last_ts" in ''|*[!0-9]*) : ;; *) elapsed=$(( now_ts - last_ts ));; esac
  [ "$elapsed" -lt 21600 ] && return 0   # < 6h since the last reminder (21600s): stay quiet
  write_marker_atomic "$marker" "$now_ts"
  note "سينما ⚠" "$msg" "elyoxe-cinema-$key"
}
# ok_now <key> <message on clear> — a condition is absent this run; notify once if it had been
# alerted, and drop its reminder marker so a future recurrence of the same key starts a fresh cycle
ok_now() { local m; m=$(alert cond "$1" --ok --clear "$2"); rm -f "$HERE/data/.reminded-$1"; [ -z "$m" ] || note "سينما ✓" "$m" "elyoxe-cinema-$1"; }
fail() {  # fail <message> <rc> <key> -- <rc> is the FRESH-failure exit code (6 tests, 7 pull, 3
  # deploy, refresh.py's own rc). A failure that was already alerted and is STILL going on exits
  # $DEGRADED_RC (78, NOT 2 -- see the top-of-file comment and docs/RULINGS.md:37) instead of
  # repeating <rc> or going quiet with 0 -- so run-job.sh's state/<job>.state records "degraded"
  # with a since-time, not "ok". Item 291: this DEGRADED branch is exactly the condition's SECOND
  # (or later) run in a row -- remind_once fires at once the first time it is called for a key (no
  # marker yet), then throttles to at most once per 6h while the freeze lasts.
  echo "FAILED: $1"
  if [ -z "$(alert cond "$3" --bad "$1" --clear "")" ]; then
    local since; since=$(since_of "$3")
    echo "DEGRADED: $3 since ${since:-?} — freeze alert at once, then at most every 6h"
    remind_once "$3" "سينما: بعده $1 من ${since:-?}"
    exit "$DEGRADED_RC"
  fi
  # run-job.sh notifies a non-zero exit; notify here only when run on its own. No marker is stamped
  # here (item 291): the FIRST failure is only a possible blip, not yet a confirmed freeze -- the
  # reminder marker belongs solely to remind_once, so the very next run (if still broken) alerts at
  # once instead of waiting up to a day.
  [ -z "${ELYOXE_JOB:-}" ] && note "سينما ✗" "$1" "elyoxe-cinema"
  exit "${2:-1}"
}

# one instance at a time. flock (util-linux) is on the Fold, CI and every Linux dev box, but
# Windows Git Bash ships none — command -v finds nothing there and `flock -n 8` would just fail
# with "command not found" (127, non-zero), which the old `flock -n 8 || skip` read as "someone
# else holds the lock" on EVERY run, forever. Where flock exists, behaviour is unchanged byte for
# byte (including test_degraded_state.py's fake `flock` on PATH). Where it doesn't, fall back to
# an mkdir lock (atomic on any filesystem, Windows included), reclaimed if stale — a run never
# takes anywhere near 3h, so a killed process must not wedge every later run forever.
if command -v flock >/dev/null 2>&1; then
  exec 8>"$HERE/data/.run.lock"
  flock -n 8 || { echo "another run holds the lock — skipping"; exit 0; }
else
  LOCKDIR="$HERE/data/.run.lock.d"
  now_lock=$(date +%s)
  if [ -d "$LOCKDIR" ]; then
    lock_ts=$(cat "$LOCKDIR/started" 2>/dev/null); case "$lock_ts" in ''|*[!0-9]*) lock_ts=0;; esac
    if [ $(( now_lock - lock_ts )) -gt 10800 ]; then
      echo "run.sh: stale lock (started ${lock_ts}, >3h old) — reclaiming"
      rm -rf "$LOCKDIR"
    fi
  fi
  if ! mkdir "$LOCKDIR" 2>/dev/null; then
    echo "another run holds the lock — skipping"; exit 0
  fi
  echo "$now_lock" > "$LOCKDIR/started"
  trap 'rm -rf "$LOCKDIR"' EXIT
fi

# .venv/bin/python (Linux: the Fold, CI) vs .venv/Scripts/python.exe (Windows `python -m venv`) —
# try both before falling back to whatever python3 is on PATH.
PY="$HERE/.venv/bin/python"
[ -x "$PY" ] || PY="$HERE/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY=python3
export PY PYTHONUNBUFFERED=1

echo "== cinema run start (py: $PY)"
# run-job.sh only starts this after its memory wait passed: a memory-wait failure it alerted has cleared
ok_now mem "الذاكرة رجعت — سينما اشتغلت من جديد"
# a pull that fails must not deploy the old code as if it were the release (final review M3): stop, tell
# the owner once (alerts.py), and let every later run stop the same way until the checkout is fixed --
# e.g. files dirty with line endings only: `git diff --ignore-all-space --quiet && git reset --hard origin/main`.
# --autostash: verdicts/intel left dirty by a run that died before commit_verdicts (the 10-09 manual recovery
# did exactly that) froze every later run for 8 days with «cannot pull with rebase: You have unstaged changes».
if ! git pull --ff-only --autostash -q; then
  fail "git pull فشل على $(git log --oneline -1 | cut -c1-40) — ما نُشر شي، الموقع على النسخة السابقة (git status في saas/cinema)" 7 pull
fi
ok_now pull "git pull رجع يشتغل"
echo "   at $(git log --oneline -1)"

# dependencies self-heal (final review C1): a pull that adds a package to requirements.txt must not turn
# the test gate red on a missing import. data/.req-hash holds the sha256 of the requirements.txt that was
# last installed successfully; a different (or missing) hash -> pip install -r before the tests. A failed
# install is a condition like any other (fresh alert, then degraded). CINEMA_PIP_INSTALL is a test seam.
req_hash() { "$PY" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' requirements.txt 2>/dev/null; }
if [ -f requirements.txt ]; then
  want=$(req_hash); have=$(cat data/.req-hash 2>/dev/null)
  if [ -n "$want" ] && [ "$want" != "$have" ]; then
    echo "   requirements.txt changed (${have:0:12} -> ${want:0:12}): installing"
    if ${CINEMA_PIP_INSTALL:-"$PY" -m pip install -q -r requirements.txt}; then
      write_marker_atomic data/.req-hash "$want"
    else
      fail "pip install -r requirements.txt فشل — ما نُشر شي، الموقع على النسخة السابقة" 5 deps
    fi
  fi
  ok_now deps "تنصيب المكتبات رجع يشتغل"
fi

# test gate (ruling 2026-09-26): whatever was just pulled must pass the suite before it can publish.
# Red -> no refresh, no deploy: the live site stays on the last good build. The laptop pushes by hand
# now (the repo has a workflow, so wsync treats it as pull-only), and CI runs the same suite there.
if ! "$PY" -m pytest -q -x -p no:cacheprovider; then
  fail "الاختبارات فشلت على $(git log --oneline -1 | cut -c1-60) — ما نُشر شي، الموقع على النسخة السابقة" 6 tests
fi
ok_now tests "الاختبارات رجعت خضراء"

"$PY" refresh.py "$@"   # e.g. bash run.sh --force (never resume a killed run's raw files)
rc=$?
[ "$rc" -eq 0 ] || fail "refresh.py خرج بـ$rc — كل السلاسل فشلت، ما نُشر شي" "$rc" refresh
ok_now refresh "السلاسل رجعت تنقرأ"

# posters mirrored this run (new films, replaced art) go to the bucket before the pages that name them:
# deploy.sh never uploads posters/ (nor deletes them). A failure costs only the new posters (each page
# falls back to the film's typographic tile), never the deploy.
if ! "$PY" posters.py --upload; then
  echo "WARN: posters.py --upload failed — new posters show as typographic tiles until the next run"
  m=$(alert cond posters --bad "رفع البوسترات الجديدة فشل — بحاول كل جولة" --clear "")
  [ -z "$m" ] || note "سينما ⚠" "$m" "elyoxe-cinema-posters"
else
  ok_now posters "رفع البوسترات رجع يشتغل"
fi

./deploy.sh || fail "deploy.sh فشل بعد تحديث ناجح — الموقع على النسخة السابقة" 3 deploy
ok_now deploy "النشر رجع يشتغل"

# verdicts/*.json and intel/*.json (UNIT r3-film: filmintel.py, the same cached-once-per-film shape) written
# this run (new films, templates replaced, merged-away files folded) go back to origin, so the laptop and the
# next run see the same set. Only these two dirs — never anything else in the tree. A conflict aborts just
# this commit; the deploy already happened.
commit_verdicts() {
  git add -A -- verdicts/ intel/ || return 1
  if git diff --cached --quiet -- verdicts/ intel/; then echo "verdicts/intel: nothing new"; return 0; fi
  local n; n=$(git diff --cached --name-only -- verdicts/ intel/ | wc -l)
  git commit -q -m "chore(verdicts,intel): auto $(date '+%F %H:%M')" -- verdicts/ intel/ || return 1
  if ! git pull --rebase --autostash -q origin main; then
    git rebase --abort >/dev/null 2>&1
    git reset -q --soft HEAD~1 && git reset -q -- verdicts/ intel/
    echo "verdicts/intel: pull --rebase conflicted — commit undone, files kept for the next run"
    return 2
  fi
  git push -q origin HEAD:main || { echo "verdicts/intel: push failed — the local commit stays ahead of origin; the next run's pull --ff-only still works and its push carries both"; return 3; }
  echo "verdicts/intel: committed and pushed $n file(s)"
}
vrc=0; commit_verdicts || vrc=$?
if [ "$vrc" -eq 0 ]; then
  ok_now git "رفع ملفات الأحكام رجع يشتغل"
else
  m=$(alert cond git --bad "نُشر الموقع، بس ما قدرت أرفع ملفات الأحكام (رمز $vrc) — بحاول كل جولة" --clear "")
  [ -z "$m" ] || note "سينما ⚠" "$m" "elyoxe-cinema-git"
fi

# discounts_watch.py (roadmap 195, 2026-10-17): once a week, read every page discounts.yaml cites and tell the
# owner which ones changed or stopped answering (the yaml's own `checked` dates are his — the watcher never
# touches them). Weekly, not every run: 20 pages behind Akamai and bank sites are not a 3-hourly habit. A
# failure here is only a log line — the site is already deployed.
WATCH_STATE="$HERE/data/discount_sources.json"
if [ ! -f "$WATCH_STATE" ] || [ -n "$(find "$WATCH_STATE" -mtime +6 2>/dev/null)" ]; then
  if m=$("$PY" discounts_watch.py 2>>"$HERE/data/discounts_watch.err"); then
    [ -z "$m" ] || note "سينما: الخصومات" "$m" "elyoxe-cinema-discounts"
  else
    echo "WARN: discounts_watch.py failed — see data/discounts_watch.err"
  fi
fi

# health.json: {chain: {ok, at, error, shows, prices_degraded, reused?}} -- alerts.py compares it with
# data/alert_state.json and prints only what started or cleared this run (a chain served from a resumed
# raw file changes nothing); a standing condition stays quiet after its first notification.
bad=$(alert health data/health.json)
if [ -n "$bad" ]; then
  echo "HEALTH CHANGE: $bad"
  note "سينما ⚠" "نُشر، والتغيّر: $bad" "elyoxe-cinema-health"
fi

# data/new_films.json: [{fid,title,title_ar,cinemas}, ...] fids refresh.py saw for the first time
# ever this run — empty on the seeding run (no film_history.json before it) by refresh.py's own
# rule, so this never fires on that one. One notification, up to 5 films. A corrupt file (should
# not happen — refresh.py writes it atomically — but a truncated write from a killed run is not
# impossible) is logged and skipped, never a reason to fail this already-deployed run.
new_line=$("$PY" - <<'EOF'
import json
films = []
try:
    with open("data/new_films.json", encoding="utf-8") as f:
        films = json.load(f)
except FileNotFoundError:
    pass
except (OSError, json.JSONDecodeError) as e:
    print(f"new_films.json unreadable, skipping the new-film alert: {e}", file=__import__("sys").stderr)
parts = [f"{f['title']} — {f['cinemas']} سينما" for f in films[:5]]
extra = len(films) - len(parts)
if extra > 0:
    parts.append(f"و{extra} غيره")
print(" · ".join(parts))
EOF
)
if [ -n "$new_line" ]; then
  echo "NEW FILMS: $new_line"
  note "سينما 🎬" "نزل: $new_line" "elyoxe-cinema-new"
fi
echo "== cinema run done"
exit 0
}
