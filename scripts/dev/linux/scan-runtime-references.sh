#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
REPORT_DIR="${ROOT_DIR}/reports"
REPORT_PATH="${REPORT_DIR}/runtime-reference-scan.txt"

mkdir -p "${REPORT_DIR}"

run_git_grep() {
  local pattern="$1"
  if git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "${ROOT_DIR}" grep -n -I -E "${pattern}" -- \
      apps backend worker tests docs scripts shared frontend \
      'ComfyUIworkflow*' '.env*' 'docker-compose*.yml' 2>/dev/null || true
  else
    printf "git worktree unavailable for pattern: %s\n" "${pattern}"
  fi
}

{
  printf "# Runtime Reference Scan\n"
  printf "Generated from: scripts/dev/linux/scan-runtime-references.sh\n\n"

  printf "## Python runtime path references\n"
  printf "Pattern: backend/src/app.py | worker/src/main.py | apps/backend-fastapi | apps/worker-v2\n"
  run_git_grep "backend/src/app.py|worker/src/main.py|apps/backend-fastapi|apps/worker-v2"
  printf "\n"

  printf "## Workflow folder references\n"
  printf "Pattern: ComfyUIworkflow | ComfyUIworkflow_api\n"
  run_git_grep "ComfyUIworkflow|ComfyUIworkflow_api"
  printf "\n"

  printf "## Storage path references\n"
  printf "Pattern: storage/outputs | storage/assets | OUTPUT_ROOT | ASSET_ROOT | STORAGE_ROOT\n"
  run_git_grep "storage/outputs|storage/assets|OUTPUT_ROOT|ASSET_ROOT|STORAGE_ROOT"
  printf "\n"

  printf "## Redis queue references\n"
  printf "Pattern: studio:v2:jobs | studio:v2:cancel: | REDIS_URL | redis\n"
  run_git_grep "studio:v2:jobs|studio:v2:cancel:|REDIS_URL|redis"
  printf "\n"

  printf "## API endpoint references\n"
  printf "Pattern: /api/generate | /api/status | /api/v1/jobs | /api/v1/assets | /api/v1/outputs\n"
  run_git_grep "/api/generate|/api/status|/api/v1/jobs|/api/v1/assets|/api/v1/outputs"
  printf "\n"

  printf "## Compose, env, and start-script files\n"
  if git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "${ROOT_DIR}" ls-files | grep -E '(^docker-compose.*\.yml$)|(^\.env)|(^scripts/.*/start.*\.(sh|bat)$)|(^scripts/start.*\.(sh|bat)$)' || true
  fi
  printf "\n"
} > "${REPORT_PATH}"

printf "Wrote runtime reference scan to %s\n" "${REPORT_PATH}"
