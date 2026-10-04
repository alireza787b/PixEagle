"""Real child-process restart ownership without camera or aircraft operations."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from classes.backend_supervisor import CONTRACT, supervisor_available

pytestmark = pytest.mark.unit


def test_supervisor_requires_live_immediate_parent(monkeypatch):
    monkeypatch.delenv("PIXEAGLE_RESTART_SUPERVISOR", raising=False)
    assert not supervisor_available()
    monkeypatch.setenv("PIXEAGLE_RESTART_SUPERVISOR", CONTRACT)
    monkeypatch.setenv("PIXEAGLE_RESTART_SUPERVISOR_PID", str(os.getppid()))
    assert supervisor_available()
    monkeypatch.setenv("PIXEAGLE_RESTART_SUPERVISOR_PID", str(os.getpid()))
    assert not supervisor_available()


@pytest.mark.parametrize("first_exit,expected_runs", [(42, 2), (1, 1), (0, 1)])
def test_only_exit42_restarts_and_preserves_process_logs(tmp_path, first_exit, expected_runs):
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.py").write_text(
        "import json, os, pathlib\n"
        "p=pathlib.Path('runs.jsonl')\n"
        "previous=p.exists()\n"
        "with p.open('a') as out:\n"
        " out.write(json.dumps({'run':os.environ['PIXEAGLE_RUN_ID'],"
        "'parent':os.getppid(),'supervisor':int(os.environ['PIXEAGLE_RESTART_SUPERVISOR_PID'])})+'\\n')\n"
        f"raise SystemExit(0 if previous else {first_exit})\n",
        encoding="utf-8",
    )
    supervisor = Path("src/classes/backend_supervisor.py").resolve()
    result = subprocess.run(
        [sys.executable, str(supervisor), "--root", str(tmp_path), "--log", str(tmp_path / "backend.log")],
        capture_output=True, timeout=10,
    )
    import json

    runs = [json.loads(row) for row in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert len(runs) == expected_runs
    assert all(row["parent"] == row["supervisor"] for row in runs)
    assert len({row["run"] for row in runs}) == expected_runs
    assert len(list(tmp_path.glob("backend-backend_*.log"))) == expected_runs
    assert result.returncode == (first_exit if first_exit == 1 else 0)


def test_sih_restart_reblocks_commands_without_mutating_sidecars(tmp_path):
    import json
    import yaml

    (tmp_path / "src").mkdir()
    (tmp_path / "configs").mkdir()
    config = tmp_path / "configs/config.yaml"
    config.write_text(yaml.safe_dump({"FOLLOWER_CIRCUIT_BREAKER": False,
        "PX4": {"SYSTEM_ADDRESS": "udpin://127.0.0.1:14540", "EXTERNAL_MAVSDK_SERVER": True,
            "MAVSDK_SERVER_ADDRESS": "127.0.0.1", "MAVSDK_SERVER_PORT": 50051},
        "MAVLink": {"MAVLINK_ENABLED": True, "MAVLINK_HOST": "127.0.0.1", "MAVLINK_PORT": 8088}}))
    (tmp_path / "src/main.py").write_text(
        "import json, pathlib, yaml\n"
        "p=pathlib.Path('runs.jsonl')\n"
        "previous=p.exists()\n"
        "c=pathlib.Path('configs/config.yaml')\n"
        "config=yaml.safe_load(c.read_text())\n"
        "with p.open('a') as out: out.write(json.dumps(config)+'\\n')\n"
        "config['FOLLOWER_CIRCUIT_BREAKER']=False\n"
        "c.write_text(yaml.safe_dump(config))\n"
        "raise SystemExit(0 if previous else 42)\n")
    result = subprocess.run([sys.executable, str(Path("src/classes/backend_supervisor.py").resolve()),
        "--root", str(tmp_path), "--sih"], capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    rows = [json.loads(row) for row in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert all(row["FOLLOWER_CIRCUIT_BREAKER"] is True for row in rows)
    assert config.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("section,key,value", [
    ("PX4", "MAVSDK_SERVER_ADDRESS", "192.0.2.20"),
    ("PX4", "MAVSDK_SERVER_PORT", 50052),
    ("PX4", "EXTERNAL_MAVSDK_SERVER", False),
    ("MAVLink", "MAVLINK_HOST", "192.0.2.20"),
    ("MAVLink", "MAVLINK_PORT", 8089),
])
def test_sih_rejects_saved_external_command_or_telemetry_route(section, key, value):
    from classes.backend_supervisor import validate_sih_routes
    config = {"PX4": {"SYSTEM_ADDRESS": "udpin://127.0.0.1:14540", "EXTERNAL_MAVSDK_SERVER": True,
        "MAVSDK_SERVER_ADDRESS": "127.0.0.1", "MAVSDK_SERVER_PORT": 50051},
        "MAVLink": {"MAVLINK_ENABLED": True, "MAVLINK_HOST": "127.0.0.1", "MAVLINK_PORT": 8088}}
    config[section][key] = value
    with pytest.raises(ValueError, match="isolated loopback"):
        validate_sih_routes(config)
