#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(dirname "$SCRIPT_DIR")
VENV_DIR=${AKSHARE_FUND_VENV:-"$SKILL_DIR/.venv"}

is_valid_runtime() {
    "$1" -c '
import sys
from importlib.metadata import version

if not (sys.version_info >= (3, 9) and sys.version_info < (3, 13)):
    raise SystemExit(1)
expected = {
    "akshare": "1.18.64",
    "pandas": "2.3.3",
    "numpy": "2.0.2",
    "requests": "2.32.5",
    "curl_cffi": "0.13.0",
}
if any(version(package) != required for package, required in expected.items()):
    raise SystemExit(1)
' >/dev/null 2>&1
}

if [ -x "$VENV_DIR/bin/python" ]; then
    if is_valid_runtime "$VENV_DIR/bin/python"; then
        PYTHON="$VENV_DIR/bin/python"
    else
        printf 'Invalid AKShare environment: %s\nRepair it with: bash "%s/scripts/setup.sh"\n' \
            "$VENV_DIR" "$SKILL_DIR" >&2
        exit 2
    fi
elif command -v python3 >/dev/null 2>&1 && is_valid_runtime python3; then
    PYTHON=python3
else
    printf 'Missing AKShare environment. Run: bash "%s/scripts/setup.sh"\n' "$SKILL_DIR" >&2
    exit 2
fi

exec "$PYTHON" "$SCRIPT_DIR/fund_advisor.py" "$@"
