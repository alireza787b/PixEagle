#!/bin/bash

# ============================================================================
# scripts/components/dashboard.sh - PixEagle Dashboard Server Script
# ============================================================================
# Runs the React dashboard in development or production mode.
#
# Features:
#   - Smart dependency caching
#   - Build caching for production mode
#   - Development mode with hot-reload
#
# Usage:
#   bash scripts/components/dashboard.sh
#   bash scripts/components/dashboard.sh -d      # Development mode
#   bash scripts/components/dashboard.sh -f      # Force rebuild
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

# Get directories
SCRIPTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

# Shared port helpers (optional).
PORTS_LIB="$SCRIPTS_DIR/lib/ports.sh"
if [ -f "$PORTS_LIB" ]; then
    # shellcheck source=/dev/null
    source "$PORTS_LIB"
fi

DASHBOARD_DEPENDENCIES_LIB="$SCRIPTS_DIR/lib/dashboard_dependencies.sh"
if [[ ! -f "$DASHBOARD_DEPENDENCIES_LIB" || -L "$DASHBOARD_DEPENDENCIES_LIB" ]]; then
    echo "Missing or unsafe dashboard dependency contract: $DASHBOARD_DEPENDENCIES_LIB"
    exit 1
fi
# shellcheck source=/dev/null
source "$DASHBOARD_DEPENDENCIES_LIB"

# Runtime versions are defined once for setup, CI, and the dashboard launcher.
NODE_VERSION_FILE="$PIXEAGLE_DIR/.nvmrc"
if [[ ! -f "$NODE_VERSION_FILE" || -L "$NODE_VERSION_FILE" ]]; then
    echo "Missing or unsafe Node.js version contract: $NODE_VERSION_FILE"
    exit 1
fi
REQUIRED_NODE_MAJOR="$(tr -d '[:space:]' < "$NODE_VERSION_FILE")"
if ! [[ "$REQUIRED_NODE_MAJOR" =~ ^[0-9]+$ ]]; then
    echo "Invalid Node.js major in $NODE_VERSION_FILE"
    exit 1
fi
MIN_NPM_VERSION=10
MAX_NPM_MAJOR=12

# Default Parameters
DEFAULT_DASHBOARD_DIR="$PIXEAGLE_DIR/dashboard"
DEFAULT_PORT="${PIXEAGLE_DEFAULT_DASHBOARD_PORT:-3040}"
DASHBOARD_HOST="${PIXEAGLE_DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_EXPOSURE_MODE="${PIXEAGLE_DASHBOARD_EXPOSURE_MODE:-local_only}"
if declare -f resolve_dashboard_port >/dev/null 2>&1; then
    DEFAULT_PORT="$(resolve_dashboard_port "$DEFAULT_DASHBOARD_DIR" 2>/dev/null || echo "$DEFAULT_PORT")"
fi

# Cache and optimization settings
CACHE_DIR=".pixeagle_cache"
FORCE_REBUILD=false

# Initialize variables
MODE="production"
POSITIONAL_ARGS=()
START_TIME=$(date +%s)

# Function to display usage instructions
display_usage() {
    echo "Usage: $0 [-d] [-f] [PORT] [DASHBOARD_DIR]"
    echo ""
    echo "Flags:"
    echo "  -d, --development : Run in development mode (default is production mode)"
    echo "  -f, --force       : Force rebuild even if no changes detected"
    echo "  -h, --help        : Display this help message"
    echo ""
    echo "Positional Arguments:"
    echo "  PORT           : Port to run the server on (default: $DEFAULT_PORT)"
    echo "  DASHBOARD_DIR  : Path to the dashboard directory (default: $DEFAULT_DASHBOARD_DIR)"
}

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--development)
            MODE="development"
            shift
            ;;
        -f|--force)
            FORCE_REBUILD=true
            shift
            ;;
        -h|--help)
            display_usage
            exit 0
            ;;
        -*)
            echo "Unknown option $1"
            display_usage
            exit 1
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done

# Restore positional arguments
set -- "${POSITIONAL_ARGS[@]}"

# Optionally allow the port and directory to be passed as arguments
PORT="${1:-$DEFAULT_PORT}"
DASHBOARD_DIR="${2:-$DEFAULT_DASHBOARD_DIR}"

