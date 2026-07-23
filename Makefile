# ============================================================================
# PixEagle Makefile - Primary Entry Point
# ============================================================================
# Professional projects use Makefiles as the standard entry point.
# The maintained guided/runtime path is Linux. Windows users may use WSL;
# native Windows helpers are legacy/experimental until their parity gates pass.
#
# Usage:
#   make help    - Show available commands
#   make init    - Initialize or resume PixEagle setup
#   make repair  - Verify and repair the current source without a Git update
#   make run     - Start the manual runtime
#   make dev     - Run in development mode
#   make stop    - Stop the manual runtime
#   make update  - Update source and reconcile the selected setup profile
#
# Windows users should use WSL for the maintained path. Native helpers are
# contributor-only experiments; review docs/WINDOWS_SETUP.md before opt-in.
# ============================================================================

.PHONY: help init repair setup-status demo run dev stop stop-legacy clean update reset-config setup-profile quick-browser-demo quick-browser-demo-cleanup \
        qgc-video-profile qgc-direct-media-profile demo-lan-browser-profile unsafe-demo-lan-media-profile production-remote-profile status logs \
        check-gstreamer-runtime managed-sih-doctor follower-contract-test \
        download-binaries binary-download-plan service-install service-uninstall service-enable \
        service-disable service-status service-logs service-attach phase0-check \
        sitl-dry-run sitl-probe sitl-sih-dry-run sitl-sih-probe \
        sitl-sih-execute-px4 sitl-gazebo-dry-run sitl-gazebo-probe \
        sitl-gazebo-execute-px4 video-udp-proof-dry-run video-udp-proof-execute \
        production-remote-browser-install production-remote-browser-e2e-dry-run \
        production-remote-browser-e2e

# Default target
.DEFAULT_GOAL := help

# Shared service ports
DASHBOARD_PORT ?= $(shell bash scripts/lib/ports.sh --dashboard-port "$(CURDIR)/dashboard" 2>/dev/null || echo 3040)
BACKEND_PORT ?= $(shell bash scripts/lib/ports.sh --backend-port "$(CURDIR)/configs/config.yaml" 2>/dev/null || echo 5077)
MAVLINK2REST_PORT ?= 8088
WEBSOCKET_PORT ?= 5551
PYTHON ?= $(if $(wildcard $(CURDIR)/.venv/bin/python),$(CURDIR)/.venv/bin/python,$(if $(wildcard $(CURDIR)/venv/bin/python),$(CURDIR)/venv/bin/python,python3))
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
	@echo "    make init              Initialize or resume PixEagle setup"
	@echo "    make repair            Reconcile current source after setup interruption/raw pull"
	@echo "    make setup-status      Show an active setup/update owner after reconnecting"
	@echo "    make download-binaries Download MAVSDK and MAVLink2REST binaries"
	@echo "    make binary-download-plan"
	@echo "                            Preview pinned binary URLs/checksums"
	@echo "    make setup-profile     Apply an explicit setup profile"
	@echo "    make qgc-video-profile Configure field QGC video (GCS_HOST=<ip>)"
	@echo "    make check-gstreamer-runtime"
	@echo "                            Verify OpenCV/GStreamer and QGC UDP prerequisites"
	@echo "    make managed-sih-doctor"
	@echo "                            Read-only managed PX4 SIH prerequisite check"
	@echo "    make qgc-direct-media-profile"
	@echo "                            Configure guarded HTTPS/WSS QGC direct media"
	@echo "    make demo-lan-browser-profile"
	@echo "                            Configure lab LAN dashboard (LAN_HOST=<this-host-ip>)"
	@echo "    make unsafe-demo-lan-media-profile"
	@echo "                            Configure anonymous lab-only media URLs"
	@echo "    make quick-browser-demo"
	@echo "                            Configure/start beginner browser demo (LAN_HOST=<ip>)"
	@echo "                            Enter keeps admin/admin; DEMO_CREDENTIAL_MODE=generated for random"
	@echo "    make quick-browser-demo-cleanup"
	@echo "                            Stop demo and remove demo credentials with CONFIRM=1"
	@echo "    make production-remote-profile"
	@echo "                            Configure loopback backend for TLS reverse proxy"
	@echo "                            Use CREDENTIAL_HANDOFF_FILE=<0600-json> in automation"
	@echo ""
	@echo "  Running:"
	@echo "    make demo              Start safe beginner video/follower test (no PX4)"
	@echo "    make run               Start the manual runtime (production mode)"
	@echo "    make dev               Run in development mode with hot-reload"
	@echo "    make stop              Stop the manual runtime"
	@echo ""
	@echo "  Monitoring:"
	@echo "    make status            Show manual runtime status"
	@echo "    make logs              Attach to live manual runtime output"
	@echo "    make attach            Attach to tmux session"
	@echo ""
	@echo "  Service Management (Linux/systemd):"
	@echo "    make service-install   Install controls (boot/runtime unchanged)"
	@echo "    pixeagle-service start Start the managed runtime now"
	@echo "    pixeagle-service stop  Stop the managed runtime now"
	@echo "    make service-enable    Enable boot auto-start"
	@echo "    make service-disable   Disable boot auto-start"
	@echo "    make service-status    Show detailed service status"
	@echo "    make service-logs      Follow service logs"
	@echo "    make service-attach    Attach to service tmux session"
	@echo "    make service-uninstall Remove pixeagle-service + systemd unit"
	@echo ""
	@echo "  Updates:"
	@echo "    make update            Normal path: fast-forward + reconcile dependencies/config"
	@echo "    make repair            After raw git pull: reconcile current source without fetching"
	@echo "                            Both require a stopped runtime and do not restart it"
	@echo "    make update SYNC_REMOTE=<remote> SYNC_BRANCH=<branch>"
	@echo "    pixeagle-service update [--remote <name> --branch <name>]"
	@echo "                            Same updater for a managed installation"
	@echo ""
	@echo "  Maintenance:"
	@echo "    make clean             Clean build artifacts and caches"
	@echo "    make reset-config      Reset config.yaml and dashboard/.env to defaults"
	@echo "    make test              Run tests"
	@echo "    make phase0-check      Run Phase 0 guardrails"
	@echo "    make follower-contract-test"
	@echo "                            Verify tracker-to-follower setpoint intent without PX4"
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
	@echo "    make production-remote-browser-e2e-dry-run"
	@echo "                            Validate the local HTTPS/browser evidence plan"
	@echo "    make production-remote-browser-install"
	@echo "                            Install Chromium and Linux dependencies for Playwright"
	@echo "    make production-remote-browser-e2e"
	@echo "                            Build dashboard and run local self-signed HTTPS E2E"
	@echo "                            Requires ALLOW_LOCAL_SELF_SIGNED_TLS=1"
	@echo ""
	@echo "  Windows Users:"
	@echo "    Use WSL for maintained setup. Native helpers are contributor-only"
	@echo "    experiments gated by PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1;"
	@echo "    review docs/WINDOWS_SETUP.md before opting in."
	@echo ""
	@echo "  ═══════════════════════════════════════════════════════════════"
	@echo ""

