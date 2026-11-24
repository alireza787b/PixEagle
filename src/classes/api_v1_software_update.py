"""Dashboard maintenance API. The request process never stops its own service."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from classes import software_update as updates
from classes.api_v1_actions import get_system_restart_availability
from classes.api_v1_errors import build_api_v1_error_response
from classes.app_version import PIXEAGLE_VERSION

ROOT = updates.ROOT


def eligibility(owner, http_request):
    if sys.platform != "linux" or os.geteuid() == 0:
        return "Use the standard Linux launcher under the installation owner."
    if os.environ.get("PIXEAGLE_RUNTIME_MODE") not in {"service", "manual"} or os.environ.get(
        "PIXEAGLE_PROJECT_ROOT"
    ) != str(ROOT):
        return "Open the Dashboard from the installed service or standard Linux launcher."
    if not os.environ.get("PIXEAGLE_RUN_ID"):
        return "The runtime identity is unavailable. Use the standard launcher."
    if not updates.local_profile():
        return "Run the normal setup or update once to record this installation’s Core or Full profile."
    permitted = get_system_restart_availability(owner, http_request)
    if not permitted["available"]:
        reasons = {
            "system_admin_principal_required": "Sign in as an administrator to install updates.",
            "restart_policy_denied": "Open the Dashboard from a connection allowed to restart this device.",
            "aircraft_not_confirmed_disarmed": "Wait until the connected aircraft is confirmed disarmed.",
            "following_or_offboard_active": "Finish the active operation before updating.",
            "target_active": "Stop tracking before updating.",
            "leave_smart_before_apply": "Leave Smart tracking before updating.",
        }
        return reasons.get(permitted["reason"], permitted["reason"].replace("_", " ").capitalize())
    return None


def public_job(job):
    if not job:
        return None
    return {
        k: job.get(k)
        for k in (
            "id",
            "stage",
            "message",
            "started",
            "release",
            "stash",
            "settings_pending",
            "migration",
            "settings_changes",
        )
    }


def status_snapshot(owner, http_request, refresh=False):
    job = updates.current_job(ROOT)
    active = job and job["stage"] not in updates.TERMINAL
    reason = eligibility(owner, http_request) if not active else None
    principal = getattr(http_request.state, "api_principal", None)
    admin = "system:admin" in (getattr(principal, "scopes", ()) or ())
    result = updates.release_status(
        ROOT,
        PIXEAGLE_VERSION,
        refresh and not active,
        inspect_checkout=not active and not reason and admin,
    )
    if reason:
        result["changes"] = []
        result["review"] = None
    visible_job = public_job(job)
    if visible_job and not admin:
        for field in ("settings_changes", "migration", "stash"):
            visible_job.pop(field, None)
    if job and job["stage"] == "recovery_required":
        reason = "Review the installation and finish host recovery before another update."
    result.update(blocked=reason, job=visible_job)
    return result


def worker_command(mode, job_id, path):
    # A new session alone remains inside pixeagle.service's cgroup. A transient
    # unit survives stopping both the backend supervisor and the Dashboard.
    runtime = "/run/user/" + str(os.getuid())
    env = {
        **os.environ,
        "XDG_RUNTIME_DIR": runtime,
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + runtime + "/bus",
    }
    user_bus = (
        Path(runtime, "bus").is_socket()
        and subprocess.run(
            ["systemctl", "--user", "show-environment"],
            env=env,
            timeout=5,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    args = (
        ["systemd-run", "--user"]
        if user_bus
        else ["sudo", "-n", "systemd-run", "--uid=" + str(os.getuid()), "--gid=" + str(os.getgid())]
    )
    # Keep a freshly launched manual tmux server alive after the worker exits.
    if mode == "manual":
        args.append("--property=ExitType=cgroup")
    if (
        mode == "service"
        and subprocess.run(
            [
                "bash",
                "-c",
                'source "$1" && PIXEAGLE_NONINTERACTIVE=1 pixeagle_sudo_validate',
                "pixeagle-update",
                str(ROOT / "scripts/lib/common.sh"),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
            check=False,
        ).returncode
    ):
        raise updates.UpdateError(
            "The installation owner lacks unattended service maintenance permission. Use the host updater."
        )
    args.extend(
        [
            "--collect",
            "--quiet",
            "--unit=pixeagle-update-" + job_id,
            "--working-directory=" + str(ROOT),
            "--setenv=HOME=" + str(Path.home()),
            "--setenv=PATH=" + os.environ.get("PATH", os.defpath),
            "/usr/bin/python3",
            str(ROOT / "src/classes/software_update.py"),
            "worker",
            str(path),
        ]
    )
    return args, env


def queue_update(request, owner, http_request):
    if sys.platform != "linux":
        raise updates.UpdateError("Software installation from the Dashboard requires Linux.")
    import fcntl

    base = updates.directory(ROOT)
    with (base / "queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = updates.current_job(ROOT)
        if existing and (
            existing["id"] == request.idempotency_key or existing["stage"] not in updates.TERMINAL
        ):
            return existing, False
        path = base / request.idempotency_key
        if path.exists():
            return updates.read_json(path / "job.json"), False
        if existing and existing["stage"] == "recovery_required":
            raise updates.UpdateError(
                "Review the previous recovery on the host before starting another update."
            )
        reason = eligibility(owner, http_request)
        if reason:
            raise updates.UpdateError(reason)
        result = updates.release_status(ROOT, PIXEAGLE_VERSION)
        if (
            result["error"]
            or result["state"] != "available"
            or request.commit != result["commit"]
            or request.review != result["review"]
        ):
            raise updates.UpdateError("The update preview changed. Check for updates again.")
        if result["changes"] and not request.save_edits:
            raise updates.UpdateError("Review the local edits and confirm their backup.")
        mode = os.environ["PIXEAGLE_RUNTIME_MODE"]
        args, env = worker_command(mode, request.idempotency_key, path)
        config_service = owner._get_config_service()
        with config_service.mutation_guard():
            effective, _, _ = config_service._read_persisted_effective_config_locked()
        job = {
            "previous_effective": hashlib.sha256(
                json.dumps(effective, sort_keys=True, allow_nan=False).encode()
            ).hexdigest(),
            "previous_version": PIXEAGLE_VERSION,
            "migration": request.migration,
            "signed": os.environ.get("PIXEAGLE_UPDATE_REQUIRE_SIGNED_COMMIT") == "1",
            "id": request.idempotency_key,
            "stage": "queued",
            "started": time.time(),
            "release": result["release"],
            "commit": result["commit"],
            "review": result["review"],
            "changes": result["changes"],
            "save_edits": request.save_edits,
            "old": updates.git(ROOT, "rev-parse", "HEAD").decode().strip(),
            "profile": updates.local_profile(),
            "mode": mode,
            "run_id": os.environ["PIXEAGLE_RUN_ID"],
            "python": sys.executable,
            "operator": http_request.state.api_principal.subject,
            "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        }
        path.mkdir(mode=0o700)
        updates.write_json(path / "job.json", job)
        updates.write_json(base / "current.json", job["id"])
        try:
            subprocess.run(
                args,
                env=env,
                check=True,
                timeout=12,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            job = updates.set_stage(
                path,
                "failed",
                "The maintenance worker could not start. Check host service permissions.",
            )
            return job, False
        return job, True


async def authorize_cutover(owner, http_request, job):
    path = updates.directory(ROOT) / job["id"]
    # The worker performs all network/download/validation work before asking.
    # If this backend disappears, a worker without a permit times out in place.
    while updates.read_json(path / "job.json")["stage"] in {"queued", "downloading", "preparing"}:
        if (path / "prepared.json").exists():
            break
        if time.time() - job["started"] > 360:
            return
        await asyncio.sleep(0.2)
    if not (path / "prepared.json").exists():
        return

    async def approve():
        async with owner.app_controller._follower_state_lock:
            if eligibility(owner, http_request):
                updates.write_json(path / "denied.json", True)
            else:
                owner._software_update_barrier = path
                updates.write_json(path / "permit.json", time.time())

    try:
        runner = owner.app_controller._run_on_flight_event_loop
        await runner(approve)
    except (RuntimeError, OSError, AttributeError, ValueError):
        updates.write_json(path / "denied.json", True)


async def install(owner, request, http_request):
    path = str(http_request.url.path)
    try:
        job, queued = await asyncio.to_thread(queue_update, request, owner, http_request)
        if queued:
            task = asyncio.create_task(authorize_cutover(owner, http_request, job))
            owner._software_update_task = task
        return public_job(job)
    except updates.UpdateError as exc:
        return build_api_v1_error_response(
            status_code=409, code="update_unavailable", detail={"message": str(exc)}, path=path
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return build_api_v1_error_response(
            status_code=503,
            code="update_host_unavailable",
            detail={
                "message": "Could not inspect the local installation. Check its storage and service status."
            },
            path=path,
        )
