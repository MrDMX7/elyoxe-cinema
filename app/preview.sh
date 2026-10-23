#!/usr/bin/env bash
# preview.sh — publish the app redesign at https://cinema.elyoxe.com/next/ (noindex, beside the live site; deploy.sh
# never touches next/*). Builds from a data file (default: the laptop runner's latest), uploads with --delete inside
# next/ only, and invalidates /next/*. Safe to rerun.
set -euo pipefail
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERE="$(cygpath -m "$HERE" 2>/dev/null || echo "$HERE")"   # Windows Python needs C:/… (MSYS_NO_PATHCONV is on for /next/)
PY="${PY:-python}"
DATA="${DATA:-C:/Users/requi/cinema-runner/data/latest.json}"
OUT="$(mktemp -d)"; OUTW="$(cygpath -m "$OUT" 2>/dev/null || echo "$OUT")"
trap 'rm -rf "$OUT"' EXIT
"$PY" "$HERE/build_app.py" --data "$DATA" --out "$OUTW/next" --base /next/
"$PY" "$HERE/build_app.py" --data "$DATA" --out "$OUTW/next/en" --base /next/en/ --lang en
BUCKET=elyoxe-cinema-574771023173
aws s3 sync "$OUTW/next/assets/" "s3://$BUCKET/next/assets/" --region ap-south-1 --cache-control "public, max-age=31536000, immutable" --only-show-errors
aws s3 sync "$OUTW/next/" "s3://$BUCKET/next/" --region ap-south-1 --delete --exclude "assets/*" \
  --cache-control "public, max-age=120" --content-type "text/html; charset=utf-8" --only-show-errors
aws s3 sync "$OUTW/next/assets/" "s3://$BUCKET/next/assets/" --region ap-south-1 --delete --only-show-errors
DIST=$(aws cloudformation describe-stacks --region ap-south-1 --stack-name elyoxe-cinema --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" --output text)
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/next/*" --query "Invalidation.Status" --output text
echo "preview: https://cinema.elyoxe.com/next/"
