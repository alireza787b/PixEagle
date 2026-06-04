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
