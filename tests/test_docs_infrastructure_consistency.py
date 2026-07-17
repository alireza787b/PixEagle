import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CRITICAL_DOCS = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "docs" / "README.md",
    PROJECT_ROOT / "docs" / "INSTALLATION.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "README.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "mavlink-anywhere.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "mavlink-router.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "port-configuration.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "05-configuration" / "px4-config.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "05-configuration" / "mavlink-config.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "05-configuration" / "safety-integration.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "03-protocols" / "mavlink2rest-api.md",
]

SECONDARY_DRONE_INTERFACE_DOCS = [
    PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "sitl-setup.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "hardware-connection.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "companion-computer.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "06-development" / "adding-control-types.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "06-development" / "custom-telemetry.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "06-development" / "testing-without-drone.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "07-troubleshooting" / "connection-issues.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "07-troubleshooting" / "telemetry-gaps.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "07-troubleshooting" / "offboard-mode.md",
]

ACTIVE_RUNTIME_DOCS = [
    PROJECT_ROOT / "docs" / "OSD_GUIDE.md",
    PROJECT_ROOT / "docs" / "developers" / "SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md",
    PROJECT_ROOT / "docs" / "gimbal_simulator.md",
    PROJECT_ROOT / "docs" / "core-app" / "README.md",
    PROJECT_ROOT / "docs" / "core-app" / "02-components" / "app-controller.md",
    PROJECT_ROOT / "docs" / "core-app" / "02-components" / "config-service.md",
    PROJECT_ROOT / "docs" / "core-app" / "02-components" / "fastapi-handler.md",
    PROJECT_ROOT / "docs" / "core-app" / "02-components" / "flow-controller.md",
    PROJECT_ROOT / "docs" / "core-app" / "02-components" / "logging-manager.md",
    PROJECT_ROOT / "docs" / "core-app" / "02-components" / "schema-manager.md",
    PROJECT_ROOT / "docs" / "core-app" / "02-components" / "tracking-state-manager.md",
    PROJECT_ROOT / "docs" / "core-app" / "03-api" / "README.md",
    PROJECT_ROOT / "docs" / "core-app" / "04-configuration" / "README.md",
    PROJECT_ROOT / "docs" / "core-app" / "05-development" / "README.md",
    PROJECT_ROOT / "docs" / "video" / "01-architecture" / "video-handler.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "README.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "http-mjpeg.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "qgc-http-websocket-source-plan.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "remote-media-security.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "websocket.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "webrtc.md",
    PROJECT_ROOT / "docs" / "video" / "06-configuration" / "streaming-config.md",
    PROJECT_ROOT / "docs" / "trackers" / "02-reference" / "README.md",
    PROJECT_ROOT / "docs" / "trackers" / "02-reference" / "gimbal-tracker.md",
    PROJECT_ROOT / "docs" / "trackers" / "04-configuration" / "parameter-reference.md",
    PROJECT_ROOT / "docs" / "trackers" / "04-configuration" / "tuning-guide.md",
    PROJECT_ROOT / "docs" / "trackers" / "06-integration" / "README.md",
    PROJECT_ROOT / "docs" / "trackers" / "06-integration" / "external-systems.md",
]

ACTIVE_TRACKER_DOCS = sorted((PROJECT_ROOT / "docs" / "trackers").rglob("*.md"))
TRACKER_STALE_CONFIG_PATTERNS = [
    re.compile(r"(?<!DEFAULT_)\bTRACKING_ALGORITHM\b"),
    re.compile(r"\bENABLE_SMART_TRACKER\b"),
    re.compile(r"\bSMART_TRACKER_COLOR\b"),
    re.compile(r"\bSMART_TRACKER_HUD_STYLE\b"),
]

STALE_PATTERNS = [
    re.compile(r"MAVLink2REST \(also known as mavlink-anywhere\)"),
    re.compile(r"Docker \(Recommended\)"),
    re.compile(r"bash scripts/run\.sh -d\s+# Skip dashboard"),
    re.compile(r"python main\.py"),
    re.compile(r"localhost:8000"),
    re.compile(r"Port = 14541"),
    re.compile(r"Port = 14551"),
    re.compile(r"udpin:0\.0\.0\.0:14551"),
    re.compile(r"connection_string:"),
    re.compile(r"^px4:", re.MULTILINE),
    re.compile(r"^mavlink2rest:", re.MULTILINE),
    re.compile(r"^circuit_breaker:", re.MULTILINE),
]

