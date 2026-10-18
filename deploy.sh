#!/usr/bin/env bash
# deploy.sh — build «سينما» from data/latest.json and publish it at https://cinema.elyoxe.com (ar at /,
# en at /en/). Target: its OWN stack elyoxe-cinema (infra/template.yaml) — bucket
# elyoxe-cinema-574771023173 and that stack's distribution. Nothing here touches the elyoxe.com
# distribution or any other bucket (tests/test_deploy_paths.py enforces it), so `--delete` can only
# ever remove files of this site.
# Source: out/ minus out/tools/ (a --preview copy of base.css, never uploaded). Until build.py emits
# pages at the out/ root (Task 3) it still writes out/cinema/ + out/en/cinema/; that layout is staged
# into the same root shape first, so this script works before and after the change.
# Cache: html/xml/txt/webmanifest/sw.js 300 s · data/*.json 600 s · everything else immutable 1 year
# (assets carry ?v=<hash> in every page).
# data/lastmod.json stays on the runner (gitignored) so sitemap lastmod only moves when a page changes.
#   PY=.venv/bin/python ./deploy.sh      (default PY: python3 if it runs, else python)
#   SRC=some/dir ./deploy.sh             (publish an already-built root-shaped dir; skips the build)
set -euo pipefail
# 2026-10-08 (owner: the fast upload for every project): uploads go through ~/workspace/tools/s3fast.py (boto3, many at a
# time, same arguments as `aws s3 sync|cp`); the CLI runs only if it fails
fast(){ shift 2; "$(command -v python3 || command -v python)" "$(cygpath -m "$HOME" 2>/dev/null || echo "$HOME")/workspace/tools/s3fast.py" "$@" || aws s3 "$@"; }
export PYTHONWARNINGS=ignore
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION=ap-south-1; STACK=elyoxe-cinema; SITE=https://cinema.elyoxe.com
BUCKET=elyoxe-cinema-574771023173
cd "$HERE"
if [ -z "${PY:-}" ]; then
  if python3 -c "" >/dev/null 2>&1; then PY=python3; else PY=python; fi
fi

if [ -z "${SRC:-}" ]; then
  [ -s data/latest.json ] || { echo "deploy: data/latest.json missing — run refresh.py first (never deploy fixtures)" >&2; exit 2; }
  "$PY" build.py --data data/latest.json
  if [ -s out/index.html ]; then
    SRC=out                                   # root layout (after Task 3)
  elif [ -s out/cinema/index.html ]; then     # legacy layout: stage it into the root shape
    SRC="$(mktemp -d)"; trap 'rm -rf "$SRC"' EXIT
    cp -r out/cinema/. "$SRC/"
    [ -d out/en/cinema ] && { mkdir -p "$SRC/en"; cp -r out/en/cinema/. "$SRC/en/"; }
  else
    echo "deploy: build produced neither out/index.html nor out/cinema/index.html" >&2; exit 3
  fi
fi
[ -s "$SRC/index.html" ] && [ -s "$SRC/en/index.html" ] && [ -s "$SRC/sitemap.xml" ] \
  || { echo "deploy: build output incomplete in $SRC" >&2; exit 3; }
[ -s "$SRC/404.html" ] || echo "deploy: warning — no 404.html, CloudFront's error page will be empty" >&2

