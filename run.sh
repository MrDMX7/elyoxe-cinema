#!/usr/bin/env bash
# run.sh — one scheduled refresh of «سينما»: pull → refresh.py → deploy.sh → tell the owner if anything is off.
#
# Runner: the Fold (residential IP; the chains' booking APIs are read from there). cron calls it through the
# workspace's job wrapper, which adds the wake lock, the memory wait and a notification on success/failure:
#   10 6,12,18,23 * * *  /data/local/debian-boot.sh -c "/root/workspace/automation/phone/run-job.sh cinema"
# By hand, in the foreground:  bash run.sh
#
# Exit: 0 = deployed (possibly with degraded chains — those notify here), non-zero = nothing deployed.
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

"$PY" refresh.py
rc=$?
[ "$rc" -eq 0 ] || fail "refresh.py خرج بـ$rc — كل السلاسل فشلت، ما نُشر شي" "$rc"

./deploy.sh || fail "deploy.sh فشل بعد تحديث ناجح — الموقع على النسخة السابقة" 3

# health.json: {chain: {ok, at, error, shows, prices_degraded}} — anything off is worth one notification
bad=$("$PY" - <<'EOF'
import json
h = json.load(open("data/health.json", encoding="utf-8"))
out = []
for c, v in sorted(h.items()):
    if not v.get("ok"):
        out.append(f"{c}: فشل ({(v.get('error') or '')[:60]})")
    elif v.get("prices_degraded"):
        out.append(f"{c}: الأسعار ناقصة")
print(" · ".join(out))
EOF
)
if [ -n "$bad" ]; then
  echo "DEGRADED: $bad"
  note "سينما ⚠" "نُشر، لكن: $bad" "elyoxe-cinema-health"
fi
echo "== cinema run done"