# ============================================================================
# Setup
# ============================================================================
init:
	@bash scripts/init.sh

setup-status:
	@bash -c 'source scripts/lib/common.sh; source scripts/lib/setup_lock.sh; venv="$$(resolve_pixeagle_venv_dir "$(CURDIR)")"; pixeagle_setup_lock_status "$$venv"'

repair:
	@PIXEAGLE_SETUP_ACTION=repair bash scripts/init.sh

download-binaries:
	@bash scripts/setup/download-binaries.sh --all

binary-download-plan:
	@bash scripts/setup/download-binaries.sh --all --dry-run

PROFILE ?= local_dev
SETUP_PROFILE_ARGS ?=
setup-profile:
	@$(PYTHON) scripts/setup/apply-setup-profile.py --profile "$(PROFILE)" $(SETUP_PROFILE_ARGS)

qgc-video-profile:
	@if [ -z "$(GCS_HOST)" ]; then \
		echo "Usage: make qgc-video-profile GCS_HOST=<ground-station-ip> [GSTREAMER_PORT=5600]"; \
		exit 2; \
	fi
	@$(PYTHON) scripts/setup/apply-setup-profile.py --profile field_qgc_video --gcs-host "$(GCS_HOST)" $(if $(GSTREAMER_PORT),--gstreamer-port "$(GSTREAMER_PORT)")

check-gstreamer-runtime:
	@bash scripts/setup/check-gstreamer-runtime.sh

managed-sih-doctor:
	@$(PYTHON) scripts/setup/check-managed-sih.py

qgc-direct-media-profile:
	@if [ -z "$(PUBLIC_HOST)" ]; then \
		echo "Usage: make qgc-direct-media-profile PUBLIC_HOST=<tls-hostname-or-stable-ip> [PUBLIC_ORIGIN=https://host] [QGC_TOKEN_FILE=<0600-json>] [QGC_HANDOFF_FILE=<0600-json>]"; \
		exit 2; \
	fi
	@$(PYTHON) scripts/setup/apply-setup-profile.py --profile qgc_direct_media --public-host "$(PUBLIC_HOST)" $(if $(PUBLIC_ORIGIN),--public-origin "$(PUBLIC_ORIGIN)") $(if $(QGC_TOKEN_FILE),--bearer-token-file "$(QGC_TOKEN_FILE)") $(if $(QGC_HANDOFF_FILE),--qgc-handoff-file "$(QGC_HANDOFF_FILE)") $(if $(QGC_TOKEN_ID),--token-id "$(QGC_TOKEN_ID)") $(if $(QGC_TOKEN_SUBJECT),--token-subject "$(QGC_TOKEN_SUBJECT)") $(if $(filter 1 true TRUE yes YES on ON,$(ROTATE_QGC_TOKEN)),--rotate-qgc-token) $(SETUP_PROFILE_ARGS)

