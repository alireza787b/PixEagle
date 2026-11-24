"""Stable-release discovery and the independent Linux maintenance worker.

The worker also runs during Python environment reconciliation. Keep its
top-level imports in the standard library and persist state outside Git.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "https://github.com/alireza787b/PixEagle"
LATEST = "https://api.github.com/repos/alireza787b/PixEagle/releases/latest"
DEFAULTS = "configs/config_default.yaml"
CONFIG = "configs/config.yaml"
TERMINAL = {"updated", "restored", "failed", "recovery_required", "review_settings"}
_cache_lock = threading.Lock()


class UpdateError(Exception):
    """An operator-readable maintenance error."""


def directory(root):
    path = root / ".pixeagle_runtime" / "updates"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def write_json(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if sys.platform == "linux":
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
    finally:
        Path(name).unlink(missing_ok=True)


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def git(root, *args, timeout=30):
    return subprocess.check_output(
        ["git", *args],
        cwd=root,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def release_metadata():
    request = Request(
        LATEST, headers={"Accept": "application/vnd.github+json", "User-Agent": "PixEagle-updater"}
    )
    with urlopen(request, timeout=8) as response:
        data = json.loads(response.read(2_000_000))
    tag = data.get("tag_name", "")
    if (
        not re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", tag)
        or data.get("draft") is not False
        or data.get("prerelease") is not False
    ):
        raise UpdateError("The official repository has no eligible stable release.")
    ref = "refs/tags/" + tag
    # Annotated tags name tag objects. The reviewed identity is the peeled commit.
    remote = REPOSITORY + ".git"
    if git(ROOT, "ls-remote", "--get-url", remote).decode().strip() != remote:
        raise UpdateError("Local Git configuration redirects the official repository.")
    rows = git(ROOT, "ls-remote", "--tags", remote, ref, ref + "^{}", timeout=12)
    refs = {name: sha for sha, name in (line.split() for line in rows.decode().splitlines())}
    commit = refs.get(ref + "^{}", refs.get(ref, ""))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise UpdateError("The published tag could not be verified.")
    return {"tag": tag, "commit": commit, "notes": REPOSITORY + "/releases/tag/" + tag}


def cached_release(root, refresh=False):
    path = directory(root) / "release.json"
    with _cache_lock:
        cache = read_json(path, {})
        now = time.time()
        elapsed = now - cache.get("attempt", 0)
        ttl = 2 if refresh else 60 if cache.get("error") else 86400
        if 0 <= elapsed < ttl:
            return cache
        try:
            cache = {**release_metadata(), "checked": now}
        except (OSError, ValueError, subprocess.SubprocessError, UpdateError):
            cache["error"] = (
                "Could not check GitHub. Check the device’s internet connection and try again."
            )
        cache["attempt"] = now
        write_json(path, cache)
        return cache


def file_digest(path):
    if path.is_symlink():
        return "link:" + os.readlink(path)
    if not path.exists():
        return "absent"
    if not path.is_file():
        raise UpdateError("Review the local directory or submodule changes before updating.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_changes(root):
    result = git(root, "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all")
    rows = []
    for entry in result.split(b"\0"):
        if entry:
            rows.append((entry[:2].decode(), os.fsdecode(entry[3:])))
    return rows


def preserved_config(status, name):
    path = Path(name)
    return status == "??" and (
        path.suffix.lower() in {".yaml", ".yml"}
        or path.name == ".env"
        or path.name.startswith(".env.")
    )


def fingerprint(root, rows):
    # Bind consent to the staged and working copies, including untracked bytes.
    digest = hashlib.sha256(git(root, "diff", "--cached", "--raw", "--no-abbrev"))
    for status, name in rows:
        digest.update(json.dumps([status, name, file_digest(root / name)]).encode())
    digest.update(file_digest(root / CONFIG).encode())
    digest.update(git(root, "rev-parse", "HEAD"))
    return digest.hexdigest()


def local_profile():
    # The supported launcher may use either .venv or venv.
    marker = Path(sys.prefix) / ".pixeagle-install-profile"
    if not marker.is_file():
        return None
    value = marker.read_text().strip()
    return value if value in {"core", "full"} else None


def current_job(root):
    path = directory(root)
    job_id = read_json(path / "current.json")
    if job_id and not re.fullmatch("[0-9a-f]{32}", job_id):
        raise UpdateError("The saved update record is invalid.")
    if not job_id:
        return None
    work = path / job_id
    job = read_json(work / "job.json")
    if not job or job["stage"] in TERMINAL or sys.platform != "linux":
        return job
    # The transient unit is never replayed at boot. flock is released by the
    # kernel even on SIGKILL; avoid displaying a running job indefinitely.
    import fcntl

    same_boot = job["boot"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if same_boot and job["stage"] == "queued" and time.time() - job["started"] < 45:
        return job
    with (work / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return job
        job = read_json(work / "job.json")
        if job["stage"] in TERMINAL:
            return job
        changed = job["stage"] in {"updating", "restarting", "restoring"}
        return set_stage(
            work,
            "recovery_required" if changed else "failed",
            "The update worker was interrupted. Check the installation before retrying.",
        )


def version_state(installed, tag):
    from packaging.version import InvalidVersion, Version

    try:
        current, latest = Version(installed), Version(tag)
    except InvalidVersion:
        return "unknown"
    return "available" if current < latest else "ahead" if current > latest else "current"


def release_status(root, installed, refresh=False, *, inspect_checkout=True):
    release = cached_release(root, refresh)
    state = version_state(installed, release["tag"]) if release.get("tag") else "unknown"
    if (
        state == "current"
        and (root / ".git").exists()
        and git(root, "rev-parse", "HEAD").decode().strip() != release.get("commit")
    ):
        state = "different"
    changes, review, error = [], None, release.get("error")
    if inspect_checkout and state == "available" and (root / ".git").exists():
        try:
            rows = local_changes(root)
            changes = [name for status, name in rows if not preserved_config(status, name)]
            review = fingerprint(root, rows)
        except (OSError, UpdateError, subprocess.SubprocessError):
            error = (
                "Could not review working files. Check for unreadable files or modified submodules."
            )
    return {
        "installed": installed,
        "state": state,
        "release": release.get("tag"),
        "commit": release.get("commit"),
        "notes": release.get("notes"),
        "checked": release.get("checked"),
        "error": error,
        "changes": changes,
        "review": review,
    }


def set_stage(path, stage, message=None, **changes):
    job = read_json(path / "job.json")
    job.update(stage=stage, message=message, **changes)
    write_json(path / "job.json", job)
    return job


def check_review(root, job):
    rows = local_changes(root)
    if fingerprint(root, rows) != job["review"]:
        raise UpdateError("Local files changed. Review the update again.")
    if any(not preserved_config(*row) for row in rows) and not job["save_edits"]:
        raise UpdateError("Review and back up your local edits before updating.")
    protected = (
        "configs/secrets/",
        "configs/backups/",
        "dashboard/backups/",
        "models/",
        "recordings/",
        "logs/",
    )
    for _, name in rows:
        if name in (CONFIG, "dashboard/.env", "configs/config_sync_meta.json") or name.startswith(
            protected
        ):
            raise UpdateError(
                "A private runtime file is tracked by Git. Remove it from source control before updating."
            )
    return rows


def extract_source(root, revision, destination, *paths):
    destination.mkdir(exist_ok=True)
    archive = destination / "source.tar"
    git(root, "archive", "--output=" + str(archive), revision, *paths)
    with tarfile.open(archive) as tar:
        tar.extractall(destination, filter="data")
    archive.unlink()


def prepare(root, path, job):
    check_review(root, job)
    if shutil.disk_usage(root).free < 512 * 1024**2:
        raise UpdateError("Free at least 512 MiB before preparing this update.")
    remote = REPOSITORY + ".git"
    if git(root, "ls-remote", "--get-url", remote).decode().strip() != remote:
        raise UpdateError("Local Git configuration redirects the official repository.")
    git(
        root,
        "fetch",
        "--no-tags",
        "--no-recurse-submodules",
        remote,
        "refs/tags/" + job["release"],
        timeout=180,
    )
    if job.get("signed"):
        git(root, "verify-commit", job["commit"])
    if git(root, "rev-parse", "FETCH_HEAD^{commit}").decode().strip() != job["commit"]:
        raise UpdateError("The release changed. Check for updates again.")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", job["old"], job["commit"]], cwd=root, check=False
    ).returncode:
        raise UpdateError(
            "This installation has a separate Git history. Your local commits are preserved."
        )
    set_stage(path, "preparing")
    # Run the candidate's own configuration loader before interrupting the runtime.
    with tempfile.TemporaryDirectory(dir=path) as temporary:
        checkout = Path(temporary)
        extract_source(root, job["commit"], checkout, "src", "configs")
        # Keep the previous transaction driver outside the checkout. A broken
        # candidate must not get to supply its own source recovery code.
        extract_source(
            root, job["old"], path / "driver", "scripts", "src/classes/software_update.py"
        )
        if subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; _target_tree_preserves_untracked_paths "$2" "$3"',
                "release-preflight",
                str(path / "driver/scripts/lib/sync.sh"),
                job["old"],
                job["commit"],
            ],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode:
            raise UpdateError(
                "An incoming source file would replace local data. Review local files before updating."
            )
        source = root / CONFIG
        if source.is_symlink() or (root / DEFAULTS).is_symlink():
            raise UpdateError("The settings backup requires regular files.")
        defaults_edited = DEFAULTS in job["changes"]
        if defaults_edited:
            (path / "original-defaults.yaml").write_bytes(git(root, "show", "HEAD:" + DEFAULTS))
            shutil.copyfile(root / DEFAULTS, path / "edited-defaults.yaml")
            if not source.exists():
                source = root / DEFAULTS
        check = subprocess.run(
            [
                job["python"],
                str(path / "driver/scripts/setup/release-settings.py"),
                str(source),
                str(path),
            ],
            cwd=checkout,
            env={**os.environ, "PYTHONPATH": str(checkout / "src")},
            capture_output=True,
            check=False,
            timeout=90,
        )
        if check.returncode:
            (path / "settings-check.log").write_bytes(check.stderr)
            raise UpdateError(
                "The release could not validate these settings. Open Settings to review them. Details are in the private settings-check.log."
            )
        preview = read_json(path / "settings-preview.json")
        if preview["changes"] and preview["digest"] != job.get("migration"):
            set_stage(
                path,
                "review_settings",
                "These saved values need to change for this release.",
                migration=preview["digest"],
                settings_changes=preview["changes"],
            )
            return False
    check_review(root, job)
    for name in (CONFIG, "configs/config_sync_meta.json", DEFAULTS):
        source = root / name
        if source.is_symlink():
            raise UpdateError("The settings backup requires regular files.")
        if source.is_file():
            shutil.copyfile(source, path / source.name)
    write_json(path / "prepared.json", True)
    return True


def stash_reviewed(root, path, job):
    rows = check_review(root, job)
    if any(not preserved_config(*row) for row in rows):
        # Exclude only untracked personal settings. A tracked YAML source edit
        # still belongs in the reviewed stash.
        exclusions = [
            ":(top,exclude,literal)" + name
            for status, name in rows
            if preserved_config(status, name)
        ]
        git(
            root,
            "-c",
            "user.name=PixEagle updater",
            "-c",
            "user.email=updater@localhost",
            "stash",
            "push",
            "--include-untracked",
            "--message",
            "PixEagle software update " + job["id"],
            "--",
            ".",
            *exclusions,
        )
        stash = git(root, "rev-parse", "refs/stash").decode().strip()
        set_stage(path, "updating", stash=stash)
    prepared, current = path / "prepared-config.yaml", root / CONFIG
    if prepared.is_file() and file_digest(prepared) != file_digest(current):
        with tempfile.NamedTemporaryFile(dir=current.parent, delete=False) as temp:
            temp.write(prepared.read_bytes())
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp.name, current)
        write_json(path / "config-written.json", file_digest(prepared))


def command(args, root, output, env, timeout=3600):
    with subprocess.Popen(
        args,
        cwd=root,
        env=env,
        stdout=output,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    ) as process:
        try:
            result = process.wait(timeout)
        except subprocess.TimeoutExpired:
            # Notify the lock supervisor as well as its shell wrapper. The
            # supervisor owns and drains its setup descendants on termination.
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raise
        if result:
            raise subprocess.CalledProcessError(result, args)


def start_and_verify(root, path, job, commit, env, output):
    (path / "ready.json").unlink(missing_ok=True)
    start = (
        ["sudo", "-n", "systemctl", "start", "pixeagle.service"]
        if job["mode"] == "service"
        else ["bash", "scripts/run.sh", "--no-attach"]
    )
    command(start, root, output, env, timeout=600)
    expected = (
        read_json(path / "settings-preview.json")["effective"]
        if commit == job["commit"]
        else job["previous_effective"]
    )
    version = job["release"].lstrip("v") if commit == job["commit"] else job["previous_version"]
    index = root / "dashboard/build/index.html"
    dashboard_digest = file_digest(index)
    # Resolve the ports from the checkout being started, including on rollback.
    ports = root / "scripts/lib/ports.sh"

    def local_url(option, settings, suffix):
        port = int(
            subprocess.check_output(["bash", str(ports), option, str(root / settings)], cwd=root)
        )
        return f"http://127.0.0.1:{port}{suffix}"

    backend = local_url("--backend-port", CONFIG, "/api/v1/auth/session")
    dashboard = local_url("--dashboard-port", "dashboard", "/")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready = read_json(path / "ready.json", {})
        if (
            ready.get("commit") == commit
            and ready.get("version") == version
            and ready.get("effective") == expected
            and ready.get("config") == file_digest(root / CONFIG)
        ):
            try:
                with urlopen(backend, timeout=2) as reply:
                    session = json.loads(reply.read(65536))
                    backend_ready = (
                        reply.status == 200 and isinstance(session, dict) and "auth_mode" in session
                    )
                if backend_ready:
                    with urlopen(dashboard, timeout=2) as reply:
                        if (
                            reply.status == 200
                            and hashlib.sha256(reply.read(1_000_000)).hexdigest()
                            == dashboard_digest
                        ):
                            return
            except (OSError, ValueError):
                pass
        time.sleep(1)
    raise UpdateError("The new runtime did not confirm its commit, configuration and Dashboard.")


def publish_ready(root):
    """Called during startup, after the runtime configuration has loaded."""
    if not (root / ".pixeagle_runtime/updates/current.json").is_file():
        return
    job = current_job(root)
    if job and job["stage"] in {"restarting", "restoring"}:
        from classes.app_version import PIXEAGLE_VERSION
        from classes.config_service import ConfigService
        from classes.config_sync import build_defaults_sync_report

        service = ConfigService.get_instance()
        effective = json.dumps(
            service.get_startup_effective_config(), sort_keys=True, allow_nan=False
        ).encode()
        write_json(
            directory(root) / job["id"] / "ready.json",
            {
                "effective": hashlib.sha256(effective).hexdigest(),
                "version": PIXEAGLE_VERSION,
                "run_id": os.environ.get("PIXEAGLE_RUN_ID"),
                "commit": git(root, "rev-parse", "HEAD").decode().strip(),
                "config": file_digest(root / CONFIG),
                "settings_pending": bool(
                    build_defaults_sync_report(service)["counts"]["actionable"]
                ),
            },
        )
        return directory(root) / job["id"]
    return None


def run_worker(root, path):
    job = read_json(path / "job.json")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PIXEAGLE_", "WATCHDOG_", "NOTIFY_SOCKET"))
    }
    env.update(
        PIXEAGLE_INSTALL_PROFILE=job["profile"],
        PIXEAGLE_NONINTERACTIVE="1",
        PIXEAGLE_UPDATE_EXPECTED_RUN=job["run_id"],
        PIXEAGLE_UPDATE_EXPECTED_MODE=job["mode"],
        PIXEAGLE_UPDATE_STOP_RUNTIME="1",
        GIT_TERMINAL_PROMPT="0",
        PIXEAGLE_VENV_DIR=str(Path(job["python"]).parent.parent),
        PIXEAGLE_UPDATE_REQUIRE_SIGNED_COMMIT="1" if job.get("signed") else "0",
    )
    wrapper = ["bash", str(path / "driver/scripts/release-maintenance.sh")]
    cutover = False
    with (path / "worker.log").open("a") as output:
        try:
            set_stage(path, "downloading")
            if not prepare(root, path, job):
                return
            deadline = time.monotonic() + 30
            while not (path / "permit.json").exists():
                if time.monotonic() > deadline or (path / "denied.json").exists():
                    raise UpdateError(
                        "Readiness changed before restart. Check device status and try again."
                    )
                time.sleep(0.2)
            if time.time() - read_json(path / "permit.json") > 5:
                raise UpdateError("Restart permission expired. Check device status and retry.")
            set_stage(path, "updating")
            cutover = True
            command([*wrapper, "apply", str(path), "/usr/bin/python3"], root, output, env)
            set_stage(path, "restarting")
            start_and_verify(root, path, job, job["commit"], env, output)
            ready = read_json(path / "ready.json")
            set_stage(path, "updated", settings_pending=ready["settings_pending"])
        except Exception as exc:  # noqa: BLE001 - transaction boundary must attempt recovery
            message = (
                str(exc)
                if isinstance(exc, UpdateError)
                else "Update failed. See the maintenance log on the device."
            )
            print(f"{type(exc).__name__}: {exc}", file=output, flush=True)
            if not cutover or not (path / "shutdown-started").is_file():
                set_stage(path, "failed", message)
                return
            try:
                set_stage(path, "restoring", message)
                ready = read_json(path / "ready.json", {})
                env["PIXEAGLE_UPDATE_EXPECTED_RUN"] = ready.get("run_id") or job["run_id"]
                command([*wrapper, "restore", str(path), "/usr/bin/python3"], root, output, env)
                start_and_verify(root, path, job, job["old"], env, output)
                set_stage(path, "restored", message)
            except Exception as recovery_error:  # noqa: BLE001 - persist terminal failure
                print(f"Recovery failed: {recovery_error}", file=output, flush=True)
                set_stage(
                    path,
                    "recovery_required",
                    "Automatic recovery could not be verified. Open the recovery guide.",
                )


def transaction(root, path, operation):
    job = read_json(path / "job.json")
    env = {**os.environ, "PIXEAGLE_INSTALL_PROFILE": job["profile"]}
    if operation == "apply":
        stash_reviewed(root, path, job)
        write_json(path / "reconciliation-started.json", True)
        subprocess.run(
            [
                "bash",
                "scripts/update.sh",
                "--internal-update",
                "--release-tag",
                job["release"],
                "--commit",
                job["commit"],
            ],
            cwd=root,
            env=env,
            check=True,
        )
        return
    head = git(root, "rev-parse", "HEAD").decode().strip()
    if head not in {job["old"], job["commit"]}:
        raise UpdateError("The checkout changed during recovery.")
    if head != job["old"]:
        subprocess.run(
            [
                "bash",
                str(path / "driver/scripts/release-maintenance.sh"),
                "rollback-source",
                job["old"],
                head,
            ],
            cwd=root,
            env=env,
            check=True,
        )
    for name in (CONFIG, "configs/config_sync_meta.json"):
        if name != CONFIG and not (path / "reconciliation-started.json").exists():
            continue
        if name == CONFIG:
            written = read_json(path / "config-written.json")
            if not written:
                continue
            if written != file_digest(root / CONFIG):
                raise UpdateError(
                    "Settings were edited during recovery. The newer edit was preserved."
                )
        backup, current = path / Path(name).name, root / name
        if backup.exists():
            with tempfile.NamedTemporaryFile(dir=current.parent, delete=False) as temp:
                temp.write(backup.read_bytes())
            os.replace(temp.name, current)
        elif name == CONFIG and (path / "edited-defaults.yaml").is_file():
            # The original checkout used edited defaults; its code edits remain in the stash.
            with tempfile.NamedTemporaryFile(dir=current.parent, delete=False) as temp:
                temp.write((path / "edited-defaults.yaml").read_bytes())
            os.replace(temp.name, current)
        else:
            current.unlink(missing_ok=True)
    subprocess.run(
        ["bash", "scripts/init.sh"],
        cwd=root,
        env={**env, "PIXEAGLE_SETUP_ACTION": "update-repair"},
        check=True,
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Internal maintenance worker requires an operation and job directory.")
    operation, job_path = sys.argv[1], Path(sys.argv[2]).resolve()
    checkout_root = Path.cwd().resolve()
    if job_path.parent != directory(checkout_root) or not re.fullmatch(
        "[a-f0-9]{32}", job_path.name
    ):
        raise SystemExit("Invalid maintenance job")
    if operation == "worker":
        import fcntl

        with (job_path / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (
                read_json(job_path.parent / "current.json") == job_path.name
                and read_json(job_path / "job.json")["stage"] == "queued"
            ):
                run_worker(checkout_root, job_path)
    elif operation in {"apply", "restore"}:
        transaction(checkout_root, job_path, operation)
    else:
        raise SystemExit("Unknown maintenance operation")