if [[ "$DASHBOARD_EXPOSURE_MODE" != "local_only" && "$DASHBOARD_EXPOSURE_MODE" != "trusted_lan_legacy" ]]; then
    echo "Invalid PIXEAGLE_DASHBOARD_EXPOSURE_MODE: $DASHBOARD_EXPOSURE_MODE"
    exit 1
fi

if [[ "$DASHBOARD_HOST" != "127.0.0.1" && "$DASHBOARD_HOST" != "localhost" && "$DASHBOARD_EXPOSURE_MODE" != "trusted_lan_legacy" ]]; then
    echo "Non-loopback dashboard bind requires PIXEAGLE_DASHBOARD_EXPOSURE_MODE=trusted_lan_legacy"
    exit 1
fi

if [[ "$DASHBOARD_EXPOSURE_MODE" == "trusted_lan_legacy" && "$DASHBOARD_HOST" != "127.0.0.1" && "$DASHBOARD_HOST" != "localhost" ]]; then
    echo "WARNING: trusted_lan_legacy dashboard exposure is unauthenticated and not production-approved."
fi

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "Invalid port: $PORT"
    echo "Port must be an integer between 1 and 65535."
    exit 1
fi

# Function to display a header message
function header_message() {
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

# Function to compare semantic version numbers
version_ge() {
    printf '%s\n%s' "$2" "$1" | sort -V -C
}

# Function to calculate file hash for change detection
calculate_hash() {
    local file="$1"
    if [ -f "$file" ]; then
        if command -v sha256sum &> /dev/null; then
            sha256sum "$file" | cut -d' ' -f1
        elif command -v shasum &> /dev/null; then
            shasum -a 256 "$file" | cut -d' ' -f1
        else
            stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null
        fi
    else
        echo "missing"
    fi
}

# Function to check if build is needed
needs_build() {
    if [ "$FORCE_REBUILD" = "true" ]; then
        echo "true"
        return
    fi

    local cache_file="$CACHE_DIR/build_hash"
    local build_dir="build"

    if [ ! -d "$build_dir" ]; then
        echo "true"
        return
    fi

    local src_hash=""
    local package_hash cached_hash
    if [ -d "src" ]; then
        src_hash=$(find src public -type f \( -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" -o -name "*.css" -o -name "*.html" -o -name "*.json" \) -exec stat -c %Y {} \; 2>/dev/null | sort | sha256sum 2>/dev/null | cut -d' ' -f1 || echo "fallback")
    fi
    package_hash=$(calculate_hash "package.json")
    local current_hash="${src_hash}_${package_hash}"

    if [ -f "$cache_file" ]; then
        cached_hash=$(cat "$cache_file")
        if [ "$cached_hash" = "$current_hash" ]; then
            echo "false"
            return
        fi
    fi

    echo "true"
}

# Function to save build hash
save_build_hash() {
    local cache_file="$CACHE_DIR/build_hash"
    mkdir -p "$CACHE_DIR"

    local src_hash=""
    local package_hash
    if [ -d "src" ]; then
        src_hash=$(find src public -type f \( -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" -o -name "*.css" -o -name "*.html" -o -name "*.json" \) -exec stat -c %Y {} \; 2>/dev/null | sort | sha256sum 2>/dev/null | cut -d' ' -f1 || echo "fallback")
    fi
    package_hash=$(calculate_hash "package.json")
    echo "${src_hash}_${package_hash}" > "$cache_file"
}

# 1. Display initial information
header_message "Starting PixEagle Dashboard Server"
echo "Mode: $MODE"
echo "Using dashboard directory: $DASHBOARD_DIR"
echo "Server will run on port: $PORT"

if [ "$MODE" = "development" ]; then
    echo "Note: Development mode provides hot-reloading and detailed error messages."
else
    echo "Note: Production mode serves the optimized build for better performance."
fi
echo ""

# 2. Navigate to the PixEagle dashboard directory
header_message "Navigating to the PixEagle dashboard directory"
if [ -d "$DASHBOARD_DIR" ]; then
    cd "$DASHBOARD_DIR" || { echo "Failed to navigate to $DASHBOARD_DIR"; exit 1; }
    echo "Current directory: $(pwd)"
else
    echo "Directory $DASHBOARD_DIR does not exist. Please check the path."
    exit 1
fi
echo ""

# 3. Check if Node.js and npm are installed
header_message "Checking Node.js and npm installations"

if ! command -v node &> /dev/null; then
    echo "Node.js is not installed. Run 'make init' to install Node.js ${REQUIRED_NODE_MAJOR}.x."
    exit 1
else
    NODE_VERSION=$(node -v | sed 's/v//')
    NODE_MAJOR="${NODE_VERSION%%.*}"
    if [[ "$NODE_MAJOR" == "$REQUIRED_NODE_MAJOR" ]]; then
        echo "Node.js version $NODE_VERSION is installed."
    else
        echo "Node.js $NODE_VERSION does not match the reviewed ${REQUIRED_NODE_MAJOR}.x runtime. Run 'make init'."
        exit 1
    fi
fi

if ! command -v npm &> /dev/null; then
    echo "npm is not installed. Please install npm version $MIN_NPM_VERSION or higher."
    exit 1
else
    NPM_VERSION=$(npm -v)
    NPM_MAJOR="${NPM_VERSION%%.*}"
    if version_ge "$NPM_VERSION" "$MIN_NPM_VERSION" \
        && [[ "$NPM_MAJOR" =~ ^[0-9]+$ ]] \
        && (( NPM_MAJOR < MAX_NPM_MAJOR )); then
        echo "npm version $NPM_VERSION is installed."
    else
        echo "npm $NPM_VERSION is outside the reviewed >=${MIN_NPM_VERSION}, <${MAX_NPM_MAJOR} range. Run 'make init'."
        exit 1
    fi
fi
echo ""

# 4. Install required npm packages if necessary
header_message "Checking npm dependencies"

if ! pixeagle_dashboard_dependencies_ready "$DASHBOARD_DIR"; then
    echo "Dashboard dependency state is incomplete or outdated."
    echo "Reconciling exactly from package-lock.json with npm ci..."
    if npm ci --no-audit --no-fund; then
        echo "npm packages installed successfully"
        if ! pixeagle_record_dashboard_dependency_fingerprint "$DASHBOARD_DIR"; then
            echo "WARNING: dependency cache could not be recorded; a later start may reconcile again."
        fi
    else
        echo "Failed to reconcile npm packages from package-lock.json"
        exit 1
    fi
else
    echo "Dependencies match package-lock.json (verified cache hit)"
fi
echo ""

# 5. Check if the server is already running on the specified port
header_message "Checking if server is already running on port $PORT"
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN &> /dev/null; then
    echo "Port $PORT is already in use. Refusing to stop an unknown process from the dashboard component script."
    echo "Use 'make stop' to stop PixEagle services, or free/change the configured dashboard port."
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN || true
    exit 1
else
    echo "Port $PORT is free."
fi
echo ""

# 6. Start the server based on the mode
header_message "Starting the Dashboard Server in $MODE mode on port $PORT"

export PORT="$PORT"

if [ "$MODE" = "development" ]; then
    HOST="$DASHBOARD_HOST" npm start
else
    # Production mode - build if needed
    header_message "Preparing production build"

    if [ "$(needs_build)" = "true" ]; then
        echo "Building the app for production..."
        BUILD_START=$(date +%s)
        if ! npm run build; then
            echo "Build failed. Please check the error messages above."
            exit 1
        else
            BUILD_END=$(date +%s)
            BUILD_TIME=$((BUILD_END - BUILD_START))
            echo "Build completed successfully in ${BUILD_TIME}s."
            save_build_hash
        fi
    else
        echo "Using cached build (no changes detected)."
    fi

    # Start the server using 'serve'
    header_message "Serving the production build on port $PORT"
    echo "Starting production server..."
    echo ""

    echo "Dashboard URLs:"
    echo "   http://$DASHBOARD_HOST:$PORT"
    echo ""

    NO_UPDATE_NOTIFIER=1 npx serve -s build -l "tcp://$DASHBOARD_HOST:$PORT" --no-clipboard
fi

# 7. Performance summary
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

header_message "Dashboard Server Running"
echo "The server is now running and can be accessed via your browser."
echo "Press Ctrl+C to stop the server at any time."
echo ""
echo "Total startup time: ${TOTAL_TIME}s"