demo-lan-browser-profile:
	@if [ -z "$(LAN_HOST)" ]; then \
		echo "Usage: make demo-lan-browser-profile LAN_HOST=<this-pixeagle-lan-ip-or-hostname>"; \
		exit 2; \
	fi
	@$(PYTHON) scripts/setup/apply-setup-profile.py --profile demo_lan_browser --lan-host "$(LAN_HOST)" $(if $(SESSION_USERNAME),--session-username "$(SESSION_USERNAME)") $(if $(SESSION_ROLE),--session-role "$(SESSION_ROLE)") $(if $(DEMO_USERNAME),--demo-username "$(DEMO_USERNAME)") $(if $(DEMO_ROLE),--demo-role "$(DEMO_ROLE)") $(if $(DEMO_CREDENTIAL_MODE),--demo-credential-mode "$(DEMO_CREDENTIAL_MODE)") $(if $(ROTATE_DEMO_CREDENTIALS),--rotate-demo-credentials) $(if $(ROTATE_SESSION_CREDENTIALS),--rotate-session-credentials) $(SETUP_PROFILE_ARGS)

unsafe-demo-lan-media-profile:
	@if [ -z "$(LAN_HOST)" ]; then \
		echo "Usage: make unsafe-demo-lan-media-profile LAN_HOST=<this-pixeagle-lan-ip-or-hostname>"; \
		echo "For a temporary public HTTP bench only, add SETUP_PROFILE_ARGS=--allow-public-http-demo"; \
		exit 2; \
	fi
	@$(PYTHON) scripts/setup/apply-setup-profile.py --profile unsafe_demo_lan_media_only --lan-host "$(LAN_HOST)" $(SETUP_PROFILE_ARGS)

quick-browser-demo:
	@LAN_HOST="$(LAN_HOST)" \
	ALLOW_PUBLIC_HTTP_DEMO="$(ALLOW_PUBLIC_HTTP_DEMO)" \
	OPEN_FIREWALL="$(OPEN_FIREWALL)" \
	TRUSTED_CIDR="$(TRUSTED_CIDR)" \
	START_DEMO="$(START_DEMO)" \
	ROTATE_DEMO_CREDENTIALS="$(if $(ROTATE_DEMO_CREDENTIALS),$(ROTATE_DEMO_CREDENTIALS),1)" \
	SESSION_USER_FILE="$(SESSION_USER_FILE)" \
	CREDENTIAL_HANDOFF_FILE="$(CREDENTIAL_HANDOFF_FILE)" \
	DEMO_USERNAME="$(DEMO_USERNAME)" \
	DEMO_ROLE="$(DEMO_ROLE)" \
	DEMO_CREDENTIAL_MODE="$(DEMO_CREDENTIAL_MODE)" \
	DASHBOARD_PORT="$(DASHBOARD_PORT)" \
	HTTP_STREAM_PORT="$(BACKEND_PORT)" \
	DRY_RUN="$(DRY_RUN)" \
	PYTHON="$(PYTHON)" \
	bash scripts/setup/quick-browser-demo.sh

quick-browser-demo-cleanup:
	@LAN_HOST="$(LAN_HOST)" \
	TRUSTED_CIDR="$(TRUSTED_CIDR)" \
	CLOSE_FIREWALL="$(CLOSE_FIREWALL)" \
	STOP_DEMO="$(STOP_DEMO)" \
	REMOVE_DEMO_CREDENTIALS="$(REMOVE_DEMO_CREDENTIALS)" \
	REMOVE_DEMO_BACKUPS="$(REMOVE_DEMO_BACKUPS)" \
	RESTORE_LOCAL_PROFILE="$(RESTORE_LOCAL_PROFILE)" \
	ALLOW_BROAD_FIREWALL_CLEANUP="$(ALLOW_BROAD_FIREWALL_CLEANUP)" \
	SESSION_USER_FILE="$(SESSION_USER_FILE)" \
	CREDENTIAL_HANDOFF_FILE="$(CREDENTIAL_HANDOFF_FILE)" \
	DASHBOARD_PORT="$(DASHBOARD_PORT)" \
	HTTP_STREAM_PORT="$(BACKEND_PORT)" \
	DRY_RUN="$(DRY_RUN)" \
	CONFIRM="$(CONFIRM)" \
	PYTHON="$(PYTHON)" \
	bash scripts/setup/quick-browser-demo-cleanup.sh

