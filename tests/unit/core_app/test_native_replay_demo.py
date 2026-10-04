"""Private real-core replay preparation; never starts a camera or application."""

import json
import hashlib
import stat
from pathlib import Path

import pytest
import yaml

from classes.browser_user_store import BrowserUserStore
from classes.config_service import ConfigService
from classes.model_artifact_policy import ModelArtifactPolicyError, ModelProvenanceStore
from classes.model_manager import MODEL_INSPECTION_CACHE_SCHEMA_VERSION, ModelManager
from tools.native_replay_demo import REPOSITORY, demo_config, prepare, run, validate, validate_runtime_policy


def test_real_replay_snapshot_is_private_inhibited_and_does_not_change_checkout(tmp_path):
    runtime_config = REPOSITORY / "configs/config.yaml"
    before = runtime_config.read_bytes() if runtime_config.exists() else None
    demo = prepare(tmp_path / "replay", port=8093)
    manifest = validate(demo)
    assert stat.S_IMODE(demo.stat().st_mode) == 0o700
    assert manifest["kind"] == "real-core-recorded-video"
    assert (demo / "src/main.py").read_bytes() == (REPOSITORY / "src/main.py").read_bytes()
    assert (demo / "src/classes/video_handler.py").read_bytes() == (
        REPOSITORY / "src/classes/video_handler.py").read_bytes()
    assert (demo / "resources/test4.mp4").read_bytes() == (REPOSITORY / "resources/test4.mp4").read_bytes()
    assert not any(path.is_symlink() for path in demo.rglob("*"))
    config = yaml.safe_load((demo / "configs/config.yaml").read_text())
    assert config["VideoSource"]["VIDEO_SOURCE_TYPE"] == "VIDEO_FILE"
    assert config["Follower"]["FOLLOWER_EXECUTION_MODE"] == "COMMAND_PREVIEW"
    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True
    assert config["MAVLink"]["MAVLINK_ENABLED"] is False
    assert config["GimbalTracker"]["ENABLED"] is False
    assert config["GimbalTracker"]["CONTROL_ENABLED"] is False
    assert config["GStreamer"]["ENABLE_GSTREAMER_STREAM"] is False
    assert config["Telemetry"]["ENABLE_UDP_STREAM"] is False
    assert config["PX4"]["MAVSDK_SERVER_PORT"] == config["Streaming"]["HTTP_STREAM_PORT"]
    assert config["Streaming"]["HTTP_STREAM_HOST"] == "127.0.0.1"
    assert config["Streaming"]["API_AUTH_MODE"] == "browser_session"
    assert config["Streaming"]["ALLOW_UNAUTHENTICATED_MEDIA_STREAMING"] is False
    users = BrowserUserStore(Path(config["Streaming"]["API_SESSION_USER_FILE"])).load_snapshot().records
    assert len(users) == 1 and users[0].role == "viewer"
    credentials = json.loads((demo / "credentials.json").read_text())
    assert credentials["username"] == users[0].username
    assert credentials["password"] not in (demo / "configs/secrets/native-demo-users.json").read_text()
    assert stat.S_IMODE((demo / "credentials.json").stat().st_mode) == 0o600
    checked = ConfigService(project_root=demo).validate_config_mapping(config, require_safety=True)
    assert checked.valid, checked.errors
    assert (runtime_config.read_bytes() if runtime_config.exists() else None) == before


def test_replay_validation_blocks_modified_core_before_start(tmp_path):
    demo = prepare(tmp_path / "replay")
    (demo / "src/main.py").write_text("raise RuntimeError('modified')\n")
    with pytest.raises(ValueError, match="snapshot changed: src/main.py"):
        validate(demo)


def test_replay_preparation_never_replaces_existing_directory(tmp_path):
    marker = tmp_path / "operator-data"
    marker.write_text("preserved")
    with pytest.raises(ValueError, match="existing data is never replaced"):
        prepare(tmp_path)
    assert marker.read_text() == "preserved"


def test_operator_replay_requires_a_new_snapshot_and_keeps_aircraft_inhibited(tmp_path):
    demo = prepare(tmp_path / "operator-replay", role="operator")
    manifest = validate(demo)
    assert manifest["role"] == "operator" and manifest["following_enabled"] is False
    credentials = json.loads((demo / "credentials.json").read_text())
    assert credentials["role"] == "operator"
    with pytest.raises(ValueError, match="existing data"):
        prepare(demo, role="viewer")


