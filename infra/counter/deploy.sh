#!/usr/bin/env bash
# deploy.sh — the counter + Web Push stack (elyoxe-cinema-counter), ap-south-1, separate from
# the site stack. Safe to re-run: every step is idempotent (SSM params created once, layer built
# once, `sam deploy` no-ops on an unchanged template). Never touches the site bucket, the
# CloudFront distributions or DNS.
set -euo pipefail
# Git Bash on Windows rewrites a bare leading "/name" into a Windows path before it ever reaches
# aws — every `/elyoxe/...` SSM parameter name below would silently become a drive path and the
# API replies "Parameter name must be a fully qualified name" (found live, 2026-09-30). This must
# stay set for the whole script.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${CINEMA_COUNTER_REGION:-ap-south-1}"
STACK="${CINEMA_COUNTER_STACK:-elyoxe-cinema-counter}"
ORIGINS="${CINEMA_COUNTER_ORIGINS:-https://cinema.elyoxe.com}"
NS="/elyoxe/cinema/counter"

# 1. the Web Push layer — cryptography + py-vapid + http-ece + pywebpush, downloaded as
# manylinux wheels (no docker: pip just fetches the prebuilt binary, it never compiles one),
# gitignored (infra/counter/layer/.gitignore), rebuilt here whenever missing.
if [[ ! -d "$HERE/layer/python/cryptography" ]]; then
  rm -rf "$HERE/layer"; mkdir -p "$HERE/layer/python"
  python3 -m pip install --quiet --platform manylinux2014_x86_64 --implementation cp \
    --python-version 3.12 --only-binary=:all: --target "$HERE/layer/python" cryptography
  python3 -m pip install --quiet --no-deps --target "$HERE/layer/python" py-vapid http-ece pywebpush cffi
  # the no-deps step above has no --platform, so pip may also drop a Windows _cffi_backend
  # build (and a cffi-gen-src.exe under bin/) when run from this laptop; only the Linux .so may
  # ship in the layer.
  rm -f "$HERE/layer/python"/_cffi_backend*win_amd64* 2>/dev/null || true
  rm -rf "$HERE/layer/python/bin" 2>/dev/null || true
  find "$HERE/layer/python" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
  echo "layer built: $(du -sh "$HERE/layer" | cut -f1)"
fi

# 2. VAPID keypair (raw web-push format: public = base64url uncompressed P-256 point, private =
# base64url 32-byte scalar — the same shapes the `web-push` npm CLI and pywebpush both expect),
# generated once and kept in SSM. The public half is not a secret (it ships to every browser).
PUB_PARAM="$NS/vapid-public"
PRIV_PARAM="$NS/vapid-private"
if ! aws ssm get-parameter --region "$REGION" --name "$PRIV_PARAM" >/dev/null 2>&1; then
  KEYPAIR=$(python3 - <<'PY'
import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

key = ec.generate_private_key(ec.SECP256R1())
priv_b = key.private_numbers().private_value.to_bytes(32, "big")
pub = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
print(f"{b64(pub)} {b64(priv_b)}")
PY
)
  VAPID_PUB=${KEYPAIR% *}
  VAPID_PRIV=${KEYPAIR#* }
  aws ssm put-parameter --region "$REGION" --name "$PUB_PARAM" --type String --value "$VAPID_PUB" --overwrite >/dev/null
  aws ssm put-parameter --region "$REGION" --name "$PRIV_PARAM" --type SecureString --value "$VAPID_PRIV" --overwrite >/dev/null
  echo "VAPID keypair generated: $PUB_PARAM (public, safe to embed in client JS)"
fi
VAPID_PUBLIC_KEY=$(aws ssm get-parameter --region "$REGION" --name "$PUB_PARAM" --query Parameter.Value --output text)

# 3. the owner's /stats secret (a long random token in the URL — accepted on this account,
# feedback_aws_root_access.md).
SECRET_PARAM="$NS/stats-secret"
if ! aws ssm get-parameter --region "$REGION" --name "$SECRET_PARAM" >/dev/null 2>&1; then
  aws ssm put-parameter --region "$REGION" --name "$SECRET_PARAM" --type SecureString \
    --value "$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" >/dev/null
  echo "stats secret created at $SECRET_PARAM"
fi

# 4. the stack
cd "$HERE"
sam build --template-file template.yaml >/dev/null
sam deploy --stack-name "$STACK" --region "$REGION" --capabilities CAPABILITY_IAM \
  --resolve-s3 --no-confirm-changeset --no-fail-on-empty-changeset \
  --parameter-overrides "AllowedOrigins=$ORIGINS" "VapidPublicKey=$VAPID_PUBLIC_KEY"

ENDPOINT=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='Endpoint'].OutputValue" --output text)
SECRET=$(aws ssm get-parameter --region "$REGION" --name "$SECRET_PARAM" --with-decryption --query Parameter.Value --output text)
echo "endpoint: $ENDPOINT"
echo "stats: ${ENDPOINT}stats?secret=$SECRET"
echo "vapid public key (embed in client JS): $VAPID_PUBLIC_KEY"
