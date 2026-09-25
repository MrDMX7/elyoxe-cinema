#!/usr/bin/env bash
# deploy.sh — build «سينما» from data/latest.json and publish under elyoxe.com/cinema + /en/cinema.
# Target: the EXISTING elyoxe-tools bucket (stack elyoxe-tools, ap-south-1). Every sync is limited to
# cinema/* and en/cinema/*, so --delete can never touch tools/, en/tools/ or quran/ (and tools'
# own deploy.sh is limited to those three, so it never touches ours). out/tools/ (a --preview copy
# of base.css) is never uploaded.
# Cache: html + sitemap 300 s · data/*.json 600 s · assets (?v=<hash> in every page) immutable.
# data/lastmod.json stays on the runner (gitignored) so sitemap lastmod only moves when a page changes.
#   PY=.venv/bin/python ./deploy.sh      (default PY: python3 if it runs, else python)
set -euo pipefail
export PYTHONWARNINGS=ignore
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION=ap-south-1; STACK=elyoxe-tools; DIST=E2QY4WECG1P5WO
cd "$HERE"
if [ -z "${PY:-}" ]; then
  if python3 -c "" >/dev/null 2>&1; then PY=python3; else PY=python; fi
fi
[ -s data/latest.json ] || { echo "deploy: data/latest.json missing — run refresh.py first (never deploy fixtures)" >&2; exit 2; }

"$PY" build.py --data data/latest.json
[ -s out/cinema/index.html ] && [ -s out/en/cinema/index.html ] && [ -s out/cinema/sitemap.xml ] \
  || { echo "deploy: build output incomplete" >&2; exit 3; }
# floor: never publish a collapse. Zero films, or under half the pages of the last deploy, stops here
# (the live site keeps the previous build). data/.last_pages is this runner's own count (gitignored).
pages=$(find out/cinema out/en/cinema -name index.html | wc -l)
films=$(find out/cinema/film -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
last=$(cat data/.last_pages 2>/dev/null || echo 0)
[ "$films" -gt 0 ] || { echo "deploy: zero film pages — refusing to publish" >&2; exit 5; }
[ $((pages * 2)) -ge "$last" ] || { echo "deploy: $pages pages vs $last last time (< 50%) — refusing to publish" >&2; exit 5; }

BUCKET=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='Bucket'].OutputValue" --output text)
[ -n "$BUCKET" ] && [ "$BUCKET" != "None" ] || { echo "deploy: no bucket from stack $STACK" >&2; exit 4; }
ONLY=(--exclude "*" --include "cinema/*" --include "en/cinema/*")

# 1) assets (immutable) — also the --delete pass for everything that is neither html/xml nor data
aws s3 sync out/ "s3://$BUCKET/" --region "$REGION" --delete "${ONLY[@]}" \
  --exclude "*.html" --exclude "*.xml" --exclude "cinema/data/*" \
  --cache-control "public, max-age=31536000, immutable" --only-show-errors
# 2) data slices, 10 min (with --delete: yesterday's <city>-<date>.json disappear)
aws s3 sync out/ "s3://$BUCKET/" --region "$REGION" --delete --exclude "*" --include "cinema/data/*" \
  --content-type "application/json; charset=utf-8" --cache-control "public, max-age=600" --only-show-errors
# 3) html + sitemap, 5 min (with --delete: pages of films that left are removed). Note: this pass also
#    uploads any non-HTML file outside assets/ and data/ (none today) with the 300 s cache — give a new
#    such file (an OG image, say) its own pass if it should be cached longer.
aws s3 sync out/ "s3://$BUCKET/" --region "$REGION" --delete "${ONLY[@]}" \
  --exclude "cinema/data/*" --exclude "cinema/assets/*" --exclude "en/cinema/assets/*" \
  --cache-control "public, max-age=300" --only-show-errors

INV=$(aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/cinema*" "/en/cinema*" \
  --query Invalidation.Id --output text)
echo "synced to s3://$BUCKET (cinema/, en/cinema/), invalidation $INV"

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
check "https://elyoxe.com/cinema/" "/cinema/assets/cinema.css"
check "https://elyoxe.com/en/cinema/" "/cinema/assets/cinema.css"
check "https://elyoxe.com/cinema/sitemap.xml" "<urlset"
echo "$pages" > data/.last_pages
echo "deployed: https://elyoxe.com/cinema/ ($pages pages, $films films)"
