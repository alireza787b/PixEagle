import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import Response
import pytest

from classes.api_security_types import APIPrincipal, APISensitivity
from classes.api_v1_actions import ApiActionStore
from classes.api_v1_contracts import SITLManagedLifecycleRequest
from classes.fastapi_handler import FastAPIHandler
from classes import managed_sih


IMAGE_ID = "sha256:" + "1" * 64


def docker_result(*, returncode=0, stdout="", stderr="", timed_out=False):
    return {
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "stdout_truncated": False,
    }


def image_inspect_output(spec):
    return "\n".join((json.dumps([spec.expected_repo_digest]), json.dumps(IMAGE_ID)))


def container_inspect_output(payload):
    return "\n".join(
        json.dumps(value)
        for value in (
            payload["Id"],
            payload["Image"],
            payload["State"]["Running"],
            payload["Config"]["Image"],
            payload["HostConfig"]["NetworkMode"],
            payload["Config"]["Labels"],
            payload["Config"]["Env"],
        )
    )


def owned_container_payload(spec, *, container_id, run_id, running=True):
    return {
        "Id": container_id,
        "Image": IMAGE_ID,
        "Config": {
            "Image": spec.expected_repo_digest,
            "Labels": {
                managed_sih.MANAGED_CONTAINER_LABEL: "true",
                managed_sih.MANAGED_PROFILE_LABEL: managed_sih.MANAGED_PROFILE,
                managed_sih.MANAGED_RUN_ID_LABEL: run_id,
                managed_sih.MANAGED_MODEL_LABEL: spec.model,
                managed_sih.MANAGED_IMAGE_DIGEST_LABEL: spec.expected_repo_digest,
            },
            "Env": [f"PX4_SIM_MODEL={spec.model}"],
        },
        "HostConfig": {"NetworkMode": "host"},
        "State": {"Running": running},
    }


@pytest.fixture(autouse=True)
def isolated_lifecycle_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(
        managed_sih,
        "MANAGED_LEDGER_PATH",
        tmp_path / "managed-sih-actions.json",
    )


def admin_request():
    return SimpleNamespace(
        state=SimpleNamespace(
            api_principal=APIPrincipal.session(
                username="admin",
                role="admin",
                session_id="managed-sih-session",
            )
        ),
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def make_handler():
    async def run_on_flight_event_loop(operation):
        return await operation()

    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler._api_action_store = ApiActionStore()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        _follower_state_lock=asyncio.Lock(),
        _run_on_flight_event_loop=run_on_flight_event_loop,
        offboard_commander=None,
        mavlink_data_manager=None,
        px4_interface=SimpleNamespace(
            get_connection_status=lambda: {
                "connected": False,
                "system_address": "udp://127.0.0.1:14540",
            }
        ),
    )
    handler.security_audit_logger = MagicMock(enabled=True)
    handler.security_audit_logger.record_event.return_value = True
    return handler


def ready_probe():
    return {
        "feature_enabled": True,
        "readiness": "ready",
        "docker_daemon_accessible": True,
        "image_available": True,
        "image_id": IMAGE_ID,
        "container_name": managed_sih.MANAGED_CONTAINER_NAME,
        "container_state": "absent",
        "container_id": None,
        "full_container_id": None,
        "ownership_verified": False,
        "start_available": True,
        "stop_available": False,
        "control_active": False,
        "px4_connected": False,
        "reasons": [],
        "spec": managed_sih.load_managed_sih_spec(),
        "operation_id": "managed-test",
    }


def response_payload(response):
    return json.loads(response.body.decode("utf-8"))


def test_managed_sih_spec_is_derived_from_checked_in_plan():
    spec = managed_sih.load_managed_sih_spec()

    assert spec.image == "px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01"
    assert spec.model == "sihsim_quadx"
    assert spec.network_mode == "host"
    assert spec.expected_repo_digest.endswith(
        "fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865"
    )


