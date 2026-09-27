#!/usr/bin/env bash
# run.sh — one scheduled refresh of «سينما»: pull → refresh.py → deploy.sh → tell the owner if anything is off.
#
# Runner: the Fold (residential IP; the chains' booking APIs are read from there). cron calls it through the
# workspace's job wrapper, which adds the wake lock, the memory wait and a notification on success/failure:
#   10 * * * *  /data/local/debian-boot.sh -c "/root/workspace/automation/phone/run-job.sh cinema"
# Hourly at :10 is the owner's ruling (Task 6), switched on only after the cutover (docs/CUTOVER.md
# step 6); until then four times a day. Prices sample at most once per cinema x hall x date per day
# (data/price_cache.json), so the extra runs cost showtime/listing calls only.
# By hand, in the foreground:  bash run.sh [--force]   (arguments go to refresh.py)
#
# Exit: 0 = deployed (possibly with degraded chains). 2 = DEGRADED — a failure (tests/pull/refresh/
#   deploy/memory-wait) that was already alerted and is STILL going on: nothing new deployed, logged
#   as DEGRADED, quiet except at most one reminder per Asia/Dubai calendar day (ruling, docs/CUTOVER.md
#   §6) -- run-job.sh's state/<job>.state must record "degraded" (not "ok") for this exit code, never
#   silently exit 0 for an ongoing failure. Any other non-zero = a FRESH failure just alerted, nothing
#   deployed (6 = the test suite failed on the pulled code, 7 = git pull failed, 3 = deploy.sh failed;
#   the live site is left as it was).
# Notifications (final review I3): on a CHANGE of state only -- alerts.py keeps data/alert_state.json and
# says whether a condition just started (notify), just cleared (notify once) or is still the same (quiet).
# run-job.sh keeps this job quiet on success (QUIET_OK).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
LOG_DIR=/data/data/com.termux/files/usr/var/log/elyoxe
[ -d "$LOG_DIR" ] || LOG_DIR="$HERE/data"
LOG="$LOG_DIR/cinema.log"
mkdir -p "$(dirname "$LOG")" data
exec > >(while IFS= read -r l; do printf '[%s] %s\n' "$(date '+%F %T')" "$l"; done | tee -a "$LOG") 2>&1

# notify <title> <body> <id> — the workspace mechanism (termux-env.sh → notify.py); never fails the run.
ENV_SH=/root/workspace/automation/phone/termux-env.sh
if [ -f "$ENV_SH" ]; then . "$ENV_SH"; fi
note() { if declare -F notify >/dev/null; then notify "$@" >/dev/null 2>&1 || echo "notify failed: $1"; else echo "notify (unavailable): $1 — $2"; fi; }
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
# remind_once <key> <message> — at most one notification per Asia/Dubai calendar day while a
# condition stays bad (ruling, docs/CUTOVER.md §6). data/.reminded-<key> holds the last date
# reminded; fail() also stamps it the day the FRESH alert fires, so the reminder cycle only starts
# the following day (the owner already knows about today's failure from that first alert).
remind_once() {
  local key="$1" msg="$2" today marker
  today=$(TZ=Asia/Dubai date +%F)
  marker="$HERE/data/.reminded-$key"
  [ "$(cat "$marker" 2>/dev/null)" = "$today" ] && return 0
  echo "$today" > "$marker"
  note "سينما ⚠" "$msg" "elyoxe-cinema-$key"
}
# ok_now <key> <message on clear> — a condition is absent this run; notify once if it had been
# alerted, and drop its reminder marker so a future recurrence of the same key starts a fresh cycle
ok_now() { local m; m=$(alert cond "$1" --ok --clear "$2"); rm -f "$HERE/data/.reminded-$1"; [ -z "$m" ] || note "سينما ✓" "$m" "elyoxe-cinema-$1"; }
fail() {  # fail <message> <rc> <key> -- <rc> is the FRESH-failure exit code (6 tests, 7 pull, 3
  # deploy, refresh.py's own rc). A failure that was already alerted and is STILL going on exits 2
  # (degraded) instead of repeating <rc> or going quiet with 0 -- so run-job.sh's state/<job>.state
  # records "degraded" with a since-time, not "ok" -- with at most one reminder per calendar day
  # while it lasts (remind_once above).
  echo "FAILED: $1"
  if [ -z "$(alert cond "$3" --bad "$1" --clear "")" ]; then
    local since; since=$(since_of "$3")
    echo "DEGRADED: $3 since ${since:-?} — quiet unless today's reminder is still due"
    remind_once "$3" "سينما: ما زال $1 من ${since:-?}"
    exit 2
  fi
  # run-job.sh notifies a non-zero exit; notify here only when run on its own
  [ -z "${ELYOXE_JOB:-}" ] && note "سينما ✗" "$1" "elyoxe-cinema"
  echo "$(TZ=Asia/Dubai date +%F)" > "$HERE/data/.reminded-$3"   # today already covered by this fresh alert
  exit "${2:-1}"
}

exec 8>"$HERE/data/.run.lock"
flock -n 8 || { echo "another run holds the lock — skipping"; exit 0; }

PY="$HERE/.venv/bin/python"; [ -x "$PY" ] || PY=python3
export PY PYTHONUNBUFFERED=1

echo "== cinema run start (py: $PY)"
# run-job.sh only starts this after its memory wait passed: a memory-wait failure it alerted has cleared
ok_now mem "الذاكرة رجعت — سينما اشتغلت من جديد"
# a pull that fails must not deploy the old code as if it were the release (final review M3): stop, tell
# the owner once (alerts.py), and let every later run stop the same way until the checkout is fixed --
# e.g. files dirty with line endings only: `git diff --ignore-all-space --quiet && git reset --hard origin/main`
if ! git pull --ff-only -q; then
  fail "git pull فشل على $(git log --oneline -1 | cut -c1-40) — ما نُشر شي، الموقع على النسخة السابقة (git status في saas/cinema)" 7 pull
fi
ok_now pull "git pull رجع يشتغل"
echo "   at $(git log --oneline -1)"

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

# verdicts/*.json written this run (new films, templates replaced, merged-away files folded) go back
# to origin, so the laptop and the next run see the same set. Only verdicts/ — never anything else
# in the tree. A conflict aborts just this commit; the deploy already happened.
commit_verdicts() {
  git add -A -- verdicts/ || return 1
  if git diff --cached --quiet -- verdicts/; then echo "verdicts: nothing new"; return 0; fi
  local n; n=$(git diff --cached --name-only -- verdicts/ | wc -l)
  git commit -q -m "chore(verdicts): auto $(date '+%F %H:%M')" -- verdicts/ || return 1
  if ! git pull --rebase --autostash -q origin main; then
    git rebase --abort >/dev/null 2>&1
    git reset -q --soft HEAD~1 && git reset -q -- verdicts/
    echo "verdicts: pull --rebase conflicted — commit undone, files kept for the next run"
    return 2
  fi
  git push -q origin HEAD:main || { echo "verdicts: push failed — the local commit stays ahead of origin; the next run's pull --ff-only still works and its push carries both"; return 3; }
  echo "verdicts: committed and pushed $n file(s)"
}
vrc=0; commit_verdicts || vrc=$?
if [ "$vrc" -eq 0 ]; then
  ok_now git "رفع ملفات الأحكام رجع يشتغل"
else
  m=$(alert cond git --bad "نُشر الموقع، بس ما قدرت أرفع ملفات الأحكام (رمز $vrc) — بحاول كل جولة" --clear "")
  [ -z "$m" ] || note "سينما ⚠" "$m" "elyoxe-cinema-git"
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
