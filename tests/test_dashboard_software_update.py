"""Stable updates use disposable Git repositories and never manage the host runtime."""

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from classes import api_v1_software_update as api
from classes import software_update as update
from classes.api_v1_contracts import APISoftwareUpdateRequest

PROJECT = Path(__file__).resolve().parents[1]


def commit(root, name):
    update.git(root, "add", "-A")
    update.git(
        root, "-c", "user.name=CI", "-c", "user.email=ci@example.invalid", "commit", "-qm", name
    )
    return update.git(root, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    update.git(root, "init", "-q")
    (root / ".gitignore").write_text(
        ".pixeagle_runtime/\nconfigs/config.yaml\nconfigs/config_sync_meta.json\ndashboard/.env\n"
    )
    for name in ("src", "configs", "scripts"):
        update.extract_source(PROJECT, "HEAD", root, name)
    for name in ("Makefile", "install.sh"):
        shutil.copyfile(PROJECT / name, root / name)
    for name in (
        "src/classes/software_update.py",
        "scripts/setup/release-settings.py",
        "scripts/release-maintenance.sh",
        "scripts/update.sh",
        "scripts/lib/sync.sh",
    ):
        dst = root / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / name, dst)
    (root / "scripts/init.sh").write_text(
        "#!/usr/bin/env bash\nset -eu\nstaged=configs/.config_default_preupdate.yaml\n"
        'if [[ -e "$staged" ]]; then\n'
        '"$PIXEAGLE_VENV_DIR/bin/python" scripts/setup/config-sync-status.py --initialize-baseline-from "$staged" --json >/dev/null\n'
        'rm -- "$staged"\nfi\n'
    )
    old = commit(root, "Installed release")
    (root / "version.txt").write_text("new")
    new = commit(root, "New release")
    tag = "v99.0.0"
    update.git(root, "tag", tag)
    origin = str(tmp_path / "official")
    update.git(root, "clone", "--bare", str(root), origin + ".git")
    monkeypatch.setattr(update, "REPOSITORY", origin)
    update.git(root, "checkout", "--detach", old)
    private = root / update.CONFIG
    shutil.copyfile(root / update.DEFAULTS, private)
    job_id = "a" * 32
    path = update.directory(root) / job_id
    path.mkdir()
    job = {
        "id": job_id,
        "commit": new,
        "old": old,
        "release": tag,
        "review": update.fingerprint(root, []),
        "changes": [],
        "save_edits": False,
        "python": sys.executable,
        "stage": "queued",
        "started": time.time(),
        "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    }
    update.write_json(path / "job.json", job)
    return root, path, job


def test_private_settings_preflight_and_approved_stash(installation):
    root, path, job = installation
    config = (root / update.CONFIG).read_bytes()
    (root / "local-note").write_text("an operator edit")
    rows = update.local_changes(root)
    job.update(review=update.fingerprint(root, rows), changes=["local-note"])
    with pytest.raises(update.UpdateError, match="back up"):
        update.check_review(root, job)
    job["save_edits"] = True
    assert update.prepare(root, path, job)
    assert (path / "driver/scripts/release-maintenance.sh").is_file()
    assert update.read_json(path / "settings-preview.json")["changes"] == []
    update.stash_reviewed(root, path, job)
    assert update.git(root, "show", "stash^3:local-note") == b"an operator edit"
    assert (root / update.CONFIG).read_bytes() == config
    assert update.git(root, "rev-parse", "HEAD").decode().strip() == job["old"]


def test_factory_edits_become_personal_settings_and_consent_expires(installation):
    root, path, job = installation
    private = root / update.CONFIG
    private.unlink()
    factory = root / update.DEFAULTS
    factory.write_bytes(factory.read_bytes() + b"\n# site-specific calibration\n")
    job.update(
        review=update.fingerprint(root, update.local_changes(root)),
        changes=[update.DEFAULTS],
        save_edits=True,
    )
    assert update.prepare(root, path, job)
    factory.write_bytes(factory.read_bytes() + b"# later edit\n")
    with pytest.raises(update.UpdateError, match="changed"):
        update.stash_reviewed(root, path, job)
    assert not private.exists()
    factory.write_bytes((path / "edited-defaults.yaml").read_bytes())
    update.stash_reviewed(root, path, job)
    assert private.read_bytes().endswith(b"# site-specific calibration\n")


def test_invalid_saved_value_requires_a_matching_review(installation):
    root, path, job = installation
    import yaml

    cfg = yaml.safe_load((root / update.CONFIG).read_text())
    cfg["Streaming"]["STREAM_FPS"] = -1000
    (root / update.CONFIG).write_text(yaml.safe_dump(cfg))
    job.update(review=update.fingerprint(root, []))
    assert not update.prepare(root, path, job)
    result = update.read_json(path / "job.json")
    assert result["stage"] == "review_settings"
    assert any(row["path"] == "Streaming.STREAM_FPS" for row in result["settings_changes"])
    assert yaml.safe_load((root / update.CONFIG).read_text())["Streaming"]["STREAM_FPS"] == -1000
    assert not (path / "permit.json").exists()
    assert update.prepare(root, path, dict(job, migration=result["migration"]))
    assert (
        yaml.safe_load((path / "prepared-config.yaml").read_text())["Streaming"]["STREAM_FPS"] > 0
    )


def test_preflight_offline_low_space_divergence_or_moved_tag(installation, monkeypatch):
    root, path, job = installation
    before = (root / update.CONFIG).read_bytes()
    with monkeypatch.context() as m:
        m.setattr(update.shutil, "disk_usage", lambda root: SimpleNamespace(free=1))
        with pytest.raises(update.UpdateError, match="Free"):
            update.prepare(root, path, job)
    with pytest.raises(update.UpdateError, match="release changed"):
        update.prepare(root, path, dict(job, commit="0" * 40))
    (root / "local-commit.txt").write_text("retained")
    job["old"] = commit(root, "diverged")
    job["review"] = update.fingerprint(root, [])
    with pytest.raises(update.UpdateError, match="separate"):
        update.prepare(root, path, job)
    assert before == (root / update.CONFIG).read_bytes()


@pytest.mark.parametrize(
    ("version", "state"),
    [("7.6.1", "ahead"), ("7.6.0", "ahead"), ("7.5.4", "current"), ("7.5.3", "available"), ("dev", "unknown")],
)
def test_stable_release_comparison(version, state):
    assert update.version_state(version, "v7.5.4") == state


def test_offline_keeps_last_success(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "release_metadata", lambda: {"tag": "v1.0.0", "commit": "a" * 40})
    first = update.cached_release(tmp_path)

    def offline():
        raise OSError("unreachable")

    monkeypatch.setattr(update, "release_metadata", offline)
    assert update.cached_release(tmp_path) == first
    first["attempt"] -= 86401
    update.write_json(update.directory(tmp_path) / "release.json", first)
    last = update.cached_release(tmp_path)
    assert last["error"] and last["checked"] == first["checked"] and last["tag"] == "v1.0.0"


def test_interruptions_do_not_replay_jobs(installation):
    root, path, job = installation
    update.write_json(path.parent / "current.json", job["id"])
    update.set_stage(path, "updating", boot="previous boot")
    assert update.current_job(root)["stage"] == "recovery_required"
    update.set_stage(path, "preparing", boot="previous boot")
    assert update.current_job(root)["stage"] == "failed"


@pytest.mark.parametrize("mode", ["manual", "service"])
@pytest.mark.parametrize("startup_fails", [False, True])
def test_worker_outcome_depends_on_verified_restart(tmp_path, monkeypatch, mode, startup_fails):
    root, path = tmp_path, tmp_path / "job"
    path.mkdir()
    update.write_json(
        path / "job.json",
        {
            "id": "test",
            "commit": "new",
            "old": "old",
            "mode": mode,
            "run_id": "original-run",
            "python": sys.executable,
            "profile": "full",
            "stage": "queued",
        },
    )
    update.write_json(path / "permit.json", time.time())
    monkeypatch.setattr(update, "prepare", lambda *args: True)
    events = []

    def command(args, root, output, env):
        events.append(args[2])
        if args[2] == "apply":
            (path / "shutdown-started").touch()
        assert env["PIXEAGLE_INSTALL_PROFILE"] == "full"

    def restart(root, path, job, revision, env, output):
        events.append((job["mode"], revision))
        if startup_fails and revision == "new":
            raise update.UpdateError("Dashboard unavailable")
        update.write_json(path / "ready.json", {"settings_pending": True})

    monkeypatch.setattr(update, "command", command)
    monkeypatch.setattr(update, "start_and_verify", restart)
    update.run_worker(root, path)
    if startup_fails:
        assert events == ["apply", (mode, "new"), "restore", (mode, "old")]
        assert update.read_json(path / "job.json")["stage"] == "restored"
    else:
        assert events == ["apply", (mode, "new")]
        assert update.read_json(path / "job.json")["stage"] == "updated"


def test_second_client_joins_current_job(installation, monkeypatch):
    root, path, job = installation
    update.write_json(path.parent / "current.json", job["id"])
    monkeypatch.setattr(api, "ROOT", root)
    monkeypatch.setattr(update, "release_status", lambda *a: {})
    request = APISoftwareUpdateRequest(
        commit=job["commit"], review=job["review"], confirm=True, idempotency_key="b" * 32
    )
    existing, spawned = api.queue_update(request, None, None)
    assert existing["id"] == job["id"] and not spawned


@pytest.mark.asyncio
async def test_runtime_guard_rechecked_at_handoff(installation, monkeypatch):
    root, path, job = installation
    monkeypatch.setattr(api, "ROOT", root)
    monkeypatch.setattr(api, "eligibility", lambda *a: "Aircraft state changed")
    update.write_json(path / "prepared.json", True)

    async def run(callback):
        await callback()

    owner = SimpleNamespace(
        app_controller=SimpleNamespace(
            _follower_state_lock=asyncio.Lock(), _run_on_flight_event_loop=run
        )
    )
    await api.authorize_cutover(owner, None, job)
    assert (path / "denied.json").exists()
    assert not (path / "permit.json").exists()


def test_pinned_shell_transaction_and_restore(installation, tmp_path):
    """Use the real Git, resource locks, candidate and rollback code with a local release."""
    root, path, job = installation
    (root / "lab-profile.yaml").write_text("bench: true\n")
    (root / "developer-note.txt").write_text("keep these edits")
    job.update(
        review=update.fingerprint(root, update.local_changes(root)),
        changes=["developer-note.txt"],
        save_edits=True,
        profile="core",
    )
    update.write_json(path / "job.json", job)
    assert update.prepare(root, path, job)
    bin_dir = tmp_path / "test-bin"
    bin_dir.mkdir()
    shims = {
        "systemctl": "echo LoadState=not-found",
        "lsof": "exit 1",
        "tmux": "exit 1",
        "sudo": "exit 1",
        # Only the network transport is substituted. Ref selection, object
        # resolution, tag pinning and publication still use real Git.
        "git": """args=("$@")
if [[ " ${args[*]} " == *" fetch "* ]]; then
    for i in "${!args[@]}"; do
        if [[ "${args[i]}" == https://github.com/alireza787b/PixEagle.git ]]; then
            args[i]="$TEST_OFFICIAL_GIT"
        fi
    done
fi
exec /usr/bin/git "${args[@]}"
""",
    }
    for filename, body in shims.items():
        script = bin_dir / filename
        script.write_text("#!/usr/bin/env bash\n" + body + "\n")
        script.chmod(0o700)
    fixture_venv = tmp_path / "venv"
    (fixture_venv / "bin").mkdir(parents=True)
    python = fixture_venv / "bin/python"
    python.write_text('#!/bin/sh\nexec "' + sys.executable + '" "$@"\n')
    python.chmod(0o700)
    env = {
        **os.environ,
        "PATH": str(bin_dir) + ":" + os.environ["PATH"],
        "TEST_OFFICIAL_GIT": str(tmp_path / "official.git"),
        "PIXEAGLE_VENV_DIR": str(fixture_venv),
        "PIXEAGLE_INSTALL_PROFILE": "core",
        "PIXEAGLE_NONINTERACTIVE": "1",
        "PIXEAGLE_UPDATE_STOP_RUNTIME": "0",
    }
    before = (root / update.CONFIG).read_bytes()
    for operation, head in [("apply", job["commit"]), ("restore", job["old"])]:
        result = subprocess.run(
            [
                "bash",
                str(path / "driver/scripts/release-maintenance.sh"),
                operation,
                str(path),
                sys.executable,
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert update.git(root, "rev-parse", "HEAD").decode().strip() == head
        assert (root / update.CONFIG).read_bytes() == before
        assert (root / "lab-profile.yaml").read_text() == "bench: true\n"
    assert update.git(root, "show", "stash^3:developer-note.txt") == b"keep these edits"


@pytest.mark.parametrize("serve_release_dashboard", [True, False])
def test_health_checks_observed_backend_and_exact_served_dashboard(
    tmp_path, monkeypatch, serve_release_dashboard
):
    import hashlib
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    root, work = tmp_path, tmp_path / "job"
    work.mkdir()
    for name in ("scripts/lib", "configs", "dashboard/build"):
        (root / name).mkdir(parents=True)
    shutil.copyfile(PROJECT / "scripts/lib/ports.sh", root / "scripts/lib/ports.sh")
    index = b"<html>current release</html>"
    (root / "dashboard/build/index.html").write_bytes(index)
    hits = []

    class Http(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            if self.path.endswith("/auth/session"):
                self.wfile.write(b'{"auth_mode":"local_compat"}')
            else:
                self.wfile.write(index if serve_release_dashboard else b"<html>old build</html>")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Http)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        port = server.server_port
        (root / "dashboard/.env").write_text(f"PORT={port}\n")
        config = f"Streaming:\n  HTTP_STREAM_PORT: {port}\n".encode()
        (root / update.CONFIG).write_bytes(config)
        job = {"mode": "manual", "release": "v2.0.0", "commit": "new"}
        update.write_json(work / "settings-preview.json", {"effective": "effective-digest"})

        def started(*args, **kwargs):
            update.write_json(
                work / "ready.json",
                {
                    "version": "2.0.0",
                    "commit": "new",
                    "config": hashlib.sha256(config).hexdigest(),
                    "effective": "effective-digest",
                },
            )

        monkeypatch.setattr(update, "command", started)
        # Advance this module's deadline without changing the HTTP server's clock.
        clock = iter((0, 1, 121))
        monkeypatch.setattr(
            update, "time", SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None)
        )
        if serve_release_dashboard:
            update.start_and_verify(root, work, job, "new", {}, None)
        else:
            with pytest.raises(update.UpdateError, match="did not confirm"):
                update.start_and_verify(root, work, job, "new", {}, None)
        assert hits == ["/api/v1/auth/session", "/"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.skipif(
    os.environ.get("PIXEAGLE_TEST_USER_SYSTEMD") != "1", reason="opt-in Linux user service test"
)
def test_independent_user_worker_prepares_review_after_caller_exits(
    installation, tmp_path, monkeypatch
):
    """A real transient user service stops at migration review, before any runtime operation."""
    import uuid

    import yaml

    root, path, job = installation
    # Avoid a transient unit name collision with another concurrent test.
    job["id"] = uuid.uuid4().hex
    work = path.with_name(job["id"])
    path.rename(work)
    private = root / update.CONFIG
    settings = yaml.safe_load(private.read_text())
    settings["Streaming"]["STREAM_FPS"] = -1000
    private.write_text(yaml.safe_dump(settings))
    before = private.read_bytes()
    job.update(mode="manual", run_id="fixture", profile="core", review=update.fingerprint(root, []))
    update.write_json(work / "job.json", job)
    update.write_json(work.parent / "current.json", job["id"])
    bin_dir = tmp_path / "fetch-local"
    bin_dir.mkdir()
    shim = bin_dir / "git"
    shim.write_text("""#!/usr/bin/env bash
args=("$@")
if [[ "$1" == fetch ]]; then
    for i in "${!args[@]}"; do
        if [[ "${args[i]}" == https://github.com/alireza787b/PixEagle.git ]]; then
            args[i]="$PWD/../official.git"
        fi
    done
fi
exec /usr/bin/git "${args[@]}"
""")
    shim.chmod(0o700)
    monkeypatch.setattr(api, "ROOT", root)
    monkeypatch.setenv("PATH", str(bin_dir) + ":" + os.environ["PATH"])
    args, env = api.worker_command("manual", job["id"], work)
    assert args[:2] == ["systemd-run", "--user"]
    subprocess.run(args, env=env, check=True, timeout=10)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        state = update.current_job(root)
        if state["stage"] in update.TERMINAL:
            break
        time.sleep(0.1)
    assert state["stage"] == "review_settings", (work / "worker.log").read_text()
    assert private.read_bytes() == before
    assert update.git(root, "rev-parse", "HEAD").decode().strip() == job["old"]


def test_asgi_startup_attests_effective_settings_and_holds_mutations(installation, monkeypatch):
    import fcntl
    import logging

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from classes.config_service import ConfigService
    from classes.fastapi_handler import FastAPIHandler

    root, work, job = installation
    assert update.prepare(root, work, job)
    update.write_json(work.parent / "current.json", job["id"])
    update.set_stage(work, "restarting")
    monkeypatch.setattr(api, "ROOT", root)
    service = ConfigService(root)
    monkeypatch.setattr(ConfigService, "get_instance", classmethod(lambda cls: service))
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.logger = logging.getLogger(__name__)
    app = FastAPI(lifespan=handler._update_lifespan)
    with (work / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with TestClient(app):
            assert handler._software_update_barrier == work
            ready = update.read_json(work / "ready.json")
            assert ready["commit"] == job["old"]
            assert ready["config"] == update.file_digest(root / update.CONFIG)
            assert (
                ready["effective"] == update.read_json(work / "settings-preview.json")["effective"]
            )