def test_admin_dashboard_replay_allows_only_the_explicit_loopback_origin(tmp_path):
    demo = prepare(tmp_path / "dashboard-replay", port=8097, role="admin", dashboard_port=3040)
    manifest = validate(demo)
    assert manifest["dashboard_port"] == 3040
    assert manifest["role"] == "admin"
    config = yaml.safe_load((demo / "configs/config.yaml").read_text())
    assert config["Streaming"]["API_CORS_ALLOWED_ORIGINS"] == [
        "http://127.0.0.1:8097", "http://127.0.0.1:3040",
    ]
    assert validate_runtime_policy(config).mode == "local_only"
    assert config["Streaming"]["API_AUTH_MODE"] == "browser_session"
    assert config["MAVLink"]["MAVLINK_ENABLED"] is False
    assert config["Follower"]["FOLLOWER_EXECUTION_MODE"] == "COMMAND_PREVIEW"
    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True
    users = BrowserUserStore(Path(config["Streaming"]["API_SESSION_USER_FILE"])).load_snapshot().records
    assert len(users) == 1 and users[0].role == "admin"


@pytest.mark.parametrize("port", [0, 1023, 65536, True, 8093, "3040"])
def test_dashboard_port_is_validated_before_snapshot_creation(tmp_path, port):
    demo = tmp_path / "invalid-dashboard"
    with pytest.raises(ValueError, match="Dashboard port"):
        prepare(demo, dashboard_port=port)
    assert not demo.exists()


def test_full_ai_dashboard_replay_keeps_configuration_validation_strict(tmp_path):
    models = _trusted_demo_models(tmp_path)
    demo = prepare(tmp_path / "ai-replay", role="admin", dashboard_port=3040,
                   model_store=models, model="vehicle.pt")
    path = demo / "configs/config.yaml"
    config = yaml.safe_load(path.read_text())
    config["Streaming"]["API_CORS_ALLOWED_ORIGINS"].append("http://127.0.0.1:3041")
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="preserve the inhibited"):
        validate(demo)


def test_dashboard_replay_manifest_cannot_allow_non_port_origin(tmp_path):
    demo = prepare(tmp_path / "dashboard-replay", dashboard_port=3040)
    path = demo / "demo-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["dashboard_port"] = "3040@untrusted.example"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Invalid demo dashboard port"):
        validate(demo)


def test_clean_bundled_recording_is_explicit_pinned_and_separate(tmp_path):
    demo = prepare(tmp_path / "clean-replay", role="operator", video="test1.mp4")
    manifest = validate(demo)
    assert manifest["video"] == "resources/test1.mp4"
    assert manifest["video_sha256"] == hashlib.sha256((REPOSITORY / manifest["video"]).read_bytes()).hexdigest()
    assert not (demo / "resources/test4.mp4").exists()
    config = yaml.safe_load((demo / "configs/config.yaml").read_text())
    assert config["VideoSource"]["VIDEO_FILE_PATH"] == "resources/test1.mp4"
    assert manifest["clean_osd"] is True and config["OSD"]["OSD_ENABLED"] is False
    assert config["SmartTracker"]["SMART_TRACKER_SHOW_PASSIVE_LABELS"] is False
    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True


def test_replay_cannot_select_an_arbitrary_video_path(tmp_path):
    with pytest.raises(ValueError, match="bundled"):
        prepare(tmp_path / "unsafe", video="../../camera-or-private-file")
    assert not (tmp_path / "unsafe").exists()


def _trusted_demo_models(tmp_path):
    root = tmp_path / "models"
    root.mkdir(mode=0o700)
    for name in ("vehicle.pt", "person.pt"):
        path = root / name
        path.write_bytes(f"Non-executable unit fixture: {name}".encode())
        path.chmod(0o600)
        ModelProvenanceStore(root).trust_pt(
            path, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            source="unit-test", expected_digest_verified=False,
        )
    return root


def test_full_ai_replay_copies_trust_receipts_without_loading_or_changing_models(tmp_path):
    models = _trusted_demo_models(tmp_path)
    before = (models / ".model-provenance.json").read_bytes()
    demo = prepare(tmp_path / "ai-replay", model_store=models, model="vehicle.pt", video="test2.mp4")
    manifest = validate(demo)
    assert manifest["profile"] == "full_ai"
    assert manifest["models"] == ["person.pt", "vehicle.pt"]
    assert manifest["selected_model"] == "vehicle.pt"
    assert (models / ".model-provenance.json").read_bytes() == before
    assert json.loads((demo / "models/.model-provenance.json").read_text()) == json.loads(before)
    config = yaml.safe_load((demo / "configs/config.yaml").read_text())
    assert config["SmartTracker"]["SMART_TRACKER_ENABLED"] is True
    assert config["SmartTracker"]["SMART_TRACKER_GPU_MODEL_PATH"] == "models/vehicle.pt"
    assert config["GimbalTracker"]["CONTROL_ENABLED"] is False
    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True
    checked = ConfigService(project_root=demo).validate_config_mapping(config, require_safety=True)
    assert checked.valid, checked.errors
    (demo / "models/vehicle.pt").write_bytes(b"modified")
    with pytest.raises(ValueError, match="snapshot changed: models/vehicle.pt"):
        validate(demo)