production-remote-profile:
	@if [ -z "$(PUBLIC_HOST)" ] || [ -z "$(SESSION_USER_FILE)" ]; then \
		echo "Usage: make production-remote-profile PUBLIC_HOST=<tls-hostname-or-stable-ip> SESSION_USER_FILE=<deployment-user-json> [PUBLIC_ORIGIN=https://host] [CREDENTIAL_HANDOFF_FILE=<0600-json>]"; \
		exit 2; \
	fi
	@$(PYTHON) scripts/setup/apply-setup-profile.py --profile production_remote --public-host "$(PUBLIC_HOST)" --session-user-file "$(SESSION_USER_FILE)" $(if $(PUBLIC_ORIGIN),--public-origin "$(PUBLIC_ORIGIN)") $(if $(CREDENTIAL_HANDOFF_FILE),--credential-handoff-file "$(CREDENTIAL_HANDOFF_FILE)") $(if $(SHOW_GENERATED_PASSWORD),--show-generated-password) $(if $(SESSION_USERNAME),--session-username "$(SESSION_USERNAME)") $(if $(SESSION_ROLE),--session-role "$(SESSION_ROLE)") $(if $(ROTATE_SESSION_CREDENTIALS),--rotate-session-credentials) $(SETUP_PROFILE_ARGS)

# ============================================================================
# Running
# ============================================================================
demo:
	@DRY_RUN="$(DRY_RUN)" PYTHON="$(PYTHON)" bash scripts/setup/run-beginner-demo.sh

run:
	@bash scripts/run.sh

dev:
	@bash scripts/run.sh --dev

stop:
	@bash scripts/stop.sh

stop-legacy:
	@bash scripts/stop.sh --legacy-default-session

# ============================================================================
# Monitoring
# ============================================================================
status:
	@bash scripts/runtime-control.sh status

logs:
	@bash scripts/runtime-control.sh attach

attach:
	@bash scripts/runtime-control.sh attach

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
# Override these to update from a different remote or branch:
#   make update SYNC_REMOTE=upstream SYNC_BRANCH=develop
# Defaults: auto-detect from git config (works with both SSH and HTTPS remotes)
SYNC_REMOTE ?=
SYNC_BRANCH ?=

update:
	@SYNC_REMOTE="$(SYNC_REMOTE)" SYNC_BRANCH="$(SYNC_BRANCH)" bash scripts/update.sh

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
	@echo "Clean complete."

test:
	@PYTHONPATH=src $(PYTHON) -m pytest tests/ -ra --tb=short -m "not sitl and not px4 and not e2e and not hardware and not manual" --strict-config

phase0-check:
	@PYTHON="$(PYTHON)" bash scripts/check_schema.sh
	@$(PYTHON) tools/generate_api_tool_candidates.py --check
	@bash -n install.sh
	@bash -n scripts/init.sh
	@bash -n scripts/run.sh
	@bash -n scripts/stop.sh
	@find scripts -name '*.sh' -print0 | xargs -0 -n1 bash -n
	@PYTHONPATH=src $(PYTHON) -m pytest tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py tests/test_test_hygiene.py tests/test_docs_infrastructure_consistency.py tests/test_setup_profiles.py tests/test_binary_download_policy.py tests/test_production_remote_browser_e2e.py tests/unit/core_app/test_api_auth_runtime.py tests/unit/core_app/test_api_exposure_policy.py tests/unit/core_app/test_api_v1_streams.py tests/unit/core_app/test_config_clean_clone.py tests/unit/core_app/test_parameters_reload.py -ra --tb=short --strict-config

follower-contract-test:
	@PYTHONPATH=src $(PYTHON) -m pytest tests/unit/trackers/test_tracker_in_loop_validation.py -ra --tb=short --strict-config

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

production-remote-browser-install:
	@cd dashboard && npx playwright install --with-deps chromium

production-remote-browser-e2e-dry-run:
	@$(PYTHON) tools/run_production_remote_browser_e2e.py --json

production-remote-browser-e2e:
	@if [ "$(ALLOW_LOCAL_SELF_SIGNED_TLS)" != "1" ]; then \
		echo "Refusing local browser execution without ALLOW_LOCAL_SELF_SIGNED_TLS=1"; \
		exit 2; \
	fi
	@$(PYTHON) tools/run_production_remote_browser_e2e.py --execute-browser --allow-local-self-signed-tls --json

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
