#!/usr/bin/env bash
# Canonical PixEagle SD tools; all behavior lives in the standard-library helper.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "$SCRIPT_DIR/sd_card.py" "$@"
