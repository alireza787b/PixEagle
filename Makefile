# ============================================================================
# PixEagle Makefile - Primary Entry Point
# ============================================================================
# Professional projects use Makefiles as the standard entry point.
# This works on Linux, macOS, and Windows (with make installed or via WSL).
#
# Usage:
#   make help    - Show available commands
#   make init    - Initialize PixEagle (first-time setup)
#   make run     - Run all services
#   make dev     - Run in development mode
#   make stop    - Stop all services
#
# For Windows without make, use:
#   scripts\init.bat
#   scripts\run.bat
# ============================================================================

.PHONY: help init run dev stop clean status logs download-binaries \
        service-install service-uninstall service-enable service-disable \
        service-status service-logs service-attach

# Default target
.DEFAULT_GOAL := help

# ============================================================================
# Help
# ============================================================================
help:
	@echo ""
	@echo "  PixEagle Commands"
	@echo "  ═══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "  Setup:"
	@echo "    make init              Initialize PixEagle (first-time setup)"
	@echo "    make download-binaries Download MAVSDK and MAVLink2REST binaries"
	@echo ""
	@echo "  Running:"
	@echo "    make run               Run all services (production mode)"
	@echo "    make dev               Run in development mode with hot-reload"
	@echo "    make stop              Stop all services"
	@echo ""
	@echo "  Monitoring:"
	@echo "    make status            Show service status"
	@echo "    make logs              Show service logs"
	@echo "    make attach            Attach to tmux session"
	@echo ""
	@echo "  Service Management (Linux/systemd):"
	@echo "    make service-install   Install pixeagle-service command"
	@echo "    make service-enable    Enable boot auto-start"
	@echo "    make service-disable   Disable boot auto-start"
	@echo "    make service-status    Show detailed service status"
	@echo "    make service-logs      Follow service logs"
	@echo "    make service-attach    Attach to service tmux session"
	@echo "    make service-uninstall Remove pixeagle-service + systemd unit"
	@echo ""
	@echo "  Maintenance:"
	@echo "    make clean             Clean build artifacts and caches"
	@echo "    make test              Run tests"
	@echo ""
	@echo "  Windows Users:"
	@echo "    Use scripts\\init.bat and scripts\\run.bat directly"
	@echo ""
	@echo "  ═══════════════════════════════════════════════════════════════"
	@echo ""

# ============================================================================
# Setup
# ============================================================================
init:
	@bash scripts/init.sh

download-binaries:
	@bash scripts/setup/download-binaries.sh --all

# ============================================================================
# Running
# ============================================================================
run:
	@bash scripts/run.sh

dev:
	@bash scripts/run.sh --dev

stop:
	@bash scripts/stop.sh

# ============================================================================
# Monitoring
# ============================================================================
status:
	@echo ""
	@echo "  PixEagle Service Status"
	@echo "  ═══════════════════════════════════════════════════════════════"
	@echo ""
	@tmux has-session -t pixeagle 2>/dev/null && echo "  Tmux session: Running" || echo "  Tmux session: Not running"
	@echo ""
	@echo "  Port Status:"
	@lsof -i :3000 >/dev/null 2>&1 && echo "    Dashboard (3000):     Running" || echo "    Dashboard (3000):     Not running"
	@lsof -i :5077 >/dev/null 2>&1 && echo "    Backend (5077):       Running" || echo "    Backend (5077):       Not running"
	@lsof -i :8088 >/dev/null 2>&1 && echo "    MAVLink2REST (8088):  Running" || echo "    MAVLink2REST (8088):  Not running"
	@lsof -i :5551 >/dev/null 2>&1 && echo "    WebSocket (5551):     Running" || echo "    WebSocket (5551):     Not running"
	@echo ""
	@echo "  ═══════════════════════════════════════════════════════════════"
	@echo ""

logs:
	@tmux has-session -t pixeagle 2>/dev/null && tmux attach -t pixeagle || echo "No active session. Start with: make run"

attach:
	@tmux has-session -t pixeagle 2>/dev/null && tmux attach -t pixeagle || echo "No active session. Start with: make run"

# ============================================================================
# Service Management (Linux/systemd)
# ============================================================================
service-install:
	@sudo bash scripts/service/install.sh

service-uninstall:
	@sudo bash scripts/service/install.sh uninstall

service-enable:
	@sudo pixeagle-service enable

service-disable:
	@sudo pixeagle-service disable

service-status:
	@pixeagle-service status

service-logs:
	@pixeagle-service logs -f

service-attach:
	@pixeagle-service attach

# ============================================================================
# Maintenance
# ============================================================================
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf dashboard/build dashboard/.pixeagle_cache
	@rm -rf __pycache__ src/__pycache__ src/**/__pycache__
	@rm -rf .pytest_cache
	@rm -rf opencv opencv_contrib
	@echo "Clean complete."

test:
	@source venv/bin/activate && python -m pytest tests/ -v

# ============================================================================
# Windows Targets (for nmake or similar)
# ============================================================================
init-win:
	@scripts\init.bat

run-win:
	@scripts\run.bat

dev-win:
	@scripts\run.bat --dev

stop-win:
	@scripts\stop.bat
