#!/usr/bin/env python3
"""Qualify backend-only restart in an explicitly owned, command-blocked SIH stack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid

import requests


def owned_containers(runtime):
    names = subprocess.check_output(
        ["docker", "ps", "--filter", "label=pixeagle.sih=gimbal-probe", "--format", "{{.Names}}"], text=True
    ).splitlines()
    for name in names:
        if not name.endswith("-backend"):
            continue
        row = json.loads(subprocess.check_output(["docker", "inspect", name], text=True))[0]
        if not any(mount["Source"] == str(runtime) for mount in row["Mounts"]):
            continue
        px4 = name.removesuffix("-backend") + "-px4"
        peer = json.loads(subprocess.check_output(["docker", "inspect", px4], text=True))[0]
        if peer["Config"]["Labels"].get("pixeagle.sih") != "gimbal-probe":
            raise RuntimeError("PX4 ownership is not verified")
        return name, px4
    raise RuntimeError("No owned SIH backend uses this runtime")


def process_inventory(names):
    rows = []
    for name in names:
        row = json.loads(subprocess.check_output(["docker", "inspect", name], text=True))[0]
        rows.append({"name": name, "id": row["Id"], "started": row["State"]["StartedAt"],
                     "pid": row["State"]["Pid"]})
    backend = names[0]
    listing = subprocess.check_output(["docker", "top", backend, "-eo", "pid,lstart,args"], text=True)
    sidecars = [line for line in listing.splitlines() if any(name in line for name in
        ("mavlink-routerd", "mavlink2rest", "mavsdk_server_bin"))]
    if len(sidecars) != 3:
        raise RuntimeError("Expected all three owned sidecars")
    return {"containers": rows, "sidecars": sidecars}


def probe(runtime):
    runtime = runtime.resolve()
    names = owned_containers(runtime)
    credentials = json.loads((runtime / "credentials.json").read_text())
    manifest = json.loads((runtime / "profile-manifest.json").read_text())
    endpoint = credentials["endpoint"]
    if endpoint != f"http://127.0.0.1:{manifest['backend_port']}":
        raise RuntimeError("Expected the isolated loopback endpoint")
    client = requests.Session()
    def login():
        response = client.post(endpoint + "/api/v1/auth/login", json={
            "username": credentials["username"], "password": credentials["password"]}, timeout=3)
        response.raise_for_status()
        auth = response.json()
        client.headers[auth["csrf_header_name"]] = auth["csrf_token"]
    def get(path):
        response = client.get(endpoint + path, timeout=3)
        response.raise_for_status()
        return response.json()
    login()
    context = get("/api/v1/integration/context")
    if (context["instance_id"] != manifest["instance_id"] or
            context["telemetry"]["autopilot_uid"] != json.loads(
                (runtime / "logs/stack-probe-result.json").read_text())["simulated_autopilot_uid"] or
            get("/api/v1/integration/safety")["active"] is not True):
        raise RuntimeError("Wrong simulated aircraft or flight commands are not blocked")
    before = get("/api/v1/integration/config")
    if not before["system_restart"]["available"]:
        raise RuntimeError(f"Restart unavailable: {before['system_restart']['reason']}")
    inventory = process_inventory(names)
    settings = get("/api/config/current")
    quality = settings["config"]["Streaming"]["STREAM_QUALITY"]
    response = client.put(endpoint + "/api/config/Streaming/STREAM_QUALITY",
        json={"value": quality - 1 if quality > 1 else 2}, timeout=5)
    response.raise_for_status()
    current = get("/api/v1/integration/config")
    if not current["pending"]:
        raise RuntimeError("Saved configuration was not reported pending")
    def body(snapshot):
        return {"confirm": True, "idempotency_key": str(uuid.uuid4()), "restart_context": {
            key: snapshot[key] for key in ("instance_id", "runtime_id", "config_generation")}}
    stale = client.post(endpoint + "/api/v1/actions/system-restart", json=body(before), timeout=5)
    if stale.status_code != 409 or get("/api/v1/integration/context")["runtime_id"] != before["runtime_id"]:
        raise RuntimeError("Stale confirmation changed the runtime")
    request = body(current)
    started = time.monotonic()
    response = client.post(endpoint + "/api/v1/actions/system-restart", json=request, timeout=5)
    response.raise_for_status()
    if response.status_code != 202 or not response.json()["executed"]:
        raise RuntimeError("Restart was not accepted")
    errors = []
    need_login = False
    login_attempts = 0
    next_login = 0.0
    while time.monotonic() - started < 60:
        try:
            if need_login:
                if login_attempts >= 6:
                    raise RuntimeError("Restart authentication retry limit reached")
                if time.monotonic() < next_login:
                    time.sleep(0.5)
                    continue
                login_attempts += 1
                next_login = time.monotonic() + 3
                try:
                    login()
                except requests.HTTPError as error:
                    if error.response.status_code in (401, 403, 429):
                        raise RuntimeError("Restart sign-in refused or rate limited") from error
                    raise
                need_login = False
            returned = get("/api/v1/integration/context")
            if returned["instance_id"] != before["instance_id"]:
                raise RuntimeError("Different installation answered")
            if returned["runtime_id"] == before["runtime_id"]:
                time.sleep(0.5)
                continue
            state = get("/api/v1/integration/config")
            if not returned["video"].get("width") or state["pending"]:
                time.sleep(0.5)
                continue
            target = get("/api/v1/integration/target-state")
            safety = get("/api/v1/integration/safety")
            if target["tracking_active"] or target["following_active"] or safety["active"] is not True:
                raise RuntimeError("An operation resumed or flight-command protection was not restored")
            after_inventory = process_inventory(names)
            if inventory != after_inventory:
                raise RuntimeError("A sidecar or container was replaced")
            result = {"passed": True, "elapsed_s": round(time.monotonic() - started, 3),
                "instance_id": before["instance_id"], "old_runtime": before["runtime_id"],
                "new_runtime": returned["runtime_id"], "stale_confirmation_status": stale.status_code,
                "pending_cleared": not state["pending"], "operations_resumed": False,
                "commands_blocked": safety["active"], "sidecars_unchanged": True,
                "inventory": inventory, "transient_errors": errors,
                "process_logs": sorted(path.name for path in (runtime / "logs").glob("pixeagle-backend_*.log"))}
            (runtime / "logs/restart-probe-result.json").write_text(json.dumps(result, indent=2) + "\n")
            return result
        except requests.RequestException as error:
            if error.response is not None:
                if error.response.status_code == 401:
                    need_login = True
                elif 400 <= error.response.status_code < 500:
                    raise RuntimeError("Restart readiness request was refused") from error
            errors.append(type(error).__name__)
            time.sleep(1)
    raise RuntimeError("A new ready backend did not return within 60 seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--execute", action="store_true", required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.runtime), indent=2))