# floor: never publish a collapse. Zero films, or under half the pages of the last deploy, stops here
# (the live site keeps the previous build). data/.last_pages is this runner's own count (gitignored).
pages=$(find "$SRC" -name index.html -not -path "$SRC/tools/*" | wc -l)
films=$(find "$SRC/film" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
last=$(cat data/.last_pages 2>/dev/null || echo 0)
[ "$films" -gt 0 ] || { echo "deploy: zero film pages — refusing to publish" >&2; exit 5; }
[ $((pages * 2)) -ge "$last" ] || { echo "deploy: $pages pages vs $last last time (< 50%) — refusing to publish" >&2; exit 5; }

out_of() {
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
[ "$(out_of Bucket)" = "$BUCKET" ] || { echo "deploy: stack $STACK does not own $BUCKET" >&2; exit 4; }
DIST=$(out_of DistributionId)
[[ "$DIST" =~ ^E[A-Z0-9]+$ ]] || { echo "deploy: no distribution id from stack $STACK" >&2; exit 4; }
DEST="s3://$BUCKET/"
NEVER=(--exclude "tools/*" --exclude "next/*")   # the --preview dir, and /next/ (the app redesign's preview, 2026-10-18,
                                              # uploaded by app/preview.sh): never uploaded here, never deleted
KEEP=(--exclude "posters/*" --exclude "state/*")   # posters/: `posters.py --upload`; state/: the OLD price-history
                                              # copy, publicly served — steps/history.py moves it to the private
                                              # media bucket and removes it itself, only once the move is safe.
                                              # Never built into out/, so every --delete pass must leave them
                                              # alone (placed last: last filter wins)
SHORT=(--include "*.html" --include "*.xml" --include "*.txt" --include "sw.js")

# 1) assets (immutable) — also the --delete pass for everything that is neither short-lived nor data
# (*.ics excluded: W2-P7's /cal/thursday.ics is a subscribed feed, never immutable, or it would never
# see a new Thursday — pass 5 below gives it its own short cache and content type)
fast aws s3 sync "$SRC/" "$DEST" --region "$REGION" --delete \
  --exclude "*.html" --exclude "*.xml" --exclude "*.txt" --exclude "sw.js" --exclude "*.webmanifest" \
  --exclude "data/*" --exclude "*.ics" "${NEVER[@]}" "${KEEP[@]}" \
  --cache-control "public, max-age=31536000, immutable" --only-show-errors
# 2) data slices, 10 min (with --delete: yesterday's <city>-<date>.json disappear)
fast aws s3 sync "$SRC/" "$DEST" --region "$REGION" --delete --exclude "*" --include "data/*" "${KEEP[@]}" \
  --content-type "application/json; charset=utf-8" --cache-control "public, max-age=600" --only-show-errors
# 3) html + sitemap + robots + service worker, 5 min (with --delete: pages of films that left are removed)
fast aws s3 sync "$SRC/" "$DEST" --region "$REGION" --delete --exclude "*" "${SHORT[@]}" \
  --exclude "data/*" "${NEVER[@]}" "${KEEP[@]}" --cache-control "public, max-age=300" --only-show-errors
# 4) the web manifest, 5 min, with its own content type (mimetypes does not know .webmanifest)
fast aws s3 sync "$SRC/" "$DEST" --region "$REGION" --delete --exclude "*" --include "*.webmanifest" "${NEVER[@]}" "${KEEP[@]}" \
  --content-type "application/manifest+json" --cache-control "public, max-age=300" --only-show-errors
# 5) /cal/thursday.ics, 5 min, its own content type (W2-P7 §2.6: a subscribed calendar must see a new
# Thursday quickly, and mimetypes does not know .ics either)
fast aws s3 sync "$SRC/" "$DEST" --region "$REGION" --delete --exclude "*" --include "*.ics" "${NEVER[@]}" "${KEEP[@]}" \
  --content-type "text/calendar; charset=utf-8" --cache-control "public, max-age=300" --only-show-errors

INV=$(aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" --query Invalidation.Id --output text)
echo "synced $SRC to $DEST, invalidation $INV on $DIST"

# live check: body in a variable, no pipes (CLAUDE.md traps). Retry while the invalidation lands.
check() {
  local url="$1" want="$2" code body i
  for i in 1 2 3 4 5 6; do
    body=$(curl -sS --compressed -m 20 -w $'\n%{http_code}' "$url" || true)
    code="${body##*$'\n'}"; body="${body%$'\n'*}"
    if [ "$code" = "200" ] && [[ "$body" == *"$want"* ]]; then echo "live ok  $code $url"; return 0; fi
    sleep 10
  done
  echo "live FAIL $code $url" >&2; return 1
}
check "$SITE/" "</html>"
check "$SITE/en/" "</html>"
check "$SITE/sitemap.xml" "<urlset"
echo "$pages" > data/.last_pages
echo "deployed: $SITE/ ($pages pages, $films films)"