SECONDARY_STALE_PATTERNS = [
    re.compile(r"\b14541\b"),
    re.compile(r"\b14551\b"),
    re.compile(r"localhost:8000"),
    re.compile(r"python main\.py"),
    re.compile(r"github\.com/yourusername"),
    re.compile(r"requirements-jetson\.txt"),
    re.compile(r"udpin:0\.0\.0\.0:14551"),
    re.compile(r"--server 0\.0\.0\.0:8088"),
    re.compile(r"(?<!/v1)/mavlink/vehicles"),
    re.compile(r"connection_string:"),
    re.compile(r"^\s*px4:", re.MULTILINE),
    re.compile(r"^\s*mavlink2rest:", re.MULTILINE),
    re.compile(r"^\s*circuit_breaker:", re.MULTILINE),
    re.compile(r"^\s*safety:", re.MULTILINE),
    re.compile(r"/api/status/circuit_breaker"),
    re.compile(r"/api/circuit_breaker"),
    re.compile(r"/api/telemetry/status"),
    re.compile(r"/api/debug/mavlink_manager"),
    re.compile(r"/api/mavlink/restart_polling"),
    re.compile(r"/api/follower/current_setpoints"),
    re.compile(r"/api/follower/commands"),
]

ACTIVE_RUNTIME_STALE_PATTERNS = [
    re.compile(r"localhost:8000"),
    re.compile(r"localhost:5000"),
    re.compile(r"\brun_pixeagle\.sh\b"),
    re.compile(r"\bpython main\.py\b"),
    re.compile(r"^\s*http:\s*$", re.MULTILINE),
    re.compile(r"^\s*port:\s*8000\b", re.MULTILINE),
    re.compile(r"GIMBAL_UDP_HOST"),
    re.compile(r"GIMBAL_UDP_PORT"),
    re.compile(r"GIMBAL_CONTROL_PORT"),
    re.compile(r"GIMBAL_LISTEN_PORT"),
    re.compile(r"GIMBAL_COORDINATE_SYSTEM"),
    re.compile(r"GIMBAL_DISABLE_ESTIMATOR"),
    re.compile(r"Session Initiation Protocol"),
    re.compile(r"Gimbal UDP Passive"),
    re.compile(r"passive_monitoring"),
    re.compile(r"JSON over UDP"),
]

VIDEO_STREAMING_CONFIG_DOCS = [
    PROJECT_ROOT / "docs" / "video" / "03-gstreamer" / "README.md",
    PROJECT_ROOT / "docs" / "video" / "03-gstreamer" / "output-pipeline.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "README.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "http-mjpeg.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "qgc-http-websocket-source-plan.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "remote-media-security.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "streaming-optimizer.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "websocket.md",
    PROJECT_ROOT / "docs" / "video" / "06-configuration" / "README.md",
    PROJECT_ROOT / "docs" / "video" / "06-configuration" / "streaming-config.md",
]

VIDEO_STREAMING_STALE_CONFIG_PATTERNS = [
    re.compile(r"^\s*FastAPI:\s*$", re.MULTILINE),
    re.compile(r"\bENABLE_HTTP_STREAM\b"),
    re.compile(r"\bENABLE_WEBSOCKET\b"),
    re.compile(r"\bENABLE_WEBRTC\b"),
    re.compile(r"\bMJPEG_BOUNDARY\b"),
    re.compile(r"\bWS_PING_INTERVAL\b"),
    re.compile(r"\bWS_MAX_CLIENTS\b"),
    re.compile(r"\bWS_FRAME_RATE\b"),
    re.compile(r"\bWS_QUALITY\b"),
    re.compile(r"\bMAX_CLIENTS\b"),
    re.compile(r"\bENABLE_OPTIMIZER\b"),
    re.compile(r"\bQUALITY_LEVELS\b"),
    re.compile(r"\bTARGET_BITRATE\b"),
    re.compile(r"\bDEST_HOST\b"),
    re.compile(r"\bDEST_PORT\b"),
    re.compile(r"\bUSE_HARDWARE_ENCODER\b"),
    re.compile(r"\bENCODER_PRESET\b"),
    re.compile(r"\bKEYFRAME_INTERVAL\b"),
    re.compile(r"GStreamer:\n\s+ENABLE:\s*true"),
    re.compile(r"/video_feed\?(?:quality|resize|osd)="),
]

VIDEO_OSD_CONFIG_DOCS = [
    PROJECT_ROOT / "docs" / "video" / "05-osd" / "README.md",
    PROJECT_ROOT / "docs" / "video" / "05-osd" / "osd-renderer.md",
    PROJECT_ROOT / "docs" / "video" / "06-configuration" / "streaming-config.md",
]

