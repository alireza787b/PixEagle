#!/usr/bin/env python3
"""Discover browser-reachable IPv4 addresses for guided setup."""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Iterable


PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
SHARED_NETWORK = ipaddress.ip_network("100.64.0.0/10")


@dataclass(frozen=True)
class BrowserHost:
    address: str
    interface: str
    scope: str
    primary: bool = False


def classify_host(value: str) -> str:
    """Classify an address without treating hostnames as local or public proof."""
    host = str(value or "").strip().strip("[]")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "hostname" if host and not any(character.isspace() for character in host) else "invalid"

    if address.version != 4:
        return "unsupported"
    if address.is_loopback:
        return "local"
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        return "invalid"
    if address in SHARED_NETWORK:
        return "shared/overlay"
    if any(address in network for network in PRIVATE_NETWORKS):
        return "private LAN"
    if address.is_link_local:
        return "link-local"
    return "public" if address.is_global else "invalid"


def _run_json(command: list[str]) -> Any:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def _default_route() -> tuple[str, str]:
    payload = _run_json(["ip", "-j", "-4", "route", "get", "1.1.1.1"])
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return "", ""
    route = payload[0]
    return str(route.get("prefsrc") or route.get("src") or ""), str(route.get("dev") or "")


def _link_kinds() -> dict[str, str]:
    payload = _run_json(["ip", "-j", "-d", "link", "show", "up"])
    if not isinstance(payload, list):
        return {}
    return {
        str(item.get("ifname")): str((item.get("linkinfo") or {}).get("info_kind") or "")
        for item in payload
        if isinstance(item, dict) and item.get("ifname")
    }


def _ip_candidates() -> list[tuple[str, str]]:
    payload = _run_json(["ip", "-j", "-4", "addr", "show", "up"])
    if not isinstance(payload, list):
        return []

    result: list[tuple[str, str]] = []
    link_kinds = _link_kinds()
    for interface in payload:
        if not isinstance(interface, dict):
            continue
        name = str(interface.get("ifname") or "unknown")
        for info in interface.get("addr_info") or []:
            if not isinstance(info, dict) or info.get("family") != "inet":
                continue
            address = str(info.get("local") or "").strip()
            if classify_host(address) in {"invalid", "local", "unsupported"}:
                continue
            result.append((address, name))

    externally_useful = [
        item for item in result if link_kinds.get(item[1]) not in {"bridge", "veth"}
    ]
    return externally_useful or result


def _hostname_candidates() -> Iterable[tuple[str, str]]:
    try:
        values = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        values = []
    for value in values:
        if classify_host(value) not in {"invalid", "local", "unsupported"}:
            yield value, "unknown"


def discover_browser_hosts() -> list[BrowserHost]:
    """Return stable, de-duplicated candidates with the default route first."""
    primary_address, primary_interface = _default_route()
    raw = _ip_candidates()
    if not raw:
        raw = list(_hostname_candidates())
    if primary_address and classify_host(primary_address) not in {
        "invalid",
        "local",
        "unsupported",
    }:
        raw.insert(0, (primary_address, primary_interface or "unknown"))

    by_address: dict[str, BrowserHost] = {}
    for address, interface in raw:
        current = by_address.get(address)
        primary = address == primary_address
        candidate = BrowserHost(
            address=address,
            interface=interface or "unknown",
            scope=classify_host(address),
            primary=primary,
        )
        if current is None or (primary and not current.primary):
            by_address[address] = candidate

    scope_order = {
        "private LAN": 0,
        "shared/overlay": 1,
        "public": 2,
        "link-local": 3,
        "hostname": 4,
    }
    return sorted(
        by_address.values(),
        key=lambda item: (
            0 if item.primary else 1,
            scope_order.get(item.scope, 9),
            item.interface,
            ipaddress.ip_address(item.address),
        ),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classify", metavar="HOST")
    parser.add_argument("--format", choices=("json", "tsv"), default="json")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.classify is not None:
        print(classify_host(args.classify))
        return 0

    hosts = discover_browser_hosts()
    if args.format == "tsv":
        for host in hosts:
            print(
                "\t".join(
                    (
                        host.address,
                        host.interface,
                        host.scope,
                        "yes" if host.primary else "no",
                    )
                )
            )
    else:
        print(json.dumps([asdict(host) for host in hosts], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
