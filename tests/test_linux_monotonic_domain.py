"""Synthetic /proc evidence only; no namespace changes or process signals."""
from copy import deepcopy

import pytest

from tools.linux_monotonic_domain import (
    monotonic_domain,
    read_monotonic_domain,
    require_same_monotonic_domain,
    require_unchanged_monotonic_domain,
)


def evidence(*, inode=10, offset='0 0', boot='12345678-1234-1234-1234-123456789abc', pid=20):
    return {'pid': pid, 'boot_id': boot,
            'namespaces': {name: {'device': 4, 'inode': inode} for name in ('time', 'time_for_children')},
            'timens_offsets': f'monotonic {offset}\nboottime 0 0\n'}


def test_equal_initial_monotonic_offsets_qualify_different_namespace_inodes_without_conversion():
    first, second = evidence(), evidence(inode=11, pid=30)
    require_same_monotonic_domain(first, second)
    assert monotonic_domain(first) == monotonic_domain(second)
    assert first['namespaces'] != second['namespaces']


def test_pid1_is_valid_readonly_monotonic_evidence():
    value = evidence(pid=1)
    require_same_monotonic_domain(value, evidence(pid=20, inode=11))
    assert monotonic_domain(value)[0] == value['boot_id']


def test_matching_nonzero_offsets_are_equal_but_boottime_is_not_monotonic():
    first, second = evidence(offset='-1 900000000'), evidence(inode=11, offset='-1 900000000')
    second['timens_offsets'] = 'boottime 20 0\nmonotonic -1 900000000\n'
    require_same_monotonic_domain(first, second)
    assert monotonic_domain(first)[1] == -100_000_000


@pytest.mark.parametrize('change', ['boot', 'seconds', 'nanoseconds'])
def test_different_boot_or_monotonic_offset_refuses_even_when_namespace_inode_matches(change):
    first, second = evidence(), evidence()
    if change == 'boot':
        second['boot_id'] = '22345678-1234-1234-1234-123456789abc'
    else:
        second['timens_offsets'] = 'monotonic ' + ('1 0' if change == 'seconds' else '0 1') + '\nboottime 0 0\n'
    with pytest.raises(ValueError, match='domain_mismatch'):
        require_same_monotonic_domain(first, second)


@pytest.mark.parametrize('change', ['missing', 'bool_pid', 'zero_pid', 'negative_pid', 'boot', 'zero_boot', 'children',
    'bool_inode', 'zero_inode', 'missing_namespace', 'unknown_namespace', 'bool_device', 'offset_type',
    'missing_offset', 'duplicate_offset', 'unknown_offset', 'fractional_seconds', 'negative_nanoseconds',
    'overflow_nanoseconds', 'too_large', 'extra_field'])
def test_unknown_or_ambiguous_raw_domain_fails_closed(change):
    value = evidence()
    if change == 'missing':
        del value['timens_offsets']
    elif change == 'bool_pid':
        value['pid'] = True
    elif change == 'zero_pid':
        value['pid'] = 0
    elif change == 'negative_pid':
        value['pid'] = -1
    elif change == 'boot':
        value['boot_id'] = 'not-a-kernel-boot-id'
    elif change == 'zero_boot':
        value['boot_id'] = '00000000-0000-0000-0000-000000000000'
    elif change == 'children':
        value['namespaces']['time_for_children']['inode'] += 1
    elif change == 'bool_inode':
        value['namespaces']['time']['inode'] = True
    elif change == 'zero_inode':
        value['namespaces']['time']['inode'] = 0
    elif change == 'missing_namespace':
        del value['namespaces']['time_for_children']
    elif change == 'unknown_namespace':
        value['namespaces']['other'] = {'device': 4, 'inode': 10}
    elif change == 'bool_device':
        value['namespaces']['time']['device'] = True
    elif change == 'offset_type':
        value['timens_offsets'] = None
    elif change == 'missing_offset':
        value['timens_offsets'] = 'monotonic 0 0\n'
    elif change == 'duplicate_offset':
        value['timens_offsets'] += 'monotonic 0 0\n'
    elif change == 'unknown_offset':
        value['timens_offsets'] += 'realtime 0 0\n'
    elif change == 'fractional_seconds':
        value['timens_offsets'] = 'monotonic 0.1 0\nboottime 0 0\n'
    elif change == 'negative_nanoseconds':
        value['timens_offsets'] = 'monotonic 0 -1\nboottime 0 0\n'
    elif change == 'overflow_nanoseconds':
        value['timens_offsets'] = 'monotonic 0 1000000000\nboottime 0 0\n'
    elif change == 'too_large':
        value['timens_offsets'] = ' ' * 1025
    else:
        value['qualified'] = True
    with pytest.raises(ValueError, match='domain_unqualified'):
        monotonic_domain(value)


def test_clock_snapshot_is_bound_to_original_pid_and_namespace_without_reusing_process_identity_parser():
    value, current = evidence(), evidence(pid=30)
    with pytest.raises(ValueError, match='domain_changed'):
        require_unchanged_monotonic_domain(value, current)
    require_same_monotonic_domain(value, current)
    current = evidence(inode=11)
    with pytest.raises(ValueError, match='domain_changed'):
        require_unchanged_monotonic_domain(value, current)


@pytest.mark.parametrize('pid', [1, 20])
def test_reader_retains_exact_raw_offsets_and_namespace_identity(tmp_path, pid):
    directory = tmp_path / str(pid)
    (directory / 'ns').mkdir(parents=True)
    (directory / 'ns/time').write_text('')
    (directory / 'ns/time_for_children').hardlink_to(directory / 'ns/time')
    raw = 'monotonic           0         0\nboottime            0         0\n'
    (directory / 'timens_offsets').write_text(raw)
    boot = tmp_path / 'sys/kernel/random/boot_id'
    boot.parent.mkdir(parents=True)
    boot.write_text(evidence()['boot_id'] + '\n')
    value = read_monotonic_domain(pid, proc=tmp_path)
    assert value['pid'] == pid and value['timens_offsets'] == raw
    assert value['namespaces']['time']['inode'] == (directory / 'ns/time').stat().st_ino
    assert value['namespaces']['time'] == value['namespaces']['time_for_children']


@pytest.mark.parametrize('pid', [0, -1, True])
def test_reader_refuses_nonpositive_or_boolean_pid_before_reading_proc(tmp_path, pid):
    with pytest.raises(ValueError, match='domain_unqualified'):
        read_monotonic_domain(pid, proc=tmp_path)


def test_reader_rejects_namespace_change_during_evidence_read(tmp_path, monkeypatch):
    from pathlib import Path
    directory = tmp_path / '20'
    (directory / 'ns').mkdir(parents=True)
    (directory / 'ns/time').write_text('')
    (directory / 'ns/time_for_children').hardlink_to(directory / 'ns/time')
    (directory / 'timens_offsets').write_text(evidence()['timens_offsets'])
    boot = tmp_path / 'sys/kernel/random/boot_id'
    boot.parent.mkdir(parents=True)
    boot.write_text(evidence()['boot_id'])
    read = Path.read_text
    def changing(path, *args, **kwargs):
        value = read(path, *args, **kwargs)
        if path.name == 'timens_offsets':
            (directory / 'ns/time').unlink()
            (directory / 'ns/time').write_text('replaced')
        return value
    monkeypatch.setattr(Path, 'read_text', changing)
    with pytest.raises(ValueError, match='domain_changed'):
        read_monotonic_domain(20, proc=tmp_path)


def test_input_evidence_is_immutable_to_validator():
    value = evidence()
    original = deepcopy(value)
    require_same_monotonic_domain(value)
    assert value == original