VIDEO_OSD_STALE_CONFIG_PATTERNS = [
    re.compile(r"OSD:\n\s+ENABLE:\s*", re.MULTILINE),
]

PXE0030_TIMING_DOCS = [
    PROJECT_ROOT / "docs" / "drone-interface" / "README.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "01-architecture" / "README.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "01-architecture" / "data-flow.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "02-components" / "setpoint-sender.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "02-components" / "px4-interface-manager.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "03-protocols" / "mavsdk-offboard.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "05-configuration" / "px4-config.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "07-troubleshooting" / "offboard-mode.md",
    PROJECT_ROOT / "docs" / "followers" / "01-architecture" / "README.md",
    PROJECT_ROOT / "docs" / "followers" / "01-architecture" / "base-follower.md",
    PROJECT_ROOT / "docs" / "followers" / "05-development" / "creating-followers.md",
    PROJECT_ROOT / "docs" / "followers" / "05-development" / "testing-followers.md",
    PROJECT_ROOT / "docs" / "followers" / "07-integration" / "README.md",
    PROJECT_ROOT / "docs" / "followers" / "07-integration" / "mavlink-integration.md",
    PROJECT_ROOT / "docs" / "followers" / "07-integration" / "tracker-integration.md",
]

PXE0030_STALE_TIMING_PATTERNS = [
    re.compile(r"Threaded command publishing"),
    re.compile(r"SETPOINT_PUBLISH_RATE_S:\s*0\.05\s*#\s*20\s*Hz"),
    re.compile(r"SetpointSender[^\n]*continuously sends", re.IGNORECASE),
    re.compile(r"Command sending\s*\|\s*20\s*Hz", re.IGNORECASE),
    re.compile(r"Follow target loop\s*\|\s*~20\s*Hz", re.IGNORECASE),
    re.compile(r"SETPOINT_PUBLISH_RATE_S[^\n]*command send rate", re.IGNORECASE),
    re.compile(r"Runs at ~20 Hz"),
    re.compile(r"PixEagle default:\s*20\s*Hz"),
    re.compile(r"PX4 Commands\s*\|\s*20\s*Hz"),
    re.compile(r"asyncio\.sleep\(0\.05\)\s*#\s*20\s*Hz"),
]

PXE0033_SAFETY_DOCS = [
    PROJECT_ROOT / "docs" / "drone-interface" / "02-components" / "px4-interface-manager.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "02-components" / "setpoint-handler.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "05-configuration" / "safety-integration.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "06-development" / "testing-without-drone.md",
    PROJECT_ROOT / "docs" / "followers" / "01-architecture" / "setpoint-handler.md",
    PROJECT_ROOT / "docs" / "followers" / "06-safety" / "safety-manager.md",
]

PXE0033_STALE_SAFETY_PATTERNS = [
    re.compile(r"Allow if circuit breaker unavailable", re.IGNORECASE),
    re.compile(r"circuit breaker unavailable\s*-\s*allow", re.IGNORECASE),
    re.compile(r"'pitchspeed_deg_s':\s*'MAX_YAW_RATE'"),
    re.compile(r"'rollspeed_deg_s':\s*'MAX_YAW_RATE'"),
    re.compile(r"Parameters\.SafetyLimits"),
    re.compile(r"Indoor testing without risk", re.IGNORECASE),
    re.compile(r"action\.terminate\("),
]

PXE0034_COMMAND_INTENT_DOCS = [
    PROJECT_ROOT / "docs" / "developers" / "SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md",
    PROJECT_ROOT / "docs" / "followers" / "README.md",
    PROJECT_ROOT / "docs" / "followers" / "02-reference" / "README.md",
    PROJECT_ROOT / "docs" / "followers" / "07-integration" / "README.md",
    PROJECT_ROOT / "docs" / "followers" / "01-architecture" / "base-follower.md",
    PROJECT_ROOT / "docs" / "followers" / "01-architecture" / "setpoint-handler.md",
    PROJECT_ROOT / "docs" / "followers" / "05-development" / "creating-followers.md",
    PROJECT_ROOT / "docs" / "followers" / "05-development" / "best-practices.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "02-components" / "setpoint-handler.md",
]

PXE0034_STALE_COMMAND_INTENT_PATTERNS = [
    re.compile(r"\b(?:self|follower|handler)\.set_command_field\("),
]

PXE0034_STALE_SETPOINT_MUTATION_PATTERNS = [
    re.compile(r"\b(?:self|handler|setpoint_handler)\.set_field\("),
    re.compile(r"\bpx4\.setpoint_handler\.set_field\("),
]

