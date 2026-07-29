"""Cross-platform unit contracts for the native Windows lifecycle controller."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest


pytestmark = pytest.mark.unit
REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = REPO_ROOT / "scripts" / "windows" / "runtime.py"
SETUP_PATH = REPO_ROOT / "scripts" / "windows" / "setup.py"
BOOTSTRAP_PATH = REPO_ROOT / "install.ps1"


def _load_runtime_module():
    spec = importlib.util.spec_from_file_location(
        "pixeagle_windows_runtime_contract",
        RUNTIME_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_setup_module():
    spec = importlib.util.spec_from_file_location(
        "pixeagle_windows_setup_contract",
        SETUP_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spawn_sleeping_child() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _receipt_for(module, process: subprocess.Popen, name: str = "test") -> dict:
    inspected = psutil.Process(process.pid)
    return {
        "name": name,
        "pid": process.pid,
        "create_time": inspected.create_time(),
        "executable": module._normalize_path(sys.executable),
        "command_anchor": "",
        "log_path": "unused.log",
    }


def test_process_identity_rejects_reused_creation_time():
    module = _load_runtime_module()
    process = _spawn_sleeping_child()
    try:
        receipt = _receipt_for(module, process)
        owned, detail = module._process_matches(receipt)
        assert owned is True
        assert detail == "owned"

        receipt["create_time"] -= 10
        owned, detail = module._process_matches(receipt)
        assert owned is False
        assert "creation time" in detail
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_stop_state_terminates_only_exact_receipt_process(tmp_path, monkeypatch):
    module = _load_runtime_module()
    state_file = tmp_path / "runtime.json"
    monkeypatch.setattr(module, "STATE_FILE", state_file)

    owned_process = _spawn_sleeping_child()
    unrelated_process = _spawn_sleeping_child()
    try:
        state = {
            "schema_version": module.STATE_SCHEMA_VERSION,
            "project_root": str(module.PROJECT_ROOT),
            "components": [_receipt_for(module, owned_process, "owned")],
        }
        state_file.write_text("{}\n", encoding="utf-8")

        exit_code, stopped = module._stop_state(state)

        assert exit_code == 0
        assert "owned" in stopped
        assert owned_process.wait(timeout=10) is not None
        assert unrelated_process.poll() is None
        assert not state_file.exists()
    finally:
        for process in (owned_process, unrelated_process):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def test_port_preflight_refuses_unknown_listener_without_stopping_it():
    module = _load_runtime_module()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    try:
        with pytest.raises(module.RuntimeContractError, match="did not terminate"):
            module._preflight_ports({"test": port})
        listener.settimeout(0.1)
        assert listener.fileno() >= 0
    finally:
        listener.close()


def test_runtime_receipt_requires_an_explicit_checkout_root(tmp_path, monkeypatch):
    module = _load_runtime_module()
    state_file = tmp_path / "runtime.json"
    monkeypatch.setattr(module, "STATE_FILE", state_file)
    state_file.write_text(
        '{"schema_version":1,"project_root":"","components":[]}\n',
        encoding="utf-8",
    )

    with pytest.raises(module.RuntimeContractError, match="another checkout"):
        module._load_state()


def test_runtime_start_timeout_accepts_the_documented_default():
    module = _load_runtime_module()
    args = argparse.Namespace(timeout=45.0)

    module._normalize_start_options(args)

    assert args.timeout == 45.0


def test_manual_mavsdk_component_requires_explicit_unscoped_grpc_opt_in():
    source = (
        REPO_ROOT / "scripts" / "components" / "mavsdk_server.bat"
    ).read_text(encoding="utf-8")

    assert "PIXEAGLE_ALLOW_UNSCOPED_MAVSDK_GRPC" in source
    assert "cannot be restricted to loopback" in source


def test_wait_for_http_fails_when_owned_process_exits():
    module = _load_runtime_module()
    process = subprocess.Popen(
        [sys.executable, "-c", "raise SystemExit(7)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    process.wait(timeout=10)

    with pytest.raises(module.RuntimeContractError, match="exited during startup"):
        module._wait_for_http(
            "http://127.0.0.1:1/status",
            process,
            time.monotonic() + 1,
            "backend",
        )


def test_bootstrap_accepts_supported_python_launcher_without_exiting_shell():
    bootstrap = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    batch_bootstrap = (
        REPO_ROOT / "scripts" / "init.bat"
    ).read_text(encoding="utf-8")

    assert "function Get-SupportedPythonInvocation" in bootstrap
    assert '[pscustomobject]@{ Command = "py.exe"; Prefix = @("-3.12") }' in bootstrap
    assert '[pscustomobject]@{ Command = "py.exe"; Prefix = @("-3.11") }' in bootstrap
    assert '[pscustomobject]@{ Command = "python.exe"; Prefix = @() }' in bootstrap
    assert "sys.version_info[:2] in {(3, 11), (3, 12)}" in bootstrap
    assert "supported_arch" in bootstrap
    assert 'struct.calcsize("P") * 8 == 64' in bootstrap
    assert "struct.calcsize('P')*8 == 64" in batch_bootstrap
    assert "python --version" not in bootstrap
    assert "legacyInitScript" not in bootstrap
    assert "PIXEAGLE_WINDOWS_NONINTERACTIVE" in bootstrap
    assert "PIXEAGLE_WINDOWS_SKIP_SOURCE_UPDATE" in bootstrap
    assert "--non-interactive --without-sidecars" in bootstrap
    assert not any(
        line.strip().startswith("exit ")
        for line in bootstrap.splitlines()
    )


def test_setup_wraps_npm_cmd_with_the_windows_command_processor():
    module = _load_setup_module()
    source = SETUP_PATH.read_text(encoding="utf-8")

    command = module._npm_command("npm", "ci")
    if os.name == "nt":
        assert command[1:4] == ["/d", "/s", "/c"]
        assert "npm" in command[4]
        assert "ci" in command[4]
    else:
        assert command == ["npm", "ci"]
    assert 'os.environ.get("COMSPEC")' in source
    assert "subprocess.list2cmdline" in source
    assert '"/d"' in source
    assert '"/s"' in source
    assert '"/c"' in source


def test_setup_consumes_exact_staged_config_baseline(tmp_path, monkeypatch):
    module = _load_setup_module()
    configs = tmp_path / "configs"
    configs.mkdir()
    staged = configs / ".config_default_preupdate.yaml"
    staged.write_text("Streaming: {}\n", encoding="utf-8")
    commands = []
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "_run", lambda command: commands.append(command))

    module._ensure_config_lifecycle()

    assert commands == [
        [
            module.VENV_PYTHON,
            module.CONFIG_SYNC,
            "--initialize-baseline-from",
            staged,
        ]
    ]
    assert not staged.exists()


def test_setup_preserves_replaced_staged_config_baseline(tmp_path, monkeypatch):
    module = _load_setup_module()
    configs = tmp_path / "configs"
    configs.mkdir()
    staged = configs / ".config_default_preupdate.yaml"
    staged.write_text("Streaming: {}\n", encoding="utf-8")
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)

    def replace_staged(_command):
        staged.unlink()
        staged.write_text("replacement: true\n", encoding="utf-8")

    monkeypatch.setattr(module, "_run", replace_staged)

    with pytest.raises(module.SetupError, match="changed during reconciliation"):
        module._ensure_config_lifecycle()

    assert staged.read_text(encoding="utf-8") == "replacement: true\n"


def test_runtime_settings_require_the_documented_local_core_profile(
    tmp_path,
    monkeypatch,
):
    module = _load_runtime_module()
    video = tmp_path / "preview.mp4"
    video.write_bytes(b"preview")
    dashboard_env = {
        "HOST": "127.0.0.1",
        "PORT": "3040",
    }
    base_config = {
        "VideoSource": {
            "VIDEO_SOURCE_TYPE": "VIDEO_FILE",
            "VIDEO_FILE_PATH": str(video),
        },
        "Streaming": {
            "ENABLE_STREAMING": True,
            "API_EXPOSURE_MODE": "local_only",
            "API_AUTH_MODE": "local_compat",
            "HTTP_STREAM_HOST": "127.0.0.1",
            "HTTP_STREAM_PORT": 5077,
        },
        "PX4": {},
        "MAVLink": {},
    }
    monkeypatch.setattr(module, "_read_dashboard_env", lambda: dashboard_env)

    monkeypatch.setattr(module, "_read_yaml_config", lambda: base_config)
    settings = module._runtime_settings()
    assert settings["video_path"] == str(video.resolve())

    for section, key, value, message in (
        ("Streaming", "API_AUTH_MODE", "browser_session", "API_AUTH_MODE"),
        ("Streaming", "ENABLE_STREAMING", False, "ENABLE_STREAMING"),
        ("VideoSource", "VIDEO_SOURCE_TYPE", "RTSP_STREAM", "VIDEO_SOURCE_TYPE"),
    ):
        candidate = {
            name: dict(values) if isinstance(values, dict) else values
            for name, values in base_config.items()
        }
        candidate[section][key] = value
        monkeypatch.setattr(module, "_read_yaml_config", lambda value=candidate: value)
        with pytest.raises(module.RuntimeContractError, match=message):
            module._runtime_settings()


def test_runtime_settings_reject_missing_preview_video(tmp_path, monkeypatch):
    module = _load_runtime_module()
    monkeypatch.setattr(
        module,
        "_read_yaml_config",
        lambda: {
            "VideoSource": {
                "VIDEO_SOURCE_TYPE": "VIDEO_FILE",
                "VIDEO_FILE_PATH": str(tmp_path / "missing.mp4"),
            },
            "Streaming": {
                "ENABLE_STREAMING": True,
                "API_EXPOSURE_MODE": "local_only",
                "API_AUTH_MODE": "local_compat",
                "HTTP_STREAM_HOST": "127.0.0.1",
                "HTTP_STREAM_PORT": 5077,
            },
        },
    )
    monkeypatch.setattr(
        module,
        "_read_dashboard_env",
        lambda: {"HOST": "127.0.0.1", "PORT": "3040"},
    )

    with pytest.raises(module.RuntimeContractError, match="video file is unavailable"):
        module._runtime_settings()


def test_unverifiable_runtime_receipt_is_preserved(tmp_path, monkeypatch):
    module = _load_runtime_module()
    state_file = tmp_path / "runtime.json"
    state_file.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(module, "STATE_FILE", state_file)
    state = {
        "schema_version": module.STATE_SCHEMA_VERSION,
        "project_root": str(module.PROJECT_ROOT),
        "components": [{"name": "backend"}],
    }

    exit_code, details = module._stop_state(state)

    assert exit_code == 1
    assert any("unverifiable" in detail for detail in details)
    assert state_file.exists()


def test_empty_interrupted_start_receipt_is_retired_under_lifecycle_lock(
    tmp_path,
    monkeypatch,
):
    module = _load_runtime_module()
    state_file = tmp_path / "runtime.json"
    state_file.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(module, "STATE_FILE", state_file)
    state = {
        "schema_version": module.STATE_SCHEMA_VERSION,
        "project_root": str(module.PROJECT_ROOT),
        "status": "starting",
        "components": [],
    }

    assert module._remove_fully_stale_state(state, []) is True
    assert not state_file.exists()


def test_shared_lifecycle_lock_path_matches_windows_bootstrap_contract():
    runtime = _load_runtime_module()
    setup = _load_setup_module()
    bootstrap = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    runtime_source = RUNTIME_PATH.read_text(encoding="utf-8")

    assert runtime.LIFECYCLE_LOCK_FILE == setup.LIFECYCLE_LOCK_FILE
    assert "pixeagle-windows-$name.lock" in bootstrap
    assert 'struct.calcsize("P") * 8' in runtime_source


def test_existing_venv_identity_must_be_supported_x64_and_isolated(
    tmp_path,
    monkeypatch,
):
    module = _load_setup_module()
    venv = tmp_path / ".venv"
    python = venv / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"placeholder")
    monkeypatch.setattr(module, "VENV_DIRECTORY", venv)
    monkeypatch.setattr(module, "VENV_PYTHON", python)

    def identity(version, machine="AMD64", bits=64):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "version": version,
                    "machine": machine,
                    "bits": bits,
                    "prefix": str(venv),
                    "base_prefix": str(tmp_path / "Python"),
                    "cache_tag": "cpython-test",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: identity([3, 12, 3]))
    assert module._venv_interpreter_identity()["version"] == [3, 12, 3]

    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: identity([3, 10, 9]))
    with pytest.raises(module.SetupError, match="unsupported Python"):
        module._venv_interpreter_identity()

    monkeypatch.setattr(
        module,
        "_run",
        lambda *_args, **_kwargs: identity([3, 12, 3], machine="x86", bits=32),
    )
    with pytest.raises(module.SetupError, match="not an x64"):
        module._venv_interpreter_identity()