def test_full_ai_replay_refuses_modified_trusted_artifact(tmp_path):
    models = _trusted_demo_models(tmp_path)
    (models / "person.pt").write_bytes(b"changed since registration")
    with pytest.raises(ModelArtifactPolicyError):
        prepare(tmp_path / "ai-replay", model_store=models, model="vehicle.pt")


def test_full_ai_replay_preserves_only_digest_bound_inspection_without_executing_models(tmp_path, monkeypatch):
    models = _trusted_demo_models(tmp_path)
    cache = {}
    for name in ("vehicle", "person"):
        cache[name] = {
            "inspection_schema_version": MODEL_INSPECTION_CACHE_SCHEMA_VERSION,
            "inspection_artifact_sha256": hashlib.sha256((models / f"{name}.pt").read_bytes()).hexdigest(),
            "metadata": {"checkpoint_executed": True, "class_names": [name], "task": "detect",
                         "smarttracker_supported": True},
        }
    cache["person"]["inspection_artifact_sha256"] = "0" * 64
    cache_path = models / ".models.json"
    cache_path.write_text(json.dumps(cache))
    cache_path.chmod(0o600)
    monkeypatch.setattr(ModelManager, "validate_model", lambda *args, **kwargs: pytest.fail("Checkpoint executed"))
    demo = prepare(tmp_path / "ai-replay", model_store=models, model="vehicle.pt")
    copied_cache = json.loads((demo / "models/.models.json").read_text())
    assert list(copied_cache) == ["vehicle"]
    assert copied_cache["vehicle"] == cache["vehicle"]
    assert json.loads(cache_path.read_text()) == cache


def test_full_ai_replay_restarts_after_installed_model_selection_only(tmp_path):
    models = _trusted_demo_models(tmp_path)
    demo = prepare(tmp_path / "ai-replay", model_store=models, model="vehicle.pt")
    path = demo / "configs/config.yaml"
    config = yaml.safe_load(path.read_text())
    for field in ("SMART_TRACKER_GPU_MODEL_PATH", "SMART_TRACKER_CPU_MODEL_PATH"):
        config["SmartTracker"][field] = str(demo / "models/person.pt")
    path.write_text(yaml.safe_dump(config))
    validate(demo)
    config["FOLLOWER_CIRCUIT_BREAKER"] = False
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="preserve the inhibited"):
        validate(demo)


@pytest.mark.parametrize("changed", ["models/missing.pt", "models/../person.pt", "/tmp/person.pt"])
def test_full_ai_replay_refuses_unadvertised_model_paths(tmp_path, changed):
    models = _trusted_demo_models(tmp_path)
    demo = prepare(tmp_path / "ai-replay", model_store=models, model="vehicle.pt")
    path = demo / "configs/config.yaml"
    config = yaml.safe_load(path.read_text())
    config["SmartTracker"]["SMART_TRACKER_GPU_MODEL_PATH"] = changed
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="copied installed model"):
        validate(demo)


@pytest.mark.parametrize("options", [{"model": "vehicle.pt"}, {"model_store": "/missing"}])
def test_full_ai_replay_requires_explicit_store_and_model_before_copy(tmp_path, options):
    with pytest.raises(ValueError, match="both a model store and selected model"):
        prepare(tmp_path / "ai-replay", **options)
    assert not (tmp_path / "ai-replay").exists()


def test_run_uses_recorded_interpreter_and_private_ai_settings(tmp_path, monkeypatch):
    demo = prepare(tmp_path / "replay")
    manifest_path = demo / "demo-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["python"] = "/private/full-ai-venv/bin/python"
    manifest_path.write_text(json.dumps(manifest))
    calls = []
    monkeypatch.setattr("tools.native_replay_demo.os.chdir", lambda path: None)
    monkeypatch.setattr("tools.native_replay_demo.os.execve", lambda *args: calls.append(args))
    run(demo)
    executable, arguments, environment = calls[0]
    assert executable == arguments[0] == manifest["python"]
    assert environment["YOLO_AUTOINSTALL"] == "False"
    assert environment["YOLO_CONFIG_DIR"] == str(demo / ".ultralytics")
    assert (demo / ".ultralytics").is_dir()


def test_replay_runtime_policy_rejects_host_port_authority_even_when_schema_accepts_it(tmp_path):
    defaults = yaml.safe_load((REPOSITORY / "configs/config_default.yaml").read_text())
    config = demo_config(defaults, tmp_path, 8093)
    assert validate_runtime_policy(config).allowed_hosts == ("127.0.0.1",)
    config["Streaming"]["API_ALLOWED_HOSTS"] = ["127.0.0.1:8093"]
    with pytest.raises(ValueError, match="permits only loopback"):
        validate_runtime_policy(config)


@pytest.mark.parametrize("port", [0, 1023, 65536, True])
def test_replay_preparation_rejects_invalid_port_before_creating_directory(tmp_path, port):
    demo = tmp_path / "replay"
    with pytest.raises(ValueError, match="Demo port"):
        prepare(demo, port=port)
    assert not demo.exists()