PXE0007_OFFBOARD_COMMANDER_DOCS = [
    PROJECT_ROOT / "docs" / "drone-interface" / "README.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "01-architecture" / "README.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "01-architecture" / "data-flow.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "02-components" / "offboard-commander.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "02-components" / "setpoint-sender.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "03-protocols" / "mavsdk-offboard.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "05-configuration" / "px4-config.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "07-troubleshooting" / "offboard-mode.md",
    PROJECT_ROOT / "docs" / "followers" / "07-integration" / "README.md",
    PROJECT_ROOT / "docs" / "followers" / "07-integration" / "mavlink-integration.md",
]

PXE0007_STALE_OFFBOARD_PATTERNS = [
    re.compile(r"current command dispatch source is `AppController\.follow_target\(\)`"),
    re.compile(r"Current MAVSDK dispatch source", re.IGNORECASE),
    re.compile(r"AppController\.follow_target\(\)[^\n]*MAVSDK", re.IGNORECASE),
    re.compile(r"frame/tracker loop coupled", re.IGNORECASE),
    re.compile(r"future commander", re.IGNORECASE),
    re.compile(r"future Offboard commander", re.IGNORECASE),
    re.compile(r"Recommended future Offboard commander", re.IGNORECASE),
    re.compile(r"PXE-0007 tracks the dedicated Offboard commander", re.IGNORECASE),
    re.compile(r"does not provide an independent MAVSDK\s+Offboard heartbeat", re.IGNORECASE),
    re.compile(r"no independent fixed-rate Offboard heartbeat", re.IGNORECASE),
    re.compile(r"\bPX4Controller\b"),
]

PXE0014_MAVLINK_FRESHNESS_DOCS = [
    PROJECT_ROOT / "docs" / "core-app" / "03-api" / "README.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "02-components" / "mavlink-data-manager.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "05-configuration" / "mavlink-config.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "07-troubleshooting" / "telemetry-gaps.md",
]

PXE0014_STALE_MAVLINK_PATTERNS = [
    re.compile(r"current polling timeout is code-level", re.IGNORECASE),
    re.compile(r"exposing retry and\s+timeout .*tracked", re.IGNORECASE | re.DOTALL),
]

COMPANION_RUNTIME_CONTRACT = (
    PROJECT_ROOT / "docs" / "architecture" / "companion-runtime-contract.md"
)
MAVLINK_ANYWHERE_DOC = (
    PROJECT_ROOT
    / "docs"
    / "drone-interface"
    / "04-infrastructure"
    / "mavlink-anywhere.md"
)
PIXEAGLE_EXPOSURE_DOCS = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "docs" / "INSTALLATION.md",
    PROJECT_ROOT / "docs" / "CONFIGURATION.md",
    PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md",
    PROJECT_ROOT / "docs" / "WINDOWS_SETUP.md",
    PROJECT_ROOT / "docs" / "WINDOWS_SITL_XPLANE.md",
    PROJECT_ROOT / "docs" / "apis" / "api-exposure-boundary.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "companion-computer.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "port-configuration.md",
    PROJECT_ROOT / "docs" / "drone-interface" / "07-troubleshooting" / "connection-issues.md",
]

SETUP_PROFILE_DOCS_AND_SCRIPTS = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "docs" / "README.md",
    PROJECT_ROOT / "docs" / "INSTALLATION.md",
    PROJECT_ROOT / "docs" / "CONFIGURATION.md",
    PROJECT_ROOT / "docs" / "WINDOWS_SETUP.md",
    PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md",
    PROJECT_ROOT / "docs" / "setup" / "setup-profiles.md",
    PROJECT_ROOT / "install.sh",
    PROJECT_ROOT / "install.ps1",
    PROJECT_ROOT / "scripts" / "init.sh",
    PROJECT_ROOT / "scripts" / "init.bat",
    PROJECT_ROOT / "Makefile",
]

PXE0068_STALE_SETUP_PATTERNS = [
    re.compile(r"Generates config\.yaml", re.IGNORECASE),
    re.compile(r"Created configs[\\/]+config\.yaml", re.IGNORECASE),
    re.compile(r"Edit\s+[`%A-Za-z{}$\\/-]*configs[\\/]+config\.yaml.*for your setup", re.IGNORECASE),
    re.compile(r"accept the guided defaults", re.IGNORECASE),
    re.compile(r"Install pixeagle-service command now\? \[Y/n\]"),
    re.compile(r"Enable auto-start on every boot now\? \[Y/n\]"),
    re.compile(r"Start PixEagle service now\? \[Y/n\]"),
    re.compile(r"WebSocket \(video\)"),
]

