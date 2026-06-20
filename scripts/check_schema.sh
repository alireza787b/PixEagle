#!/usr/bin/env bash
# scripts/check_schema.sh
# CI check: verifies config_schema.yaml is in sync with config_default.yaml.
#
# Usage:
#   bash scripts/check_schema.sh          # Check only
#   bash scripts/check_schema.sh --fix    # Regenerate schema and exit 0
#
# Exit codes:
#   0 = schema is up-to-date (or --fix was used)
#   1 = schema is out of sync

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FIX_MODE=false
for arg in "$@"; do
    [[ "$arg" == "--fix" ]] && FIX_MODE=true
done

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
        PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    else
        echo "ERROR: python3 or python is required to generate the schema." >&2
        exit 1
    fi
fi

if $FIX_MODE; then
    echo "Regenerating schema..."
    "$PYTHON_BIN" "$SCRIPT_DIR/generate_schema.py"
    echo "Schema regenerated (--fix mode)."
    exit 0
fi

EXPECTED_SCHEMA="$(mktemp)"
trap 'rm -f "$EXPECTED_SCHEMA"' EXIT

echo "Running schema generator in check mode..."
"$PYTHON_BIN" "$SCRIPT_DIR/generate_schema.py" \
    "$PROJECT_ROOT/configs/config_default.yaml" \
    "$EXPECTED_SCHEMA"

if cmp -s "$EXPECTED_SCHEMA" "$PROJECT_ROOT/configs/config_schema.yaml"; then
    echo "Schema is up-to-date."
    exit 0
else
    echo ""
    echo "ERROR: configs/config_schema.yaml is out of sync with config_default.yaml."
    echo "Run the following command to update it:"
    echo ""
    echo "    bash scripts/check_schema.sh --fix"
    echo ""
    echo "Then commit the updated config_schema.yaml."
    exit 1
fi
