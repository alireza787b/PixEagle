"""Read-only Linux CLOCK_MONOTONIC evidence; no clock conversion or process authority."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path


def read_monotonic_domain(pid: int | None = None, *, proc: Path = Path('/proc')) -> dict:
    pid = os.getpid() if pid is None else pid
    if type(pid) is not int or pid <= 0:
        raise ValueError('monotonic_clock_domain_unqualified')
    directory = proc / str(pid)

    def namespaces():
        return {name: {'device': value.st_dev, 'inode': value.st_ino}
                for name in ('time', 'time_for_children')
                for value in [(directory / 'ns' / name).stat()]}

    before = namespaces()
    value = {'pid': pid, 'boot_id': (proc / 'sys/kernel/random/boot_id').read_text().strip(),
             'namespaces': before, 'timens_offsets': (directory / 'timens_offsets').read_text()}
    if namespaces() != before:
        raise ValueError('monotonic_clock_domain_changed')
    monotonic_domain(value)
    return value


def monotonic_domain(value: dict) -> tuple[str, int]:
    """Recompute the domain from retained raw evidence, never a producer's qualified flag."""
    try:
        if not isinstance(value, dict) or set(value) != {'pid', 'boot_id', 'namespaces', 'timens_offsets'}:
            raise ValueError
        if type(value['pid']) is not int or value['pid'] <= 0:
            raise ValueError
        boot = value['boot_id']
        if not isinstance(boot, str) or str(uuid.UUID(boot)) != boot or uuid.UUID(boot).int == 0:
            raise ValueError
        namespaces = value['namespaces']
        if not isinstance(namespaces, dict) or set(namespaces) != {'time', 'time_for_children'}:
            raise ValueError
        for item in namespaces.values():
            if (not isinstance(item, dict) or set(item) != {'device', 'inode'}
                    or any(type(item[key]) is not int or item[key] <= 0 for key in item)):
                raise ValueError
        # Linux proc_timens_show_offsets reads time_ns_for_children, not time_ns.
        # https://man7.org/linux/man-pages/man7/time_namespaces.7.html
        if namespaces['time'] != namespaces['time_for_children']:
            raise ValueError
        raw = value['timens_offsets']
        if not isinstance(raw, str) or len(raw) > 1024:
            raise ValueError
        offsets = {}
        for line in raw.splitlines():
            match = re.fullmatch(r'\s*(monotonic|boottime)\s+(-?\d+)\s+(\d+)\s*', line)
            if match is None or match[1] in offsets:
                raise ValueError
            seconds, nanoseconds = int(match[2]), int(match[3])
            if not -2**63 < seconds < 2**63 or not 0 <= nanoseconds < 1_000_000_000:
                raise ValueError
            offsets[match[1]] = seconds * 1_000_000_000 + nanoseconds
        if set(offsets) != {'monotonic', 'boottime'}:
            raise ValueError
        return boot, offsets['monotonic']
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError('monotonic_clock_domain_unqualified') from error


def require_same_monotonic_domain(*values: dict) -> None:
    domains = [monotonic_domain(value) for value in values]
    if not domains or any(domain != domains[0] for domain in domains[1:]):
        raise ValueError('monotonic_clock_domain_mismatch')


def require_unchanged_monotonic_domain(original: dict, current: dict) -> None:
    require_same_monotonic_domain(original, current)
    if (original['namespaces'] != current['namespaces']
            or original['pid'] != current['pid']):
        raise ValueError('monotonic_clock_domain_changed')
