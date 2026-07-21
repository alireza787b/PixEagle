"""Tests for interface-aware browser host discovery."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "scripts" / "setup" / "browser_hosts.py"
SPEC = importlib.util.spec_from_file_location("pixeagle_browser_hosts", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_browser_host_scope_classification_is_explicit():
    assert MODULE.classify_host("192.168.10.2") == "private LAN"
    assert MODULE.classify_host("100.82.207.49") == "shared/overlay"
    assert MODULE.classify_host("8.8.8.8") == "public"
    assert MODULE.classify_host("127.0.0.1") == "local"
    assert MODULE.classify_host("203.0.113.10") == "invalid"
    assert MODULE.classify_host("pixeagle.local") == "hostname"
    assert MODULE.classify_host("bad host") == "invalid"


def test_discovery_prefers_default_route_and_hides_non_primary_bridges(monkeypatch):
    address_payload = [
        {
            "ifname": "docker0",
            "addr_info": [{"family": "inet", "local": "172.17.0.1"}],
        },
        {
            "ifname": "eth0",
            "addr_info": [{"family": "inet", "local": "8.8.4.4"}],
        },
        {
            "ifname": "wt0",
            "addr_info": [{"family": "inet", "local": "100.82.207.49"}],
        },
    ]
    links_payload = [
        {"ifname": "docker0", "linkinfo": {"info_kind": "bridge"}},
        {"ifname": "eth0"},
        {"ifname": "wt0", "linkinfo": {"info_kind": "wireguard"}},
    ]
    route_payload = [{"prefsrc": "8.8.4.4", "dev": "eth0"}]

    def fake_run_json(command):
        if "addr" in command:
            return address_payload
        if "link" in command:
            return links_payload
        return route_payload

    monkeypatch.setattr(MODULE, "_run_json", fake_run_json)
    hosts = MODULE.discover_browser_hosts()

    assert [host.address for host in hosts] == ["8.8.4.4", "100.82.207.49"]
    assert hosts[0].primary is True
    assert hosts[1].scope == "shared/overlay"
