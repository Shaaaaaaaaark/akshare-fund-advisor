#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(dirname "$SCRIPT_DIR")
VENV_DIR=${AKSHARE_FUND_VENV:-"$SKILL_DIR/.venv"}

if ! python3 -c 'import sys; raise SystemExit(0 if (3, 9) <= sys.version_info < (3, 13) else 1)'; then
    printf 'Python 3.9 through 3.12 is required.\n' >&2
    exit 2
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -r "$SKILL_DIR/requirements.txt"
"$VENV_DIR/bin/python" -m pip check
"$VENV_DIR/bin/python" -c '
from importlib.metadata import version

expected = {
    "akshare": "1.18.64",
    "pandas": "2.3.3",
    "numpy": "2.0.2",
    "requests": "2.32.5",
    "curl_cffi": "0.13.0",
}
if any(version(package) != required for package, required in expected.items()):
    raise SystemExit("Unexpected runtime dependency version")
'

printf 'AKShare fund advisor environment: %s\n' "$VENV_DIR"
