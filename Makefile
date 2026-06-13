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
#   make sync    - Pull latest changes from upstream
#
# For Windows without make, use:
#   scripts\init.bat
#   scripts\run.bat
# ============================================================================

.PHONY: help init run dev stop clean sync update reset-config status logs \
        download-binaries service-install service-uninstall service-enable \
        service-disable service-status service-logs service-attach phase0-check \
        sitl-dry-run sitl-probe sitl-sih-dry-run sitl-sih-probe \
        sitl-sih-execute-px4 sitl-gazebo-dry-run sitl-gazebo-probe \
        sitl-gazebo-execute-px4 video-udp-proof-dry-run video-udp-proof-execute

# Default target
.DEFAULT_GOAL := help

# Shared service ports
DASHBOARD_PORT ?= $(shell bash scripts/lib/ports.sh --dashboard-port "$(CURDIR)/dashboard" 2>/dev/null || echo 3040)
BACKEND_PORT ?= $(shell bash scripts/lib/ports.sh --backend-port "$(CURDIR)/configs/config.yaml" 2>/dev/null || echo 5077)
MAVLINK2REST_PORT ?= 8088
WEBSOCKET_PORT ?= 5551
PYTHON ?= python3
VIDEO_PROOF_PYTHON ?= python3

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
	@echo "  Updates:"
	@echo "    make sync              Pull latest changes from upstream safely"
	@echo "    make update            Alias for sync"
	@echo "    Options: SYNC_REMOTE=<remote> SYNC_BRANCH=<branch>"
	@echo ""
	@echo "  Maintenance:"
	@echo "    make clean             Clean build artifacts and caches"
	@echo "    make reset-config      Reset config.yaml and dashboard/.env to defaults"
	@echo "    make test              Run tests"
	@echo "    make phase0-check      Run Phase 0 guardrails"
	@echo "    make sitl-dry-run      Validate the PX4/SITL plan without side effects"
	@echo "    make sitl-probe        Probe an already running PX4/SITL stack"
	@echo "    make sitl-sih-dry-run  Validate the official PX4 SIH profile without side effects"
	@echo "    make sitl-sih-probe    Probe an already running PX4 SIH stack"
	@echo "    make sitl-sih-execute-px4"
	@echo "                            Start only the guarded PX4 SIH container and collect evidence"
	@echo "    make sitl-gazebo-dry-run"
	@echo "                            Validate the official PX4 Gazebo visual profile without side effects"
	@echo "    make sitl-gazebo-probe"
	@echo "                            Probe an already running official PX4 Gazebo visual stack"
	@echo "    make sitl-gazebo-execute-px4"
	@echo "                            Start only the guarded official PX4 Gazebo container"
	@echo "    make video-udp-proof-dry-run"
	@echo "                            Validate generated RTP/UDP receiver contract without side effects"
	@echo "    make video-udp-proof-execute"
	@echo "                            Start only a local generated RTP/UDP sender and collect video evidence"
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
	@lsof -i :$(DASHBOARD_PORT) >/dev/null 2>&1 && echo "    Dashboard ($(DASHBOARD_PORT)):     Running" || echo "    Dashboard ($(DASHBOARD_PORT)):     Not running"
	@lsof -i :$(BACKEND_PORT) >/dev/null 2>&1 && echo "    Backend ($(BACKEND_PORT)):       Running" || echo "    Backend ($(BACKEND_PORT)):       Not running"
	@lsof -i :$(MAVLINK2REST_PORT) >/dev/null 2>&1 && echo "    MAVLink2REST ($(MAVLINK2REST_PORT)):  Running" || echo "    MAVLink2REST ($(MAVLINK2REST_PORT)):  Not running"
	@lsof -i :$(WEBSOCKET_PORT) >/dev/null 2>&1 && echo "    WebSocket ($(WEBSOCKET_PORT)):     Running" || echo "    WebSocket ($(WEBSOCKET_PORT)):     Not running"
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
# Updates
# ============================================================================
# Override these to sync from a different remote or branch:
#   make sync SYNC_REMOTE=upstream SYNC_BRANCH=develop
# Defaults: auto-detect from git config (works with both SSH and HTTPS remotes)
SYNC_REMOTE ?=
SYNC_BRANCH ?=

sync:
	@SYNC_REMOTE="$(SYNC_REMOTE)" SYNC_BRANCH="$(SYNC_BRANCH)" bash scripts/lib/sync.sh

update: sync

sync-restart:
	@bash scripts/service/sync_and_restart.sh

# ============================================================================
# Maintenance
# ============================================================================
reset-config:
	@bash scripts/lib/reset-config.sh

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf dashboard/build dashboard/.pixeagle_cache
	@rm -rf __pycache__ src/__pycache__ src/**/__pycache__
	@rm -rf .pytest_cache
	@rm -rf opencv opencv_contrib
	@echo "Clean complete."

test:
	@PYTHONPATH=src $(PYTHON) -m pytest tests/ -ra --tb=short -m "not sitl and not px4 and not e2e and not hardware and not manual" --strict-config

phase0-check:
	@bash scripts/check_schema.sh
	@$(PYTHON) tools/generate_api_tool_candidates.py --check
	@bash -n install.sh
	@bash -n scripts/init.sh
	@bash -n scripts/run.sh
	@bash -n scripts/stop.sh
	@find scripts -name '*.sh' -print0 | xargs -0 -n1 bash -n
	@PYTHONPATH=src $(PYTHON) -m pytest tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py tests/test_test_hygiene.py tests/test_docs_infrastructure_consistency.py tests/unit/core_app/test_config_clean_clone.py tests/unit/core_app/test_parameters_reload.py -ra --tb=short --strict-config

sitl-dry-run:
	@$(PYTHON) tools/run_sitl_validation_suite.py --plan-name phase2_follower_validation --dry-run

sitl-probe:
	@$(PYTHON) tools/run_sitl_validation_suite.py --plan-name phase2_follower_validation --probe-only --artifact-root reports/sitl

sitl-sih-dry-run:
	@PYTHON_BIN="$(PYTHON)" bash scripts/sitl/run_px4_sih_profile.sh --mode dry-run --json

sitl-sih-probe:
	@PYTHON_BIN="$(PYTHON)" bash scripts/sitl/run_px4_sih_profile.sh --mode probe-only --artifact-root reports/sitl

sitl-sih-execute-px4:
	@PYTHON_BIN="$(PYTHON)" bash scripts/sitl/run_px4_sih_profile.sh --mode execute-px4 --artifact-root reports/sitl

sitl-gazebo-dry-run:
	@PYTHON_BIN="$(PYTHON)" bash scripts/sitl/run_px4_gazebo_visual_profile.sh --mode dry-run --json

sitl-gazebo-probe:
	@PYTHON_BIN="$(PYTHON)" bash scripts/sitl/run_px4_gazebo_visual_profile.sh --mode probe-only --artifact-root reports/sitl

sitl-gazebo-execute-px4:
	@PYTHON_BIN="$(PYTHON)" bash scripts/sitl/run_px4_gazebo_visual_profile.sh --mode execute-gazebo --artifact-root reports/sitl

video-udp-proof-dry-run:
	@$(PYTHON) tools/run_udp_video_receiver_proof.py --dry-run --json

video-udp-proof-execute:
	@$(VIDEO_PROOF_PYTHON) tools/run_udp_video_receiver_proof.py --execute --allow-process-start --artifact-root reports/video --json

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
