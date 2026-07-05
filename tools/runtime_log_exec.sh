#!/bin/bash
# Mirror a component command to the terminal and PixEagle runtime JSONL logs.

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

resolve_python_interpreter() {
    if [[ -x "$PIXEAGLE_DIR/.venv/bin/python" ]]; then
        echo "$PIXEAGLE_DIR/.venv/bin/python"
    elif [[ -x "$PIXEAGLE_DIR/venv/bin/python" ]]; then
        echo "$PIXEAGLE_DIR/venv/bin/python"
    else
        echo "python3"
    fi
}

component="$1"
shift || true
if [[ "${1:-}" == "--" ]]; then
    shift
fi

if [[ -z "$component" || "$#" -eq 0 ]]; then
    echo "Usage: $0 <component> -- <command> [args...]" >&2
    exit 2
fi

python="${PIXEAGLE_RUNTIME_LOG_PIPE_PYTHON:-$(resolve_python_interpreter)}"
pipe_tool="$PIXEAGLE_DIR/tools/runtime_log_pipe.py"

"$@" 2>&1 | "$python" "$pipe_tool" \
    --component "$component" \
    --stream combined \
    --source launcher-pipe \
    --mirror
component_exit=${PIPESTATUS[0]}

echo
echo "Component exited with code $component_exit"
exit "$component_exit"