INIT_INSTALL_SCRIPT_FILES = [
    PROJECT_ROOT / "install.sh",
    PROJECT_ROOT / "install.ps1",
    PROJECT_ROOT / "scripts" / "init.sh",
    PROJECT_ROOT / "scripts" / "init.bat",
]


def test_critical_infrastructure_docs_do_not_teach_stale_defaults():
    failures = []
    for path in CRITICAL_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in STALE_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_secondary_drone_interface_docs_do_not_teach_stale_defaults():
    failures = []
    for path in SECONDARY_DRONE_INTERFACE_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in SECONDARY_STALE_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_active_runtime_docs_do_not_teach_legacy_ports_or_gimbal_keys():
    failures = []
    for path in ACTIVE_RUNTIME_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in ACTIVE_RUNTIME_STALE_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_active_tracker_docs_use_canonical_config_hierarchy():
    failures = []
    for path in ACTIVE_TRACKER_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in TRACKER_STALE_CONFIG_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_video_streaming_docs_use_current_config_keys():
    failures = []
    for path in VIDEO_STREAMING_CONFIG_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in VIDEO_STREAMING_STALE_CONFIG_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_video_osd_docs_use_current_config_keys():
    failures = []
    for path in VIDEO_OSD_CONFIG_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in VIDEO_OSD_STALE_CONFIG_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_qgc_http_ws_source_plan_preserves_generic_and_pixeagle_boundaries():
    plan_path = (
        PROJECT_ROOT
        / "docs"
        / "video"
        / "04-streaming"
        / "qgc-http-websocket-source-plan.md"
    )
    remote_path = (
        PROJECT_ROOT
        / "docs"
        / "video"
        / "04-streaming"
        / "remote-media-security.md"
    )
    plan_text = plan_path.read_text(encoding="utf-8")
    remote_text = remote_path.read_text(encoding="utf-8")

    required_plan_terms = [
        "Keep the QGroundControl feature generic",
        "Generic anonymous HTTP MJPEG",
        "PixEagle same-host development",
        "PixEagle remote HTTP/WS",
        "PixEagle unsafe anonymous lab media",
        "Supported only with `unsafe_demo_lan_media_only`",
        "Do not provide a no-password remote control panel",
        "demo_lan_browser",
        "unsafe_demo_lan_media_only",
        "The official repository default should remain a beginner-friendly local demo",
        "remote backend control",
        "PixEagle Configuration Contract",
        "API_ALLOWED_HOSTS",
        "request Host authority allowlist",
        "selected GCS/source-IP restriction belongs to firewall",
        "Authorization: Bearer <token>",
        "media:read",
        "video-only QGC",
        "WebSocket Origin",
        "credential redaction",
        "machine-client",
        "authorization mechanism",
    ]
    missing = [term for term in required_plan_terms if term not in plan_text]

    required_remote_terms = [
        "demo_lan_browser",
        "API_AUTH_MODE: browser_session",
        "Do not provide a no-password remote control panel",
        "unsafe_demo_lan_media_only",
        "media viewing rather than dashboard mutations",
        "selected GCS/source IPs",
        "Host and client-source controls are separate",
        "For QGC video-only use, grant only `media:read`",
        "local same-host demo requires no",
        "manual credential setup",
    ]
    missing.extend(
        f"remote policy missing {term}"
        for term in required_remote_terms
        if term not in remote_text
    )

    assert not missing, "\n".join(missing)


def test_setup_profiles_are_documented_and_linked_from_onboarding_docs():
    setup_doc = PROJECT_ROOT / "docs" / "setup" / "setup-profiles.md"
    setup_text = setup_doc.read_text(encoding="utf-8")
    required_terms = [
        "configs/config_default.yaml` is the checked-in runtime source of truth",
        "configs/config.yaml` is optional",
        "field_qgc_video",
        "make qgc-video-profile GCS_HOST=",
        "backend loopback-only",
        "demo_lan_browser",
        "make demo-lan-browser-profile LAN_HOST=",
        "Generated browser-session user file",
        "private overlay/VPN",
        "100.64.0.0/10",
        "%25eth0",
        "dashboard port `3040`",
        "port `5077`",
        "TLS is not only for domain names",
        "production_remote",
        "make production-remote-profile",
        "SESSION_USER_FILE",
        "CREDENTIAL_HANDOFF_FILE",
        "API_SESSION_COOKIE_SECURE: true",
        "serve the dashboard under `/pixeagle`",
        "proxy `/pixeagle-api`",
        "production remote reverse-proxy runbook",
        "unsafe_demo_lan_media_only",
        "make unsafe-demo-lan-media-profile",
        "ALLOW_UNAUTHENTICATED_MEDIA_STREAMING: true",
        "Do not create a no-password remote control panel",
        "Authorization",
        "media:read",
        "API_ALLOWED_HOSTS",
        "client/source-IP allowlists",
        "firewall",
    ]
    missing = [term for term in required_terms if term not in setup_text]

    linked_docs = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs" / "README.md",
        PROJECT_ROOT / "docs" / "INSTALLATION.md",
        PROJECT_ROOT / "docs" / "CONFIGURATION.md",
    ]
    missing.extend(
        f"{path.relative_to(PROJECT_ROOT)} does not link setup profiles"
        for path in linked_docs
        if "setup-profiles.md" not in path.read_text(encoding="utf-8")
    )

    assert not missing, "\n".join(missing)


