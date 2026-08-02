#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${MSTY_LOCAL_OPS_INSTALL_ROOT:-${HOME}/Library/Application Support/Msty Local Ops}"
VENV_DIR="$INSTALL_ROOT/venv"
CONFIG_DIR="$INSTALL_ROOT/config"

finish() {
    if [[ "${MSTY_LOCAL_OPS_NO_PAUSE:-0}" == "1" ]]; then
        return
    fi
    printf "\nPress Return to close this window."
    read -r _
}
trap finish EXIT

echo "Installing Msty Local Ops..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10, 3.11, or 3.12 is required. Install Python from python.org and try again." >&2
    exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)'; then
    echo "Python 3.10, 3.11, or 3.12 is required." >&2
    exit 1
fi

mkdir -p "$INSTALL_ROOT" "$CONFIG_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install \
    --disable-pip-version-check \
    --require-hashes \
    -r "$SOURCE_DIR/requirements-audit.txt"
"$VENV_DIR/bin/python" -m pip install \
    --disable-pip-version-check \
    --no-deps \
    --upgrade \
    "$SOURCE_DIR"
"$VENV_DIR/bin/python" "$SOURCE_DIR/scripts/write_toolbox_configs.py" \
    --python "$VENV_DIR/bin/python" \
    --output "$CONFIG_DIR"
"$VENV_DIR/bin/python" "$SOURCE_DIR/scripts/check_installed.py" \
    --mode diagnostic \
    --allow-no-models

echo
echo "Installation passed."
echo "In Msty Studio, open Toolbox > Add New Tool > STDIO / JSON."
echo "Paste the diagnostic configuration first:"
echo "$CONFIG_DIR/msty-toolbox-diagnostic.json"
echo
echo "The local-inference configuration is optional and exposes prompt content to the MCP client:"
echo "$CONFIG_DIR/msty-toolbox-local-inference.json"
if [[ "${MSTY_LOCAL_OPS_NO_OPEN:-0}" != "1" ]]; then
    open "$CONFIG_DIR"
fi
