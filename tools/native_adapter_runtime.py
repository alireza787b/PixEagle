"""Shared adapter preparation and one-shot DDS bootstrap; callers own isolation and cleanup."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import time


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def dds_session_ready(result):
    """Pinned print_status fields; exit0 or the substring 'connected' is insufficient."""
    if result.returncode != 0:
        return False
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    text = re.sub(r"(?m)^\s*INFO\s+\[uxrce_dds_client\]\s*", "", text)
    expected = {"Running,": "connected", "Using transport:": "udp", "Agent IP:": "127.0.0.1",
                "Agent port:": "8888", "timesync converged:": "true"}
    return all(re.findall(r"(?m)^\s*" + re.escape(field) + r"\s*(\S+)\s*$", text) == [value]
               for field, value in expected.items())


def adapter_launch_args(work, bundle, assets, *, token, primary, label, name):
    script = work / "adapter.sh"
    script.write_text('set -eo pipefail\nsource /work/ws/install/setup.bash\n'
        'source /output/ros/install/local_setup.bash\n'
        'export LD_LIBRARY_PATH=/opt/pixeagle/agent/lib:${LD_LIBRARY_PATH:-}\n'
        'exec /output/adapter/pixeagle-native-guidance --ros-args -p socket_path:=/runtime/private/guidance.sock '
        '> /runtime/adapter.log 2>&1\n')
    (work / "agent.sh").write_text('set -eo pipefail\nsource /work/ws/install/setup.bash\n'
        'source /output/ros/install/local_setup.bash\n'
        'export LD_LIBRARY_PATH=/opt/pixeagle/agent/lib:${LD_LIBRARY_PATH:-}\n'
        'exec /opt/pixeagle/agent/bin/MicroXRCEAgent udp4 -p 8888 > /runtime/dds.log 2>&1\n')
    return ["docker", "run", "-d", "--name", name, "--label",
        label + "=" + token, "--network", "container:" + primary,
        "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--mount", f"type=bind,src={work},dst=/runtime", "--mount",
        f"type=bind,src={bundle.resolve()},dst=/output,readonly",
        assets["adapter_image"], "bash", "/runtime/agent.sh"]


def adapter_info(self, owned_container_info):
    info = owned_container_info(self.sidecar, self.token)
    host = info["HostConfig"]
    mounts = {item["Destination"]: (Path(item["Source"]).resolve(), item["RW"]) for item in info["Mounts"]}
    if (info["State"]["Running"] is not True or info["Image"] != self.assets["adapter_image"]
            or info["Config"]["User"] != f"{os.getuid()}:{os.getgid()}"
            or host["NetworkMode"] != "container:" + self.primary or host["Privileged"]
            or host.get("Devices") or info["NetworkSettings"]["Ports"]
            or mounts != {"/runtime": (self.output / "simulator", True),
                          "/output": (self.args.adapter_bundle.resolve(), False)}):
        raise ValueError("Native observer sidecar isolation changed")
    return info


async def bootstrap_adapter(self, deadline, *, clock=None, sleep=asyncio.sleep):
    """DDS readiness, one adapter launch and socket arrival share the original45s budget."""
    clock = time.monotonic if clock is None else clock
    if self.adapter_requested:
        raise ValueError("Adapter bootstrap is one-shot; no restart")
    while clock() < deadline:
        status = await asyncio.to_thread(self.bootstrap_status, timeout=min(15., deadline - clock()))
        ready = dds_session_ready(status)
        with (self.output / "bootstrap-status.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(returncode=status.returncode, stdout=status.stdout, stderr=status.stderr,
                session_ready=ready, remaining_boot_budget_s=deadline - clock())) + "\n")
        if ready:
            if clock() >= deadline:
                break
            self.primary_info()
            self.sidecar_info()
            if clock() >= deadline:
                break
            self.adapter_requested = True  # Set before exec: a lost reply never permits a second launch.
            launched = self.command(["docker", "exec", "-d", "--user", f"{os.getuid()}:{os.getgid()}",
                self.sidecar, "bash", "/runtime/adapter.sh"], timeout=min(15., deadline - clock()))
            write(self.output / "adapter-bootstrap.json", dict(returncode=launched.returncode,
                stdout=launched.stdout, stderr=launched.stderr, original_sidecar=self.sidecar,
                remaining_boot_budget_s=deadline - clock(), discovery_timeout_changed=False, launch_attempts=1))
            while clock() < deadline:
                self.primary_info()
                self.sidecar_info()
                if clock() >= deadline:
                    break
                if self.socket.is_socket():
                    return
                await sleep(min(.5, max(0., deadline - clock())))
            break
        await sleep(min(.5, max(0., deadline - clock())))
    raise TimeoutError("Original45s bootstrap budget exhausted; adapter not restarted")
