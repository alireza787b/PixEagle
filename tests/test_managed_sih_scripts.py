import json
import os
from pathlib import Path
import stat
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = PROJECT_ROOT / "scripts" / "sitl" / "start_px4_sitl.sh"
STOP_SCRIPT = PROJECT_ROOT / "scripts" / "sitl" / "stop_px4_sitl.sh"
CONTAINER_ID = "a" * 64
IMAGE_ID = "sha256:" + "b" * 64
IMAGE_TAG = "px4io/px4-sitl:test"
IMAGE_DIGEST = "px4io/px4-sitl@sha256:" + "c" * 64
MODEL = "sihsim_quadx"


def write_plan(path: Path) -> None:
    path.write_text(
        json.dumps({
            "stack": {
                "px4": {
                    "recommended_image": IMAGE_TAG,
                    "expected_repo_digest": IMAGE_DIGEST,
                    "vehicle_model": MODEL,
                    "network_mode": "host",
                }
            }
        }),
        encoding="utf-8",
    )


def write_fake_docker(path: Path) -> None:
    path.write_text(
        f"""#!/bin/bash
set -u
printf '%s\\n' "$*" >> "$DOCKER_COMMAND_LOG"
scenario="${{DOCKER_SCENARIO:-start_success}}"

if [[ "$1" == "version" ]]; then
    echo 27.5.1
    exit 0
fi
if [[ "$1 $2" == "image inspect" ]]; then
    printf '["{IMAGE_DIGEST}"]\\n'
    exit 0
fi
if [[ "$1 $2" == "container inspect" ]]; then
    reference="${{@: -1}}"
    if [[ "$scenario" == "daemon_error" ]]; then
        echo 'Cannot connect to the Docker daemon' >&2
        exit 1
    fi
    if [[ "$scenario" == "absent" ]]; then
        echo 'Error: No such container' >&2
        exit 1
    fi
    if [[ "$reference" == "pixeagle-px4-sitl" && "$*" != *"--format"* ]]; then
        echo 'Error: No such container' >&2
        exit 1
    fi
    if [[ "$scenario" == "unowned" ]]; then
        printf '{CONTAINER_ID}|true|false|wrong-profile|run-test|{MODEL}|{IMAGE_DIGEST}\\n'
        exit 0
    fi
    if [[ "$*" == *"{{.Image}}"* ]]; then
        printf '{CONTAINER_ID}|true|{IMAGE_ID}|{IMAGE_DIGEST}|host|true|official_px4_sih|run-test|{MODEL}|{IMAGE_DIGEST}\\n'
    else
        printf '{CONTAINER_ID}|true|true|official_px4_sih|run-test|{MODEL}|{IMAGE_DIGEST}\\n'
    fi
    exit 0
fi
if [[ "$1" == "run" ]]; then
    echo {CONTAINER_ID}
    exit 0
fi
if [[ "$1" == "logs" ]]; then
    echo 'bounded initial PX4 log'
    exit 0
fi
if [[ "$1" == "stop" ]]; then
    echo {CONTAINER_ID}
    exit 0
fi
echo "unexpected docker invocation: $*" >&2
exit 2
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def fake_docker_environment(tmp_path: Path, scenario: str) -> tuple[dict, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_docker(bin_dir / "docker")
    command_log = tmp_path / "docker-commands.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DOCKER_COMMAND_LOG": str(command_log),
        "DOCKER_SCENARIO": scenario,
    }
    return env, command_log


def run_script(script: Path, args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_start_uses_plan_digest_resource_limits_and_bounded_artifacts(tmp_path):
    plan = tmp_path / "plan.json"
    artifact_dir = tmp_path / "run-test"
    write_plan(plan)
    env, command_log = fake_docker_environment(tmp_path, "start_success")

    result = run_script(
        START_SCRIPT,
        ["--plan", str(plan), "--artifact-dir", str(artifact_dir)],
        env,
    )

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    run_command = next(line for line in commands.splitlines() if line.startswith("run "))
    assert IMAGE_DIGEST in run_command
    assert IMAGE_TAG not in run_command
    assert "--pull=never" in run_command
    assert "--cpus 1.5" in run_command
    assert "--memory 1g" in run_command
    assert "--pids-limit 256" in run_command
    assert "--log-driver local" in run_command
    assert f"org.pixeagle.sitl.image_digest={IMAGE_DIGEST}" in run_command
    assert (artifact_dir / "logs" / "px4_sitl.initial.log").stat().st_size < 1_048_577
    assert IMAGE_DIGEST in (artifact_dir / "container.env").read_text(encoding="utf-8")


def test_stop_treats_absence_as_idempotent_success(tmp_path):
    env, command_log = fake_docker_environment(tmp_path, "absent")

    result = run_script(STOP_SCRIPT, [], env)

    assert result.returncode == 0
    assert "Container is absent" in result.stdout
    assert not any(
        line.startswith("stop ")
        for line in command_log.read_text(encoding="utf-8").splitlines()
    )


def test_stop_does_not_hide_docker_daemon_failure(tmp_path):
    env, _ = fake_docker_environment(tmp_path, "daemon_error")

    result = run_script(STOP_SCRIPT, [], env)

    assert result.returncode != 0
    assert "Cannot connect to the Docker daemon" in result.stderr


def test_stop_refuses_incomplete_ownership_labels(tmp_path):
    env, command_log = fake_docker_environment(tmp_path, "unowned")

    result = run_script(STOP_SCRIPT, [], env)

    assert result.returncode != 0
    assert "complete PixEagle SIH ownership contract" in result.stderr
    assert not any(
        line.startswith("stop ")
        for line in command_log.read_text(encoding="utf-8").splitlines()
    )


def test_stop_uses_only_the_verified_immutable_id(tmp_path):
    env, command_log = fake_docker_environment(tmp_path, "owned")

    result = run_script(STOP_SCRIPT, [], env)

    assert result.returncode == 0, result.stderr
    stop_commands = [
        line
        for line in command_log.read_text(encoding="utf-8").splitlines()
        if line.startswith("stop ")
    ]
    assert stop_commands == [f"stop --time 10 {CONTAINER_ID}"]
    assert "pixeagle-px4-sitl" not in stop_commands[0]
