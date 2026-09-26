#!/usr/bin/env bash
# run.sh — one scheduled refresh of «سينما»: pull → refresh.py → deploy.sh → tell the owner if anything is off.
#
# Runner: the Fold (residential IP; the chains' booking APIs are read from there). cron calls it through the
# workspace's job wrapper, which adds the wake lock, the memory wait and a notification on success/failure:
#   10 * * * *  /data/local/debian-boot.sh -c "/root/workspace/automation/phone/run-job.sh cinema"
# Hourly at :10 since 2026-09-27 (owner's ruling, Task 6) — was four times a day. Prices still
# sample at most once per cinema x hall x date per day (data/price_cache.json), so the extra runs
# cost showtime/listing calls only, never re-hammer the seat-map endpoints.
# By hand, in the foreground:  bash run.sh [--force]   (arguments go to refresh.py)
#
# Exit: 0 = deployed (possibly with degraded chains — those notify here), non-zero = nothing deployed
#   (6 = the test suite failed on the pulled code; the live site is left as it was).
# Notifications: only when something is wrong (a chain failed, prices degraded, verdicts not pushed);
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
fail() {  # run-job.sh already notifies a non-zero exit; notify here only when run on its own
  echo "FAILED: $1"
  [ -z "${ELYOXE_JOB:-}" ] && note "سينما ✗" "$1" "elyoxe-cinema"
  exit "${2:-1}"
}

exec 8>"$HERE/data/.run.lock"
flock -n 8 || { echo "another run holds the lock — skipping"; exit 0; }

PY="$HERE/.venv/bin/python"; [ -x "$PY" ] || PY=python3
export PY PYTHONUNBUFFERED=1

echo "== cinema run start (py: $PY)"
if ! git pull --ff-only -q; then
  echo "WARN: git pull --ff-only failed — running the checked-out code"
fi
echo "   at $(git log --oneline -1)"

# test gate (ruling 2026-09-26): whatever was just pulled must pass the suite before it can publish.
# Red -> no refresh, no deploy: the live site stays on the last good build. The laptop pushes by hand
# now (the repo has a workflow, so wsync treats it as pull-only), and CI runs the same suite there.
if ! "$PY" -m pytest -q -x -p no:cacheprovider; then
  fail "الاختبارات فشلت على $(git log --oneline -1 | cut -c1-60) — ما نُشر شي، الموقع على النسخة السابقة" 6
fi

"$PY" refresh.py "$@"   # e.g. bash run.sh --force (ignore the 3-hour raw reuse and fetch every chain now)
rc=$?
[ "$rc" -eq 0 ] || fail "refresh.py خرج بـ$rc — كل السلاسل فشلت، ما نُشر شي" "$rc"

./deploy.sh || fail "deploy.sh فشل بعد تحديث ناجح — الموقع على النسخة السابقة" 3

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
[ "$vrc" -eq 0 ] || note "سينما ⚠" "نُشر الموقع، بس ما قدرت أرفع ملفات الأحكام (رمز $vrc) — بحاول الجولة الياية" "elyoxe-cinema-git"

# health.json: {chain: {ok, at, error, shows, prices_degraded}} — anything off is worth one notification
bad=$("$PY" - <<'EOF'
import json
CHAINS = ("vox", "star", "cineroyal", "novo", "reel", "roxy", "cinemacity")
h = json.load(open("data/health.json", encoding="utf-8"))
out, low = [], []
for c in CHAINS:
    v = h.get(c) or {}
    if not v.get("ok"):
        out.append(f"{c}: فشل ({(v.get('error') or 'ما انقرأ')[:60]})")
    elif v.get("prices_degraded"):
        out.append(f"{c}: الأسعار ناقصة")
for k, v in sorted(h.items()):   # enrich / verdicts: a lower-priority note (the site still deployed)
    if k not in CHAINS and isinstance(v, dict) and v.get("ok") is False:
        low.append(f"{k}: {(v.get('error') or 'فشل')[:60]}")
print(" · ".join(out + ([f"(ثانوي) {' · '.join(low)}"] if low else [])))
EOF
)
if [ -n "$bad" ]; then
  echo "DEGRADED: $bad"
  note "سينما ⚠" "نُشر، لكن: $bad" "elyoxe-cinema-health"
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
