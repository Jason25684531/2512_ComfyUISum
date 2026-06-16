#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT

printf 'sample' > "${TMP_FILE}"

echo "[1/5] health"
curl --fail --silent "${BASE_URL}/api/v1/health" >/dev/null

echo "[2/5] workflows"
curl --fail --silent "${BASE_URL}/api/v1/workflows" >/dev/null

echo "[3/5] asset upload"
curl --fail --silent -X POST "${BASE_URL}/api/v1/assets" -F "file=@${TMP_FILE};filename=sample.txt" >/dev/null

echo "[4/5] create mock job"
curl --fail --silent -X POST "${BASE_URL}/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"task_type":"text_to_image","params":{"prompt":"smoke test"},"input_assets":[],"priority":5}' >/dev/null

if command -v redis-cli >/dev/null 2>&1; then
  echo "[5/5] redis queue length"
  redis-cli llen studio:v2:jobs || true
else
  echo "[5/5] redis-cli not found, skip queue length"
fi

echo "smoke-test: PASS"
