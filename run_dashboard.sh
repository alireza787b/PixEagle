#!/bin/bash

#########################################
# PixEagle Dashboard Server Script
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
#
# This script automates the process of starting the React
# server for the PixEagle dashboard. It includes customizable
# parameters for the port and directory, and provides step-by-step
# progress updates. It intelligently handles npm installations
# and checks for required versions of Node.js and npm.
#
# By default, it runs in production mode, serving the optimized
# build files. Use the -d flag to run in development mode.
#
# Default Usage: ./run_dashboard.sh
# Custom Port:   ./run_dashboard.sh <PORT>
# Custom Dir:    ./run_dashboard.sh <PORT> <DASHBOARD_DIR>
# Development Mode: ./run_dashboard.sh -d
#
# Flags:
#   -d : Run in development mode (default is production mode)
#
# Example:
#   ./run_dashboard.sh -d 3001
#   (Runs the dashboard in development mode on port 3001)
#
#########################################

# Minimum required versions
MIN_NODE_VERSION=12
MIN_NPM_VERSION=6

# Default Parameters (user can modify these)
DEFAULT_PORT=3000
DEFAULT_DASHBOARD_DIR="$HOME/PixEagle/dashboard"

# Cache and optimization settings
CACHE_DIR=".pixeagle_cache"
FORCE_REBUILD=false

# Resolve script directory to support execution from any location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
  echo ""
  echo "Examples:"
  echo "  $0            # Runs in production mode on default port"
  echo "  $0 -d         # Runs in development mode on default port"
  echo "  $0 4000       # Runs in production mode on port 4000"
  echo "  $0 -d 4000    # Runs in development mode on port 4000"
  echo "  $0 -f         # Force rebuild in production mode"
}

# Parse options
while [[ $# -gt 0 ]]; do
  case $1 in
    -d|--development)
      MODE="development"
      shift # Remove argument from processing
      ;;
    -f|--force)
      FORCE_REBUILD=true
      shift # Remove argument from processing
      ;;
    -h|--help)
      display_usage
      exit 0
      ;;
    -*|--*)
      echo "Unknown option $1"
      display_usage
      exit 1
      ;;
    *)
      POSITIONAL_ARGS+=("$1") # Save positional argument
      shift
      ;;
  esac
done

# Restore positional arguments
set -- "${POSITIONAL_ARGS[@]}"

# Optionally allow the port and directory to be passed as arguments
PORT="${1:-$DEFAULT_PORT}"
DASHBOARD_DIR="${2:-$DEFAULT_DASHBOARD_DIR}"

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
    # Use different hash commands based on availability
    if command -v sha256sum &> /dev/null; then
      sha256sum "$file" | cut -d' ' -f1
    elif command -v shasum &> /dev/null; then
      shasum -a 256 "$file" | cut -d' ' -f1
    else
      # Fallback to modification time
      stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null
    fi
  else
    echo "missing"
  fi
}

# Function to check if dependencies need reinstallation
needs_dependency_install() {
  local cache_file="$CACHE_DIR/deps_hash"

  # Create cache directory if it doesn't exist
  mkdir -p "$CACHE_DIR"

  # Calculate current hashes
  local package_hash=$(calculate_hash "package.json")
  local lock_hash=$(calculate_hash "package-lock.json")
  local current_hash="${package_hash}_${lock_hash}"

  # Check if node_modules exists
  if [ ! -d "node_modules" ]; then
    echo "true"
    return
  fi

  # Check cached hash
  if [ -f "$cache_file" ]; then
    local cached_hash=$(cat "$cache_file")
    if [ "$cached_hash" = "$current_hash" ]; then
      echo "false"
      return
    fi
  fi

  echo "true"
}

# Function to save dependency hash
save_dependency_hash() {
  local cache_file="$CACHE_DIR/deps_hash"
  local package_hash=$(calculate_hash "package.json")
  local lock_hash=$(calculate_hash "package-lock.json")
  echo "${package_hash}_${lock_hash}" > "$cache_file"
}