def test_onboarding_docs_do_not_confuse_host_allowlist_with_client_ip():
    docs_to_check = {
        "README.md": PROJECT_ROOT / "README.md",
        "docs/INSTALLATION.md": PROJECT_ROOT / "docs" / "INSTALLATION.md",
        "docs/drone-interface/04-infrastructure/port-configuration.md": (
            PROJECT_ROOT / "docs" / "drone-interface" / "04-infrastructure" / "port-configuration.md"
        ),
    }
    combined = "\n".join(
        f"# {name}\n{path.read_text(encoding='utf-8')}"
        for name, path in docs_to_check.items()
    )

    for required in [
        "not the client IP",
        "not a GCS source-IP allowlist",
        "selected client restrictions",
        "firewall",
        "VPN",
        "reverse-proxy source",
        "sudo ufw allow from <trusted-gcs-ip-or-cidr> to any port 14550 proto udp",
        "sudo ufw allow from <trusted-gcs-ip-or-cidr> to any port 5760 proto tcp",
    ]:
        assert required in combined


def test_production_remote_runbook_preserves_proxy_firewall_and_evidence_boundary():
    runbook = (
        PROJECT_ROOT / "docs" / "setup" / "production-remote-reverse-proxy.md"
    ).read_text(encoding="utf-8")

    for required in [
        "POSIX owner-only file modes",
        "proxy_pass http://127.0.0.1:5077/",
        "proxy_set_header Upgrade",
        "Do not open `3040` or `5077`",
        "Evidence Checklist",
        "make production-remote-browser-e2e-dry-run",
        "ALLOW_LOCAL_SELF_SIGNED_TLS=1 make production-remote-browser-e2e",
        "does not prove nginx/Caddy",
        "does not retain plaintext credentials",
        "Rollback",
    ]:
        assert required in runbook


