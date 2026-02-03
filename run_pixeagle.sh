#!/bin/bash

# ============================================================================
# run_pixeagle.sh - DEPRECATED: Use 'make run' or 'bash scripts/run.sh'
# ============================================================================
# This wrapper script is deprecated and will be removed in v6.0.
# Please update your workflow to use the new entry points.
#
# New usage:
#   make run                     (recommended - via Makefile)
#   make dev                     (development mode)
#   bash scripts/run.sh          (direct script invocation)
#   bash scripts/run.sh --dev    (development mode)
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

# Colors for warning message
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

echo ""
echo -e "${YELLOW}════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}   ⚠️  DEPRECATION WARNING${NC}"
echo -e "${YELLOW}════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "   ${BOLD}run_pixeagle.sh${NC} is deprecated and will be removed in v6.0"
echo ""
echo -e "   Please use one of these alternatives:"
echo -e "     ${CYAN}make run${NC}               (recommended)"
echo -e "     ${CYAN}make dev${NC}               (development mode)"
echo -e "     ${CYAN}bash scripts/run.sh${NC}    (direct)"
echo ""
echo -e "${YELLOW}════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "   Continuing in 3 seconds..."
sleep 3
echo ""

# Forward to the new script location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/run.sh" "$@"
