#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PYTHON=""
  for candidate in python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,12))' 2>/dev/null; then
      PYTHON="$candidate"
      break
    fi
  done
  if [ -z "$PYTHON" ]; then
    echo "Python 3.12 or newer is required. Install Python, then double-click this shortcut again."
    read -r -p "Press Return to close..."
    exit 1
  fi
  "$PYTHON" -m venv "$ROOT/.venv"
  PY="$ROOT/.venv/bin/python"
fi

if ! "$PY" -c 'import openpyxl' >/dev/null 2>&1; then
  echo "Installing the pinned workbook reader (first run only)..."
  "$PY" -m pip install --disable-pip-version-check "openpyxl==3.1.5"
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
echo "Starting UT Review. Keep this window open while using the app."
"$PY" -m evaluator --project "$HOME/UT Inspection Evaluator"