def test_remote_browser_docs_keep_lab_overlay_and_production_tls_boundaries():
    docs = {
        "README.md": (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        "setup": (PROJECT_ROOT / "docs" / "setup" / "setup-profiles.md").read_text(
            encoding="utf-8"
        ),
        "remote": (
            PROJECT_ROOT
            / "docs"
            / "video"
            / "04-streaming"
            / "remote-media-security.md"
        ).read_text(encoding="utf-8"),
        "exposure": (
            PROJECT_ROOT / "docs" / "apis" / "api-exposure-boundary.md"
        ).read_text(encoding="utf-8"),
        "qgc": (
            PROJECT_ROOT
            / "docs"
            / "video"
            / "04-streaming"
            / "qgc-http-websocket-source-plan.md"
        ).read_text(encoding="utf-8"),
    }
    checks = {
        "setup": [
            "HTTP for beginner lab/private-overlay testing",
            "production remote",
            "browser profile",
            "port `5077`",
            "%25eth0",
            "TLS is not only for domain names",
            "make production-remote-profile",
            "proxy `/pixeagle-api`",
        ],
        "remote": [
            "Lab/private-overlay browser demo",
            "TLS is not a domain-only concept",
            "overlay remains a lab or operator-approved test profile",
            "IPv6 zone identifiers",
            "production_remote",
            "dashboard served under `/pixeagle`",
        ],
        "exposure": [
            "private overlay is still not a production remote-browser approval",
            "TLS is not limited to public domain names",
            "production-remote-profile",
            "HTTPS/WSS reverse proxy",
        ],
        "qgc": [
            "private overlay/VPN",
            "100.64.0.0/10",
            "replace production TLS/operator",
        ],
        "README.md": [
            "Lab/private-overlay browser demo",
            "TLS is not domain-only",
        ],
    }
    missing = [
        f"{doc_name} missing {term}"
        for doc_name, terms in checks.items()
        for term in terms
        if term not in docs[doc_name]
    ]

    assert not missing, "\n".join(missing)


def test_setup_docs_and_scripts_do_not_reintroduce_default_config_or_service_drift():
    failures = []
    for path in SETUP_PROFILE_DOCS_AND_SCRIPTS:
        text = path.read_text(encoding="utf-8")
        for pattern in PXE0068_STALE_SETUP_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_init_and_install_scripts_do_not_create_runtime_config_by_copying_defaults():
    failures = []
    unsafe_patterns = [
        re.compile(r"\bcp\s+configs/config_default\.yaml\s+configs/config\.yaml"),
        re.compile(r"\bcopy\s+configs\\config_default\.yaml\s+configs\\config\.yaml", re.IGNORECASE),
        re.compile(r"\bcp\s+\"\$DEFAULT_CONFIG\"\s+\"\$USER_CONFIG\""),
        re.compile(r"\bcopy\s+\"%DEFAULT_CONFIG%\"\s+\"%USER_CONFIG%\"", re.IGNORECASE),
    ]
    for path in INIT_INSTALL_SCRIPT_FILES:
        text = path.read_text(encoding="utf-8")
        for pattern in unsafe_patterns:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    init_text = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")
    if "PIXEAGLE_ENABLE_SERVICE_SETUP=1" not in init_text:
        failures.append("scripts/init.sh does not document explicit service setup opt-in")
    if 'PIXEAGLE_ENABLE_SERVICE_SETUP:-0}" == "1"' not in init_text:
        failures.append("scripts/init.sh service setup is not gated by PIXEAGLE_ENABLE_SERVICE_SETUP")

    assert not failures, "\n".join(failures)


def test_troubleshooting_labels_backend_media_and_legacy_telemetry_ports_correctly():
    text = (PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md").read_text(encoding="utf-8")
    assert "browser-session boundary" not in text
    assert "Legacy telemetry WebSocket" in text
    assert "WebSocket (video)" not in text
    assert "`API_AUTH_MODE=browser_session`" in text


def test_service_docs_keep_media_health_auth_and_claim_boundary():
    service_text = (PROJECT_ROOT / "docs" / "SERVICE_MANAGEMENT.md").read_text(encoding="utf-8")
    troubleshooting_text = (PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md").read_text(encoding="utf-8")

    combined = f"{service_text}\n{troubleshooting_text}"
    assert "Media health" in combined
    assert "/api/v1/streams/media-health" in combined
    assert "media:read" in combined
    assert "PIXEAGLE_MEDIA_HEALTH_BEARER_TOKEN_FILE" in combined
    assert "query-string tokens" in combined
    assert "process-local" in combined
    assert "Remote receipt: not proven" in combined
    assert "/api/v1/auth/login" not in service_text


def test_drone_timing_docs_do_not_overstate_setpoint_sender_publish_cadence():
    failures = []
    for path in PXE0030_TIMING_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in PXE0030_STALE_TIMING_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_safety_docs_do_not_teach_fail_open_or_stale_limit_mapping():
    failures = []
    for path in PXE0033_SAFETY_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in PXE0033_STALE_SAFETY_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_follower_docs_do_not_teach_field_by_field_command_publication():
    failures = []
    for path in PXE0034_COMMAND_INTENT_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in PXE0034_STALE_COMMAND_INTENT_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_project_docs_do_not_teach_single_field_setpoint_mutation():
    failures = []
    for path in _all_project_markdown_docs():
        text = path.read_text(encoding="utf-8")
        for pattern in PXE0034_STALE_SETPOINT_MUTATION_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_offboard_docs_teach_commander_not_frame_loop_publication():
    failures = []
    for path in PXE0007_OFFBOARD_COMMANDER_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in PXE0007_STALE_OFFBOARD_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_mavlink_docs_teach_typed_freshness_config():
    failures = []
    required_terms = [
        "MAVLINK_REQUEST_TIMEOUT_S",
        "MAVLINK_REQUEST_RETRIES",
        "MAVLINK_STALE_TIMEOUT_S",
        "mavlink_telemetry",
    ]
    for path in PXE0014_MAVLINK_FRESHNESS_DOCS:
        text = path.read_text(encoding="utf-8")
        for term in required_terms:
            if term not in text:
                failures.append(f"{path.relative_to(PROJECT_ROOT)} missing {term}")
        for pattern in PXE0014_STALE_MAVLINK_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    assert not failures, "\n".join(failures)


def test_companion_runtime_contract_keeps_sidecars_local_guarded_and_external():
    text = COMPANION_RUNTIME_CONTRACT.read_text(encoding="utf-8")
    required_terms = [
        "127.0.0.1:9070",
        "127.0.0.1:9080",
        "MAVLINK_ANYWHERE_API_TOKEN",
        "SMART_WIFI_MANAGER_API_TOKEN",
        "X-Sidecar-CSRF",
        "password_file",
        "dry_run=true",
        "process-local",
        "acknowledged_risks",
        "fleet-merge",
        "fleet-strict",
        "service runtime modes",
        "Generated OpenAPI candidates are non-callable",
        "MDS_MCP_ENABLED=false",
        "Agent-specific bypass access",
        "approved, blocked, or",
        "does not silently clone, update, or install companion repositories",
        "Read-only health or status success is not routing success",
    ]

    missing = [term for term in required_terms if term not in text]
    assert not missing, "Companion runtime contract missing:\n" + "\n".join(missing)


def test_mavlink_anywhere_doc_does_not_teach_unguarded_remote_management():
    text = MAVLINK_ANYWHERE_DOC.read_text(encoding="utf-8")
    required_terms = [
        "--dashboard-auth-password-file",
        "--dashboard-api-token-file",
        "MAVLINK_ANYWHERE_API_TOKEN",
        "X-Sidecar-CSRF",
        "dry_run=true",
        "confirmation token",
        "process-local",
        "validated-tag-or-commit",
        "Open-lab mode",
        "A successful health/status probe is not routing evidence",
    ]

    missing = [term for term in required_terms if term not in text]
    failures = [f"missing {term}" for term in missing]
    first_checkout = text.find("git checkout <validated-tag-or-commit>")
    first_root_install = text.find("sudo ./install_mavlink_router.sh")
    if first_checkout < 0 or first_root_install < 0 or first_checkout > first_root_install:
        failures.append("initial root install is not preceded by validated revision checkout")

    assert not failures, "MavlinkAnywhere guide problems:\n" + "\n".join(failures)


def test_pixeagle_docs_do_not_teach_unqualified_unauthenticated_api_exposure():
    failures = []
    unsafe_patterns = [
        re.compile(r"sudo ufw allow (?:5077|3040)(?:/tcp)?\b"),
        re.compile(r"\|\s*5077\s*\|[^|]+\|\s*Yes\s*\|"),
        re.compile(r"\*\*LAN\*\*:\s*http://<your-ip>:3040"),
        re.compile(r"Remote access via IP"),
        re.compile(r"Firewall allows ports 3040, 5077"),
        re.compile(r"sudo ufw allow from <trusted-cidr> to any port 5077"),
        re.compile(r"Test exposed PixEagle ports", re.IGNORECASE),
        re.compile(r"nc -zv\s+\S+\s+5077"),
        re.compile(r'"5077:5077"'),
        re.compile(r"python ~/PixEagle/src/main\.py"),
        re.compile(r"mavlink-routerd -e \d+\.\d+\.\d+\.\d+:14540"),
    ]
    combined = []
    for path in PIXEAGLE_EXPOSURE_DOCS:
        text = path.read_text(encoding="utf-8")
        combined.append(text)
        for pattern in unsafe_patterns:
            if pattern.search(text):
                failures.append(f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}")

    all_text = "\n".join(combined)
    for required in [
        "local-only",
        "trusted_lan_legacy",
        "Do not expose",
    ]:
        if required not in all_text:
            failures.append(f"active exposure docs missing {required}")

    assert not failures, "\n".join(failures)


def _strip_markdown_code(text):
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def _local_markdown_link_targets(text):
    return re.finditer(r"\[[^\]]+\]\(([^)]+)\)", _strip_markdown_code(text))


def _all_project_markdown_docs():
    docs = [PROJECT_ROOT / "README.md"]
    docs.extend(sorted((PROJECT_ROOT / "docs").rglob("*.md")))
    return docs


def _is_external_or_anchor(target):
    return target.startswith(("http://", "https://", "#", "mailto:"))


def test_project_markdown_local_links_exist():
    docs_to_check = _all_project_markdown_docs()
    missing = []

    for doc_path in docs_to_check:
        text = doc_path.read_text(encoding="utf-8")
        for match in _local_markdown_link_targets(text):
            target = match.group(1).split("#", 1)[0]
            if not target or _is_external_or_anchor(target):
                continue
            target_path = (doc_path.parent / target).resolve()
            if not target_path.exists():
                missing.append(
                    f"{doc_path.relative_to(PROJECT_ROOT)} -> {match.group(1)}"
                )

    assert not missing, "Broken active documentation links:\n" + "\n".join(missing)
