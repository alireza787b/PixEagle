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

echo "Running schema generator..."
python "$SCRIPT_DIR/generate_schema.py"

if $FIX_MODE; then
    echo "Schema regenerated (--fix mode)."
    exit 0
fi

UNTRACKED=$(git -C "$PROJECT_ROOT" ls-files --others --exclude-standard configs/config_schema.yaml)
MODIFIED=$(git -C "$PROJECT_ROOT" diff --name-only configs/config_schema.yaml)

if [ -z "$UNTRACKED" ] && [ -z "$MODIFIED" ]; then
    echo "Schema is up-to-date."
    exit 0
else
    echo ""
    echo "ERROR: configs/config_schema.yaml is out of sync with config_default.yaml."
    echo "Run the following command to update it:"
    echo ""
    echo "    python scripts/generate_schema.py"
    echo ""
    echo "Then commit the updated config_schema.yaml."
    exit 1
fi
