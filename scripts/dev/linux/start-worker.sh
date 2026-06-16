#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env.local-wsl"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export PYTHONPATH="${REPO_ROOT}:${REPO_ROOT}/apps/backend-fastapi:${REPO_ROOT}/packages/workflow_registry:${PYTHONPATH:-}"

cd "${REPO_ROOT}/apps/worker-v2"
exec python -m worker.main
