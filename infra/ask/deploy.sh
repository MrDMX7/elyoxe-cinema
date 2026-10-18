#!/usr/bin/env bash
# deploy.sh — «اسأل الفيلم» (stack elyoxe-cinema-ask, ap-south-1). Builds infra/ask/build/ (handler + system.txt +
# the anthropic SDK as Linux wheels — pydantic-core is compiled, so never the laptop's own Windows wheels), then
# `sam deploy` (no `sam build`: CodeUri points at the ready folder). Prints the endpoint; put it in counter.yaml
# as ask_api. Safe to rerun.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
PY="${PY:-python}"
"$PY" make_system.py
rm -rf build && mkdir -p build
"$PY" -m pip install -q --target build --platform manylinux2014_x86_64 --implementation cp --python-version 3.13 \
  --only-binary=:all: --upgrade anthropic
rm -rf build/*.dist-info/RECORD
cp src/handler.py src/system.txt src/lexicon.json build/
sam deploy --template-file template.yaml --stack-name elyoxe-cinema-ask --region ap-south-1 \
  --capabilities CAPABILITY_IAM --resolve-s3 --no-fail-on-empty-changeset --no-confirm-changeset
aws cloudformation describe-stacks --region ap-south-1 --stack-name elyoxe-cinema-ask \
  --query "Stacks[0].Outputs[?OutputKey=='Endpoint'].OutputValue" --output text
