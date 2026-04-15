#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "$PROJECT_ROOT/venv/bin/python" ]]; then
        PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"
    elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
        PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
    elif [[ -x "$PROJECT_ROOT/venv/Scripts/python.exe" ]]; then
        PYTHON_BIN="$PROJECT_ROOT/venv/Scripts/python.exe"
    elif [[ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]]; then
        PYTHON_BIN="$PROJECT_ROOT/.venv/Scripts/python.exe"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python)"
    else
        echo "[maintenance] ERROR: No Python interpreter found." >&2
        exit 1
    fi
fi

exec "$PYTHON_BIN" "$PROJECT_ROOT/scripts/maintenance_lib.py" --project-root "$PROJECT_ROOT" "$@"