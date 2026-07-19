#!/usr/bin/env bash
# Start the safe same-host beginner demo without PX4/MAVSDK side effects.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON:-$PROJECT_ROOT/.venv/bin/python}"
DRY_RUN="${DRY_RUN:-0}"

case "${DRY_RUN,,}" in
    1|true|yes|on) DRY_RUN=true ;;
    0|false|no|off|'') DRY_RUN=false ;;
    *)
        printf 'ERROR: DRY_RUN must be 0/1, true/false, yes/no, or on/off.\n' >&2
        exit 2
        ;;
esac

if [[ ! -x "$PYTHON_BIN" ]]; then
    printf 'ERROR: PixEagle is not initialized. Run make init first.\n' >&2
    exit 1
fi

cd "$PROJECT_ROOT"

profile_args=(--profile beginner_lab)
if [[ "$DRY_RUN" == "true" ]]; then
    profile_args+=(--dry-run)
fi

"$PYTHON_BIN" scripts/setup/apply-setup-profile.py "${profile_args[@]}"

if [[ "$DRY_RUN" == "true" ]]; then
    printf '\nDry run complete. No config or runtime was changed.\n'
    exit 0
fi

bash scripts/run.sh --no-attach -m -k

dashboard_port="$(bash scripts/lib/ports.sh --dashboard-port "$PROJECT_ROOT/dashboard" 2>/dev/null || printf '3040')"
printf '\nBeginner demo started.\n'
printf 'Open: http://127.0.0.1:%s\n' "$dashboard_port"
printf 'Mode: recorded video + local follower test; PX4/MAVSDK commands are disabled.\n'
printf 'Stop: make stop\n'