def test_managed_sih_spec_accepts_registry_ports_without_confusing_them_for_tags(
    tmp_path,
):
    plan = tmp_path / "managed-sih.json"
    plan.write_text(
        json.dumps({
            "stack": {
                "px4": {
                    "recommended_image": "registry.example:5000/px4/sitl:v1",
                    "vehicle_model": "sihsim_quadx",
                    "network_mode": "host",
                    "expected_repo_digest": (
                        "registry.example:5000/px4/sitl@sha256:" + "a" * 64
                    ),
                }
            }
        }),
        encoding="utf-8",
    )

    spec = managed_sih.load_managed_sih_spec(plan)

    assert spec.image == "registry.example:5000/px4/sitl:v1"


def test_managed_sih_spec_requires_an_immutable_digest(tmp_path):
    plan = tmp_path / "managed-sih.json"
    plan.write_text(
        json.dumps({
            "stack": {
                "px4": {
                    "recommended_image": "px4io/px4-sitl:v1",
                    "vehicle_model": "sihsim_quadx",
                    "network_mode": "host",
                }
            }
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="immutable image digest"):
        managed_sih.load_managed_sih_spec(plan)


def test_runtime_summary_distinguishes_unknown_control_state_from_inactive(
    monkeypatch,
):
    def unavailable(_owner):
        raise RuntimeError("state unavailable")

    monkeypatch.setattr(managed_sih, "get_control_activity_state", unavailable)

    summary = managed_sih._runtime_summary(make_handler())

    assert summary["activity_available"] is False
    assert summary["control_active"] is False


def test_probe_reports_ready_only_for_verified_image_and_absent_name(monkeypatch):
    spec = managed_sih.load_managed_sih_spec()
    monkeypatch.setattr(managed_sih.Parameters, "ENABLE_MANAGED_SIH", True, raising=False)
    monkeypatch.setattr(managed_sih.shutil, "which", lambda command: "/usr/bin/docker")

    def fake_run(args, *, timeout_s, max_output_chars=2048):
        assert timeout_s > 0
        assert max_output_chars > 0
        if args[0] == "version":
            return docker_result(stdout="27.5.1")
        if args[:2] == ["image", "inspect"]:
            return docker_result(stdout=image_inspect_output(spec))
        if args[:2] == ["container", "inspect"]:
            return docker_result(returncode=1, stderr="No such container")
        raise AssertionError(args)

    monkeypatch.setattr(managed_sih, "_run_docker", fake_run)
    owner = make_handler()

    probe = managed_sih.probe_managed_sih(owner)

    assert probe["readiness"] == "ready"
    assert probe["image_available"] is True
    assert probe["container_state"] == "absent"
    assert probe["start_available"] is True
    assert probe["stop_available"] is False


def test_probe_fails_closed_when_px4_connection_state_is_unknown(monkeypatch):
    spec = managed_sih.load_managed_sih_spec()
    monkeypatch.setattr(managed_sih.Parameters, "ENABLE_MANAGED_SIH", True, raising=False)
    monkeypatch.setattr(managed_sih.shutil, "which", lambda command: "/usr/bin/docker")

    def fake_run(args, *, timeout_s, max_output_chars=2048):
        if args[0] == "version":
            return docker_result(stdout="27.5.1")
        if args[:2] == ["image", "inspect"]:
            return docker_result(stdout=image_inspect_output(spec))
        if args[:2] == ["container", "inspect"]:
            return docker_result(returncode=1, stderr="No such container")
        raise AssertionError(args)

    owner = make_handler()
    owner.app_controller.px4_interface = None
    monkeypatch.setattr(managed_sih, "_run_docker", fake_run)

    probe = managed_sih.probe_managed_sih(owner)

    assert probe["px4_connected"] is None
    assert probe["start_available"] is False
    assert "px4_connection_state_unavailable" in probe["reasons"]


def test_probe_never_treats_an_unowned_name_collision_as_managed(monkeypatch):
    spec = managed_sih.load_managed_sih_spec()
    monkeypatch.setattr(managed_sih.Parameters, "ENABLE_MANAGED_SIH", True, raising=False)
    monkeypatch.setattr(managed_sih.shutil, "which", lambda command: "/usr/bin/docker")

    collision = {
        "Id": "f" * 64,
        "Image": "sha256:" + "f" * 64,
        "Config": {"Image": "unrelated/image:latest", "Labels": {}, "Env": []},
        "HostConfig": {"NetworkMode": "host"},
        "State": {"Running": True},
    }

    def fake_run(args, *, timeout_s, max_output_chars=2048):
        if args[0] == "version":
            return docker_result(stdout="27.5.1")
        if args[:2] == ["image", "inspect"]:
            return docker_result(stdout=image_inspect_output(spec))
        if args[:2] == ["container", "inspect"]:
            return docker_result(stdout=container_inspect_output(collision))
        raise AssertionError(args)

    monkeypatch.setattr(managed_sih, "_run_docker", fake_run)

    probe = managed_sih.probe_managed_sih(make_handler())

    assert probe["readiness"] == "conflict"
    assert probe["container_state"] == "conflict"
    assert probe["ownership_verified"] is False
    assert probe["start_available"] is False
    assert probe["stop_available"] is False


def test_start_uses_fixed_argv_and_verifies_the_returned_container_id(monkeypatch):
    probe = ready_probe()
    commands = []
    full_id = "a" * 64
    spec = probe["spec"]
    inspected = owned_container_payload(
        spec,
        container_id=full_id,
        run_id="managed-test",
    )

    def fake_run(args, *, timeout_s, max_output_chars=2048):
        commands.append(list(args))
        if args[0] == "run":
            return docker_result(stdout=full_id)
        if args[:2] == ["container", "inspect"]:
            assert args[-1] == full_id
            return docker_result(stdout=container_inspect_output(inspected))
        raise AssertionError(args)

    monkeypatch.setattr(managed_sih, "_run_docker", fake_run)

    result = managed_sih._run_managed_start(probe)

    start = commands[0]
    assert start[0] == "run"
    assert "--pull=never" in start
    assert start[-1] == spec.expected_repo_digest
    assert "--cpus" in start
    assert "--memory" in start
    assert "--pids-limit" in start
    assert "--log-driver" in start
    assert f"PX4_SIM_MODEL={spec.model}" in start
    assert "sh" not in start
    assert result["container_id"] == full_id[:12]
    assert result["ownership_verified"] is True


def test_start_timeout_reconciles_only_the_exact_owned_run(monkeypatch):
    probe = {**ready_probe(), "operation_id": "managed-timeout"}
    spec = probe["spec"]
    full_id = "d" * 64
    inspected = owned_container_payload(
        spec,
        container_id=full_id,
        run_id="managed-timeout",
    )
    commands = []

    def fake_run(args, *, timeout_s, max_output_chars=2048):
        commands.append(list(args))
        if args[0] == "run":
            return docker_result(
                returncode=None,
                stderr="docker command timed out",
                timed_out=True,
            )
        if args[:2] == ["container", "inspect"]:
            assert args[-1] == managed_sih.MANAGED_CONTAINER_NAME
            return docker_result(stdout=container_inspect_output(inspected))
        raise AssertionError(args)

    monkeypatch.setattr(managed_sih, "_run_docker", fake_run)

    result = managed_sih._run_managed_start(probe)

    assert result["container_id"] == full_id[:12]
    assert result["reconciled_after_timeout"] is True


def test_start_timeout_fails_unknown_when_container_cannot_be_reconciled(monkeypatch):
    probe = {**ready_probe(), "operation_id": "managed-timeout-unknown"}

    def fake_run(args, *, timeout_s, max_output_chars=2048):
        if args[0] == "run":
            return docker_result(
                returncode=None,
                stderr="docker command timed out",
                timed_out=True,
            )
        if args[:2] == ["container", "inspect"]:
            return docker_result(returncode=1, stderr="daemon unavailable")
        raise AssertionError(args)

    monkeypatch.setattr(managed_sih, "_run_docker", fake_run)

    with pytest.raises(managed_sih.ManagedSIHError) as error:
        managed_sih._run_managed_start(probe)

    assert error.value.code == "ACTION_MANAGED_SIH_START_OUTCOME_UNKNOWN"
    assert error.value.details["outcome_unknown"] is True


def test_stop_uses_only_the_verified_immutable_container_id(monkeypatch):
    full_id = "b" * 64
    probe = {
        **ready_probe(),
        "container_state": "running",
        "full_container_id": full_id,
        "ownership_verified": True,
    }
    commands = []

    def fake_run(args, *, timeout_s, max_output_chars=2048):
        commands.append(list(args))
        return docker_result(stdout=full_id)

    monkeypatch.setattr(managed_sih, "_run_docker", fake_run)

    result = managed_sih._run_managed_stop(probe)

    assert commands == [["stop", "--time", "10", full_id]]
    assert managed_sih.MANAGED_CONTAINER_NAME not in commands[0]
    assert result["stopped"] is True


def test_stop_timeout_reconciles_an_absent_owned_container(monkeypatch):
    full_id = "e" * 64
    probe = {
        **ready_probe(),
        "container_state": "running",
        "full_container_id": full_id,
        "ownership_verified": True,
    }

    def fake_run(args, *, timeout_s, max_output_chars=2048):
        if args[0] == "stop":
            return docker_result(
                returncode=None,
                stderr="docker command timed out",
                timed_out=True,
            )
        if args[:2] == ["container", "inspect"]:
            return docker_result(returncode=1, stderr="No such container")
        raise AssertionError(args)

    monkeypatch.setattr(managed_sih, "_run_docker", fake_run)

    result = managed_sih._run_managed_stop(probe)

    assert result["stopped"] is True
    assert result["reconciled_after_timeout"] is True


def test_stop_refuses_unverified_container_ownership(monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(managed_sih, "_run_docker", run)

    try:
        managed_sih._run_managed_stop({
            "full_container_id": "c" * 64,
            "ownership_verified": False,
        })
    except managed_sih.ManagedSIHError as exc:
        assert exc.code == "ACTION_MANAGED_SIH_OWNERSHIP_UNVERIFIED"
    else:
        raise AssertionError("unverified container stop unexpectedly succeeded")
    run.assert_not_called()


async def test_action_requires_explicit_no_real_aircraft_confirmation(monkeypatch):
    handler = make_handler()
    monkeypatch.setattr(
        managed_sih,
        "probe_managed_sih",
        lambda owner, runtime_override=None: ready_probe(),
    )
    mutation = MagicMock()
    monkeypatch.setattr(managed_sih, "_run_managed_start", mutation)

    response = Response(status_code=202)
    result = await managed_sih.managed_sih_action(
        handler,
        SITLManagedLifecycleRequest(
            confirm=True,
            idempotency_key="managed-sih-no-hardware-ack",
        ),
        response,
        admin_request(),
        operation="start",
    )

    assert result.status_code == 409
    assert response_payload(result)["code"] == (
        "ACTION_MANAGED_SIH_REAL_AIRCRAFT_CONFIRMATION_REQUIRED"
    )
    mutation.assert_not_called()


async def test_action_audits_then_executes_once_and_replays_idempotently(monkeypatch):
    handler = make_handler()
    monkeypatch.setattr(
        managed_sih,
        "probe_managed_sih",
        lambda owner, runtime_override=None: ready_probe(),
    )
    mutation = MagicMock(return_value={"container_id": "abc123", "ownership_verified": True})
    monkeypatch.setattr(managed_sih, "_run_managed_start", mutation)
    request = SITLManagedLifecycleRequest(
        confirm=True,
        idempotency_key="managed-sih-start-once",
        no_real_aircraft_confirmed=True,
    )

    first_response = Response(status_code=202)
    first = await managed_sih.managed_sih_action(
        handler,
        request,
        first_response,
        admin_request(),
        operation="start",
    )
    second_response = Response(status_code=202)
    second = await managed_sih.managed_sih_action(
        handler,
        request,
        second_response,
        admin_request(),
        operation="start",
    )

    assert first["status"] == "success"
    assert first["executed"] is True
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert second_response.status_code == 200
    mutation.assert_called_once()
    assert handler.security_audit_logger.record_event.call_count == 2
    assert (
        handler.security_audit_logger.record_event.call_args_list[-1].kwargs["sensitivity"]
        == APISensitivity.SYSTEM
    )


async def test_action_replays_from_durable_ledger_after_process_store_reset(
    monkeypatch,
):
    monkeypatch.setattr(
        managed_sih,
        "probe_managed_sih",
        lambda owner, runtime_override=None: ready_probe(),
    )
    mutation = MagicMock(
        return_value={"container_id": "abc123", "ownership_verified": True}
    )
    monkeypatch.setattr(managed_sih, "_run_managed_start", mutation)
    request = SITLManagedLifecycleRequest(
        confirm=True,
        idempotency_key="managed-sih-durable-replay",
        no_real_aircraft_confirmed=True,
    )

    first = await managed_sih.managed_sih_action(
        make_handler(),
        request,
        Response(status_code=202),
        admin_request(),
        operation="start",
    )
    replay_response = Response(status_code=202)
    replay = await managed_sih.managed_sih_action(
        make_handler(),
        request,
        replay_response,
        admin_request(),
        operation="start",
    )

    assert first["status"] == "success"
    assert replay["idempotent_replay"] is True
    assert replay["result"]["durable_replay"] is True
    assert replay_response.status_code == 200
    mutation.assert_called_once()
    ledger_text = managed_sih.MANAGED_LEDGER_PATH.read_text(encoding="utf-8")
    assert request.idempotency_key not in ledger_text


async def test_cancelled_api_wait_holds_flight_barrier_until_mutation_finishes(
    monkeypatch,
):
    import threading

    handler = make_handler()
    monkeypatch.setattr(
        managed_sih,
        "probe_managed_sih",
        lambda owner, runtime_override=None: ready_probe(),
    )
    started = threading.Event()
    release = threading.Event()

    def blocking_mutation(_probe):
        started.set()
        assert release.wait(timeout=5.0)
        return {"container_id": "abc123", "ownership_verified": True}

    monkeypatch.setattr(managed_sih, "_run_managed_start", blocking_mutation)
    task = asyncio.create_task(
        managed_sih.managed_sih_action(
            handler,
            SITLManagedLifecycleRequest(
                confirm=True,
                idempotency_key="managed-sih-cancelled-client",
                no_real_aircraft_confirmed=True,
            ),
            Response(status_code=202),
            admin_request(),
            operation="start",
        )
    )

    assert await asyncio.to_thread(started.wait, 2.0)
    task.cancel()
    await asyncio.sleep(0)
    assert handler.app_controller._follower_state_lock.locked() is True
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert handler.app_controller._follower_state_lock.locked() is False


async def test_stop_does_not_require_start_only_hardware_confirmation(monkeypatch):
    handler = make_handler()
    probe = {
        **ready_probe(),
        "readiness": "running",
        "container_state": "running",
        "full_container_id": "b" * 64,
        "ownership_verified": True,
        "start_available": False,
        "stop_available": True,
    }
    monkeypatch.setattr(
        managed_sih,
        "probe_managed_sih",
        lambda owner, runtime_override=None: probe,
    )
    mutation = MagicMock(
        return_value={
            "container_id": "b" * 12,
            "ownership_verified": True,
            "stopped": True,
        }
    )
    monkeypatch.setattr(managed_sih, "_run_managed_stop", mutation)

    result = await managed_sih.managed_sih_action(
        handler,
        SITLManagedLifecycleRequest(
            confirm=True,
            idempotency_key="managed-sih-stop-recovery",
        ),
        Response(status_code=202),
        admin_request(),
        operation="stop",
    )

    assert result["status"] == "success"
    mutation.assert_called_once()


async def test_local_compat_principal_cannot_manage_sih(monkeypatch):
    handler = make_handler()
    request = admin_request()
    request.state.api_principal = APIPrincipal.local_compat()
    mutation = MagicMock()
    monkeypatch.setattr(managed_sih, "_run_managed_start", mutation)

    result = await managed_sih.managed_sih_action(
        handler,
        SITLManagedLifecycleRequest(
            confirm=True,
            idempotency_key="managed-sih-local-compat",
            no_real_aircraft_confirmed=True,
        ),
        Response(status_code=202),
        request,
        operation="start",
    )

    assert result.status_code == 403
    assert response_payload(result)["code"] == "ACTION_MANAGED_SIH_ADMIN_REQUIRED"
    mutation.assert_not_called()