# Function to check if build is needed
needs_build() {
  if [ "$FORCE_REBUILD" = "true" ]; then
    echo "true"
    return
  fi

  local cache_file="$CACHE_DIR/build_hash"
  local build_dir="build"

  # If build directory doesn't exist, need to build
  if [ ! -d "$build_dir" ]; then
    echo "true"
    return
  fi

  # Calculate hash of source files
  local src_hash=""
  if [ -d "src" ]; then
    src_hash=$(find src public -type f \( -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" -o -name "*.css" -o -name "*.html" -o -name "*.json" \) -exec stat -c %Y {} \; 2>/dev/null | sort | sha256sum 2>/dev/null | cut -d' ' -f1 || echo "fallback")
  fi
  local package_hash=$(calculate_hash "package.json")
  local current_hash="${src_hash}_${package_hash}"

  # Check cached hash
  if [ -f "$cache_file" ]; then
    local cached_hash=$(cat "$cache_file")
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
  if [ -d "src" ]; then
    src_hash=$(find src public -type f \( -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" -o -name "*.css" -o -name "*.html" -o -name "*.json" \) -exec stat -c %Y {} \; 2>/dev/null | sort | sha256sum 2>/dev/null | cut -d' ' -f1 || echo "fallback")
  fi
  local package_hash=$(calculate_hash "package.json")
  echo "${src_hash}_${package_hash}" > "$cache_file"
}

# 1. Display initial information
header_message "Starting PixEagle Dashboard Server"
echo "Mode: $MODE"
echo "Using dashboard directory: $DASHBOARD_DIR"
echo "Server will run on port: $PORT"
echo "You can modify the directory or port by editing the script or passing them as arguments."
echo ""
if [ "$MODE" = "development" ]; then
  echo "Note: Development mode provides hot-reloading and detailed error messages."
else
  echo "Note: Production mode serves the optimized build for better performance."
fi
echo ""

# 2. Navigate to the PixEagle dashboard directory
header_message "Navigating to the PixEagle dashboard directory"
if [ -d "$DASHBOARD_DIR" ]; then
  cd "$DASHBOARD_DIR" || { echo "❌ Failed to navigate to $DASHBOARD_DIR"; exit 1; }
  echo "✅ Current directory: $(pwd)"
else
  echo "❌ Directory $DASHBOARD_DIR does not exist. Please check the path."
  exit 1
fi
echo ""

# 3. Check if Node.js and npm are installed and meet minimum version requirements
header_message "Checking Node.js and npm installations"

# Check Node.js
if ! command -v node &> /dev/null; then
  echo "❌ Node.js is not installed. Please install Node.js version $MIN_NODE_VERSION or higher."
  exit 1
else
  NODE_VERSION=$(node -v | sed 's/v//')
  if version_ge "$NODE_VERSION" "$MIN_NODE_VERSION"; then
    echo "✅ Node.js version $NODE_VERSION is installed."
  else
    echo "❌ Node.js version $NODE_VERSION is installed. Please upgrade to version $MIN_NODE_VERSION or higher."
    exit 1
  fi
fi

# Check npm
if ! command -v npm &> /dev/null; then
  echo "❌ npm is not installed. Please install npm version $MIN_NPM_VERSION or higher."
  exit 1
else
  NPM_VERSION=$(npm -v)
  if version_ge "$NPM_VERSION" "$MIN_NPM_VERSION"; then
    echo "✅ npm version $NPM_VERSION is installed."
  else
    echo "❌ npm version $NPM_VERSION is installed. Please upgrade to version $MIN_NPM_VERSION or higher."
    exit 1
  fi
fi
echo ""

# 4. Install required npm packages if necessary
header_message "Checking npm dependencies"

# Function to validate package-lock.json integrity
validate_lockfile() {
  if [ ! -f "package-lock.json" ]; then
    echo "⚠️  package-lock.json not found"
    return 1
  fi

  if [ ! -d "node_modules" ]; then
    echo "ℹ️  node_modules not found (first-time install)"
    return 0
  fi

  # Check if lockfile is valid JSON
  if ! python3 -c "import json; json.load(open('package-lock.json'))" 2>/dev/null; then
    echo "⚠️  package-lock.json is corrupted (invalid JSON)"
    return 1
  fi

  return 0
}

# Function to perform npm install with robust error handling
install_npm_dependencies() {
  local install_success=false
  local attempt=1
  local max_attempts=3

  echo "📦 Installing npm dependencies..."

  # Strategy 1: Try npm ci first (fastest, most reliable if lockfile is good)
  if [ -f "package-lock.json" ] && validate_lockfile; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 Attempt $attempt: Using 'npm ci' (clean install from lockfile)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if npm ci 2>&1 | tee /tmp/npm_ci.log; then
      if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "✅ npm ci completed successfully"
        install_success=true
        return 0
      fi
    fi

    echo "⚠️  npm ci failed. Analyzing error..."

    # Check for common npm ci failure patterns
    if grep -q "lock file's .* does not match" /tmp/npm_ci.log || \
       grep -q "Missing:" /tmp/npm_ci.log || \
       grep -q "lockfile" /tmp/npm_ci.log; then
      echo "🔍 Detected lockfile integrity issue"
      echo "💡 This usually happens when:"
      echo "   • package-lock.json is out of sync with package.json"
      echo "   • Different npm versions were used"
      echo "   • Cross-platform development (Windows ↔ Linux)"
    fi
  fi

  # Strategy 2: Remove node_modules and try npm ci again
  if [ ! "$install_success" = true ]; then
    attempt=$((attempt + 1))
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔄 Attempt $attempt: Removing node_modules and retrying npm ci"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ -d "node_modules" ]; then
      echo "🗑️  Removing existing node_modules..."
      rm -rf node_modules
      echo "✅ node_modules removed"
    fi

    if [ -f "package-lock.json" ]; then
      echo "🔄 Retrying npm ci with clean slate..."
      if npm ci 2>&1 | tee /tmp/npm_ci_retry.log; then
        if [ ${PIPESTATUS[0]} -eq 0 ]; then
          echo "✅ npm ci completed successfully after cleanup"
          install_success=true
          return 0
        fi
      fi
    fi
  fi

  # Strategy 3: Regenerate package-lock.json with npm install
  if [ ! "$install_success" = true ]; then
    attempt=$((attempt + 1))
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔧 Attempt $attempt: Regenerating lockfile with 'npm install'"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "⚠️  This will regenerate package-lock.json"

    # Backup existing lockfile
    if [ -f "package-lock.json" ]; then
      echo "💾 Backing up existing package-lock.json..."
      cp package-lock.json package-lock.json.backup
      echo "✅ Backup saved as package-lock.json.backup"
    fi

    # Remove lockfile to force regeneration
    rm -f package-lock.json

    echo "🔄 Running 'npm install' to regenerate lockfile..."
    if npm install 2>&1 | tee /tmp/npm_install.log; then
      if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "✅ npm install completed successfully"
        echo "✅ New package-lock.json generated"
        install_success=true
        return 0
      fi
    fi
  fi

  # All strategies failed
  if [ ! "$install_success" = true ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "❌ All npm install strategies failed"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "📋 Troubleshooting steps:"
    echo "   1. Check npm version: npm -v (should be >= $MIN_NPM_VERSION)"
    echo "   2. Check Node.js version: node -v (should be >= $MIN_NODE_VERSION)"
    echo "   3. Clear npm cache: npm cache clean --force"
    echo "   4. Check disk space: df -h"
    echo "   5. Check permissions: ls -la node_modules"
    echo ""
    echo "📝 Error logs saved to:"
    echo "   • /tmp/npm_ci.log"
    echo "   • /tmp/npm_ci_retry.log"
    echo "   • /tmp/npm_install.log"
    echo ""
    return 1
  fi
}

# Smart dependency management with change detection
if [ "$(needs_dependency_install)" = "true" ]; then
  if install_npm_dependencies; then
    echo ""
    echo "✅ npm packages installed successfully"
    save_dependency_hash
  else
    echo ""
    echo "❌ Failed to install npm packages after all attempts"
    echo "💡 Please review the error logs above and try manual installation"
    exit 1
  fi
else
  echo "✅ Dependencies are up to date (cache hit)"
  echo "ℹ️  Skipping npm install based on dependency hash check"
fi
echo ""

# 5. Check if the server is already running on the specified port
header_message "Checking if server is already running on port $PORT"
if lsof -i tcp:"$PORT" &> /dev/null; then
  echo "⚠️  A process is already running on port $PORT. Attempting to kill it..."
  PID=$(lsof -t -i tcp:"$PORT")
  if kill -9 "$PID" &> /dev/null; then
    echo "✅ Successfully killed process $PID."
  else
    echo "❌ Failed to kill process $PID. Please free up port $PORT manually."
    exit 1
  fi
else
  echo "✅ Port $PORT is free."
fi
echo ""

# 6. Start the server based on the mode
header_message "Starting the Dashboard Server in $MODE mode on port $PORT"

# Set the PORT environment variable
export PORT="$PORT"

if [ "$MODE" = "development" ]; then
  # Start the development server
  npm start
  if [ $? -eq 0 ]; then
    echo "✅ Development server started successfully on port $PORT."
  else
    echo "❌ Failed to start the development server. Please check the error messages above."
    exit 1
  fi
else
  # Smart build with caching
  header_message "Preparing production build"

  if [ "$(needs_build)" = "true" ]; then
    echo "🔨 Building the app for production..."
    BUILD_START=$(date +%s)
    npm run build
    if [ $? -ne 0 ]; then
      echo "❌ Build failed. Please check the error messages above."
      exit 1
    else
      BUILD_END=$(date +%s)
      BUILD_TIME=$((BUILD_END - BUILD_START))
      echo "✅ Build completed successfully in ${BUILD_TIME}s."
      save_build_hash
    fi
  else
    echo "✅ Using cached build (no changes detected)."
  fi

  # Start the server using 'serve' (now available as devDependency)
  header_message "Serving the production build on port $PORT"
  echo "🚀 Starting production server..."
  NO_UPDATE_NOTIFIER=1 npx serve -s build -l $PORT --no-clipboard
  if [ $? -eq 0 ]; then
    echo "✅ Production server started successfully on port $PORT."
  else
    echo "❌ Failed to start the production server. Please check the error messages above."
    exit 1
  fi
fi

# 7. Provide information on what the script is doing
header_message "Server Information"
if [ "$MODE" = "development" ]; then
  echo "🌐 The PixEagle dashboard is running in development mode on http://localhost:$PORT"
  echo "🌐 Development mode provides hot-reloading and detailed error messages."
else
  echo "🌐 The PixEagle dashboard is being served on http://localhost:$PORT"
  echo "🌐 Production mode serves the optimized build for better performance."
fi
echo "🌐 To access it from another device on the network, replace 'localhost' with your device's IP address."
echo "ℹ️  This dashboard provides a web interface for interacting with PixEagle, a system designed for UAV/UGV control and monitoring."
echo ""

# 8. Performance summary and end message
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

header_message "Dashboard Server Running"
echo "🎉 The server is now running and can be accessed via your browser."
echo "👉 Press Ctrl+C to stop the server at any time."
echo ""
echo "⚡ Performance Summary:"
echo "   Total startup time: ${TOTAL_TIME}s"
if [ "$MODE" = "production" ]; then
  if [ "$(needs_dependency_install)" = "false" ]; then
    echo "   Dependencies: ✅ Cache hit"
  else
    echo "   Dependencies: 🔄 Reinstalled"
  fi
  if [ "$FORCE_REBUILD" = "true" ]; then
    echo "   Build: 🔄 Force rebuild"
  elif [ "$(needs_build)" = "false" ]; then
    echo "   Build: ✅ Cache hit"
  else
    echo "   Build: 🔄 Rebuilt"
  fi
fi
