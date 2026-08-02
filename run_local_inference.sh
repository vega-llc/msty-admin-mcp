#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Run Install Msty Local Ops.command first." >&2
    exit 1
fi

export PYTHONUNBUFFERED=1
exec "$PYTHON_BIN" -m msty_ops.local_server
