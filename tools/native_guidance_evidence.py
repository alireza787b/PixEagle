"""Closed-log evidence for a native pursuit; no controller or runtime actions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np

from classes.native_guidance import NativeAcquisitionContext, NativeReleaseReceipt

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONTRACT = ROOT / 'native/guidance-evidence-source.json'


def _source_provenance(run, acquisition, *, adapter_bundle, adapter_file_manifest, build_repository):
    """Reopen only canonical Runtime artifacts; never inspect or launch Docker."""
    from tools.run_native_transition_baseline import ASSETS, verify_adapter
    from tools.sih_baseline import authority, artifact_manifest, recipe_fingerprint

    def read(path):
        return json.loads(Path(path).read_text())

    def digest(path):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError('native_guidance_provenance_regular_input_required')
        return hashlib.sha256(path.read_bytes()).hexdigest()

    run = Path(run)
    contract, assets, host = read(SOURCE_CONTRACT), read(ASSETS), read(run / 'host-manifest.json')
    if (contract.get('schema_version') != 1 or digest(ASSETS) != contract['runtime_assets_sha256']
            or host['runtime_assets_sha256'] != contract['runtime_assets_sha256']
            or host['tool_sha256'] != contract['runtime_helper_sha256']
            or digest(ROOT / 'tools/run_native_transition_baseline.py') != contract['runtime_helper_sha256']
            or host['adapter_image'] != assets['adapter_image']):
        raise ValueError('native_guidance_runtime_provenance_unsupported')
    verify_adapter(Path(adapter_bundle), Path(adapter_file_manifest), assets)
    sdk = next(item for item in read(ROOT / 'native/dependencies.lock.json')['sources']
               if item['repository'] == contract['sdk_source']['repository'])
    if sdk != contract['sdk_source'] or any(digest(run / 'simulator' / name) != pin
                                           for name, pin in contract['scripts'].items()):
        raise ValueError('native_guidance_compiled_producer_changed')
    build = host['simulation_build']
    path = Path(build['manifest'])
    manifest = read(path)
    simulator = {'pixeagle_sih_build': 'sih', 'pixeagle_gazebo_build': 'gazebo'}.get(manifest.get('kind'))
    variant = manifest['build'].get('resource_variant')
    variant = variant.get('name', 'stock') if isinstance(variant, dict) else 'stock'
    repository = ROOT if build_repository is None else Path(build_repository)
    firmware, spec = authority(repository, simulator=simulator, resource_variant=variant)
    artifacts = artifact_manifest(path.parent / 'packaged', simulator=simulator)
    if (digest(path) != build['manifest_sha256'] or manifest['firmware'] != firmware
            or manifest['build'] != spec or manifest['artifacts'] != artifacts
            or manifest['recipe_sha256'] != recipe_fingerprint(firmware, spec, repository=repository)
            or manifest['image_id'] != build['image_id'] or build['firmware'] != firmware
            or artifacts['binary_sha256'] != build['binary_sha256']):
        raise ValueError('native_guidance_build_provenance_changed')
    source = path.parent / 'context/source'
    if any(digest(source / name) != pin for name, pin in contract['firmware_files'].items()):
        raise ValueError('native_guidance_producer_source_unsupported')
    message = (source / 'msg/versioned/VehicleStatus.msg').read_text()
    modes = [int(re.findall(r'(?m)^uint8 NAVIGATION_STATE_EXTERNAL' + number + r'\s*=\s*(\d+)', message)[0])
             for number in ('1', '8')]
    if not modes[0] <= acquisition.mode_id <= modes[1]:
        raise ValueError('native_guidance_external_mode_required')
    registration = read(run / 'capabilities.json')
    capabilities = registration['capabilities']
    bootstrap = read(run / 'adapter-bootstrap.json')
    witnesses = [json.loads(line) for line in (run / 'isolation-verifications.jsonl').read_text().splitlines()]
    if (not all(re.fullmatch('[0-9a-f]{64}', host[key]) for key in ('primary', 'sidecar'))
            or host['primary'] == host['sidecar'] or len(witnesses) < 2
            or re.fullmatch('[0-9a-f]{32}', host['owner_token']) is None
            or bootstrap['original_sidecar'] != host['sidecar'] or bootstrap['launch_attempts'] != 1
            or bootstrap['returncode'] != 0 or capabilities['runtime_id'] != acquisition.runtime_id
            or bootstrap['discovery_timeout_changed'] is not False
            or capabilities['owned_mode_id'] != acquisition.mode_id or capabilities['owned_mode_supported'] is not True
            or registration['binding']['aircraft_uid'] != acquisition.identity.binding.aircraft_uid):
        raise ValueError('native_guidance_original_runtime_unqualified')
    for row in witnesses:
        checked = row['checked']
        if (checked['container_id'] != host['primary'] or checked['image_id'] != build['image_id']
                or checked['firmware_build'] != build or checked['instance'] != 0
                or checked['aircraft_uid'] != acquisition.identity.binding.aircraft_uid
                or checked['process']['binary_sha256'] != build['binary_sha256']
                or checked['process']['model'] != host['fixture']['model']
                or row['sidecar_id'] != host['sidecar'] or row['sidecar_image'] != assets['adapter_image']
                or row['sidecar_running'] is not True):
            raise ValueError('native_guidance_runtime_identity_changed')
    return dict(artifact_root=str(run), source_contract_sha256=digest(SOURCE_CONTRACT),
                native_hold_nav_state=int(re.findall(r'(?m)^uint8 NAVIGATION_STATE_AUTO_LOITER\s*=\s*(\d+)', message)[0]),
                native_fixed_wing_type=int(re.findall(r'(?m)^uint8 VEHICLE_TYPE_FIXED_WING\s*=\s*(\d+)', message)[0]),
                build_manifest_sha256=build['manifest_sha256'], compiled_adapter_sha256=assets['adapter_sha256'])


def _exclusive_payloads(log, topics, start, end):
    """Only the compiled adapter's applicable SDK command forms are supported."""
    def all_fields(name, fields, predicate):
        data = log.get_dataset(name).data
        selected = (data['timestamp'] >= start) & (data['timestamp'] < end)
        return all(np.all(predicate(data[field][selected])) for field in fields)

    if topics == ('trajectory_setpoint',):
        return (all_fields(topics[0], [f'{field}[{i}]' for field in ('position', 'acceleration') for i in range(3)] + ['yaw'], np.isnan)
            and all_fields(topics[0], [f'velocity[{i}]' for i in range(3)] + ['yawspeed'], np.isfinite))
    long = log.get_dataset(topics[1]).data
    selected = (long['timestamp'] >= start) & (long['timestamp'] < end)
    return (all_fields(topics[0], ['course'], np.isfinite)
        and all_fields(topics[0], ['airspeed_direction', 'lateral_acceleration'], np.isnan)
        and all_fields(topics[1], ['equivalent_airspeed'], np.isfinite)
        and all_fields(topics[1], ['pitch_direct', 'throttle_direct'], np.isnan)
        and np.all((np.isfinite(long['altitude'][selected]) & np.isnan(long['height_rate'][selected]))
                   | (np.isnan(long['altitude'][selected]) & np.isfinite(long['height_rate'][selected]))))


def _right_edge(log, topics, end, acquisition, receipt, source):
    """Classify recorded endpoint rows only; no ordering or complete-delivery claim."""
    counts = {name: int(np.sum(log.get_dataset(name).data['timestamp'] == end)) for name in topics}
    result = dict(classification='none' if not any(counts.values()) else 'UNKNOWN',
                  timestamp_us=end, samples=counts, included_in_external_cadence=False)
    if not any(counts.values()) or source is None or topics != (
            'fixed_wing_lateral_setpoint', 'fixed_wing_longitudinal_setpoint'):
        return result

    def row(name):
        data = log.get_dataset(name).data
        indices = np.flatnonzero(data['timestamp'] == end)
        if len(indices) != 1:
            raise ValueError('unique native endpoint witness required')
        return {field: values[indices[0]] for field, values in data.items()}

    try:
        hold = source['native_hold_nav_state']
        lateral, longitudinal = map(row, topics)
        vehicle, owned, control = map(row, ('vehicle_status', 'owned_mode_status', 'vehicle_control_mode'))
        correlated = (receipt.outcome == 'hold_confirmed' and receipt.observed_nav_state == hold
            and receipt.observed_nav_state_timestamp == end
            and vehicle['nav_state'] == hold and vehicle['nav_state_timestamp'] == end
            and vehicle['vehicle_type'] == source['native_fixed_wing_type']
            and vehicle['in_transition_mode'] == 0 and vehicle['accepts_offboard_setpoints'] == 0
            and owned['owner_active'] == 0 and owned['rescue_active'] == 0 and owned['nav_state'] == hold
            and owned['acquired_nav_state_timestamp'] == acquisition.activation_timestamp
            and f"{int(owned['token[0]']):016x}{int(owned['token[1]']):016x}" == acquisition.token
            and control['flag_control_auto_enabled'] == 1 and control['flag_control_position_enabled'] == 1
            and control['flag_control_offboard_enabled'] == 0)
        disjoint = (all(np.isfinite(lateral[name]) for name in ('course', 'lateral_acceleration'))
            and np.isnan(lateral['airspeed_direction']) and np.isfinite(longitudinal['altitude'])
            and all(np.isnan(longitudinal[name]) for name in
                    ('equivalent_airspeed', 'height_rate', 'pitch_direct', 'throttle_direct')))
        if correlated and disjoint:
            result['classification'] = 'native_hold_disjoint'
    except (KeyError, IndexError, TypeError, ValueError):
        pass  # Missing/ambiguous raw witnesses cannot relax the endpoint refusal.
    return result


def ownership_interval(log, acquisition, receipt, *, vehicle_type, initial_altitude_m,
                       phase_exit_required=False, publication_counter_delta=None,
                       run_directory=None, adapter_bundle=None, adapter_file_manifest=None, build_repository=None):
    """Native clocks define pursuit and retained-authority/drain intervals separately.

    Shared setpoint topics after release can belong to native Hold/Transition;
    their timestamps alone cannot identify an obsolete external publisher.
    Wire barriers and the original adapter counter plateau are separate gates.
    """
    acquisition = NativeAcquisitionContext.from_payload(acquisition)
    if vehicle_type not in (1, 2):
        raise ValueError("native_guidance_vehicle_type_unsupported")
    receipt = NativeReleaseReceipt.from_payload(receipt)
    receipt.require_match(acquisition.identity, acquisition.runtime_id, acquisition.token, acquisition)
    if not receipt.released or log.dropouts or log.file_corruption:
        raise ValueError("native_guidance_log_or_release_unqualified")
    owned = log.get_dataset('owned_mode_status').data
    stamp = owned['timestamp'].astype(np.int64)
    word = lambda name: np.array([f'{int(a):016x}{int(b):016x}' for a, b in
                                 zip(owned[name + '[0]'], owned[name + '[1]'])])
    if (any(str(int(uid)) != acquisition.identity.binding.aircraft_uid for uid in owned['autopilot_uid'])
            or np.any(word('incarnation') != acquisition.firmware_incarnation)):
        raise ValueError("native_guidance_log_identity_changed")
    token = word('token') == acquisition.token
    active = token & owned['owner_active'].astype(bool)
    start = acquisition.activation_timestamp
    first = np.flatnonzero(active)
    if not len(first) or not start <= int(stamp[first[0]]) <= start + 750000:
        raise ValueError("native_guidance_acquisition_start_missing")
    released = np.flatnonzero((np.arange(len(stamp)) > first[0]) & ~active)
    if not len(released):
        raise ValueError("native_guidance_authority_end_missing")
    inactive_witness = int(stamp[released[0]])
    vehicle = log.get_dataset('vehicle_status').data
    mode_exits = np.flatnonzero(vehicle['nav_state_timestamp'] > start)
    if not len(mode_exits):
        raise ValueError('native_guidance_external_mode_exit_epoch_missing')
    end = int(vehicle['nav_state_timestamp'][mode_exits[0]])
    mode_exit_publication = int(vehicle['timestamp'][mode_exits[0]])
    if not (start < end <= mode_exit_publication <= end + 750000
            and abs(inactive_witness - end) <= 750000):
        raise ValueError('native_guidance_external_mode_exit_uncorroborated')
    if receipt.outcome == 'hold_confirmed' and receipt.observed_nav_state_timestamp != end:
        raise ValueError('native_guidance_Hold_epoch_mismatch')
    status_window = stamp[(stamp >= start) & (stamp <= max(end, inactive_witness))]
    if len(status_window) < 2 or np.any(np.diff(status_window) <= 0) or np.diff(status_window).max() > 750000:
        raise ValueError('native_guidance_authority_status_coverage_missing')
    if np.any(active & (stamp > inactive_witness)):
        raise ValueError("native_guidance_retired_owner_reactivated")
    for field, expected in (('source_revision', acquisition.source_revision),
                            ('source_nav_state_timestamp', acquisition.source_nav_state_timestamp),
                            ('source_nav_state', acquisition.source_nav_state),
                            ('acquired_nav_state_timestamp', start)):
        if np.any(owned[field][active] != expected):
            raise ValueError("native_guidance_owner_context_changed:" + field)
    if np.any(owned['rescue_active'][active]) or np.any(owned['registration_id'][active] == 0):
        raise ValueError("native_guidance_owner_rescue_or_unregistered")
    if np.any(owned['nav_state'][active] != acquisition.mode_id):
        raise ValueError('native_guidance_authority_mode_changed')
    exited = np.flatnonzero((vehicle['timestamp'] >= start) &
        (vehicle['in_transition_mode'].astype(bool) | (vehicle['vehicle_type'] != vehicle_type)))
    phase_end = int(vehicle['timestamp'][exited[0]]) if len(exited) else None
    if phase_exit_required and phase_end is None:
        raise ValueError("native_guidance_phase_exit_missing")
    pursuit_end = min(end, inactive_witness, phase_end) if phase_end is not None else min(end, inactive_witness)
    if pursuit_end <= start:
        raise ValueError("native_guidance_pursuit_interval_empty")
    topics = ('trajectory_setpoint',) if vehicle_type == 1 else (
        'fixed_wing_lateral_setpoint', 'fixed_wing_longitudinal_setpoint')
    gaps, receipts = {}, {}
    for name in topics:
        published = log.get_dataset(name).data['timestamp'].astype(np.int64)
        ticks = published[(published >= start) & (published < end)]
        if not len(ticks) or np.any(np.diff(ticks) <= 0):
            raise ValueError("native_guidance_authority_publications_missing:" + name)
        receipts[name] = ticks
        gaps[name] = dict(samples=len(ticks), maximum_gap_s=int(np.diff(np.r_[start, ticks, end]).max()) / 1e6,
            samples_at_authority_end=int(np.sum(published == end)),
            interval_us=[start, end], includes_retained_authority_and_neutral_drain=True)
    publication_samples = {name: gap['samples'] for name, gap in gaps.items()}
    fw_timestamp_matches = None if vehicle_type == 1 else len(np.intersect1d(*receipts.values()))
    source, source_error = None, 'Canonical runtime provenance not supplied'
    if run_directory is not None:
        try:
            source = _source_provenance(run_directory, acquisition, adapter_bundle=adapter_bundle,
                adapter_file_manifest=adapter_file_manifest, build_repository=build_repository)
            source_error = None
        except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration) as error:
            source_error = type(error).__name__ + ':' + str(error)
    mode_window = (vehicle['timestamp'] >= start) & (vehicle['timestamp'] < end)
    mode_exclusive = (np.any(mode_window) and np.all(vehicle['nav_state'][mode_window] == acquisition.mode_id)
        and np.all(vehicle['nav_state_timestamp'][mode_window] == start)
        and not np.any(vehicle['accepts_offboard_setpoints'][mode_window])
        and not np.any(active & (stamp >= end)))
    right_edge = _right_edge(log, topics, end, acquisition, receipt, source)
    source_attributed = bool(source is not None and mode_exclusive and _exclusive_payloads(log, topics, start, end)
        and right_edge['classification'] in ('none', 'native_hold_disjoint'))
    position = log.get_dataset('vehicle_local_position').data
    home = log.get_dataset('home_position').data
    pose_t = position['timestamp'].astype(np.int64)
    window = (pose_t >= start) & (pose_t < pursuit_end)
    home_i = np.searchsorted(home['timestamp'], pose_t, side='right') - 1
    if (not np.any(window) or np.any(home_i[window] < 0)
            or not np.all(home['valid_alt'][home_i[window]])):
        raise ValueError("native_guidance_pursuit_altitude_reference_missing")
    altitude = position['ref_alt'][window] - position['z'][window] - home['alt'][home_i[window]]
    pose_flags = all(np.all(position[name][window]) for name in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'))
    pose_reference_stable = all(len(np.unique(position[name][window])) == 1 for name in (
        'ref_timestamp', 'ref_alt', 'xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter', 'heading_reset_counter'))
    attitude = log.get_dataset('vehicle_attitude').data
    attitude_t = attitude['timestamp'].astype(np.int64)
    aq = (attitude_t >= start) & (attitude_t < pursuit_end)
    quaternions = np.array([attitude['q[' + str(i) + ']'][aq] for i in range(4)])
    attitude_fresh = (np.any(aq) and attitude_t[aq][0] - start <= 750000
        and pursuit_end - attitude_t[aq][-1] <= 750000 and len(attitude_t[aq]) >= 2
        and np.all((np.diff(attitude_t[aq]) >= 0) & (np.diff(attitude_t[aq]) <= 750000))
        and np.all((np.diff(attitude['timestamp_sample'][aq].astype(np.int64)) > 0)
                   & (np.diff(attitude['timestamp_sample'][aq].astype(np.int64)) <= 750000))
        and len(np.unique(attitude['quat_reset_counter'][aq])) == 1
        and np.all(np.isfinite(quaternions)) and np.all(np.sum(quaternions ** 2, axis=0) > 0.)
        and np.all((attitude['timestamp_sample'][aq] > 0) &
                   (attitude_t[aq] - attitude['timestamp_sample'][aq].astype(np.int64) >= 0) &
                   (attitude_t[aq] - attitude['timestamp_sample'][aq].astype(np.int64) <= 750000)))
    truth = log.get_dataset('vehicle_local_position_groundtruth').data
    truth_t = truth['timestamp'].astype(np.int64)
    anchor = int(np.searchsorted(truth_t, start, side='right')) - 1
    truth_window = (truth_t >= start) & (truth_t < pursuit_end)
    if anchor < 0 or start - truth_t[anchor] > 750000 or not np.any(truth_window):
        raise ValueError("native_guidance_truth_entry_missing")
    ground = truth['z'][anchor] - truth['z'][truth_window]
    raw_pose_finite = all(np.all(np.isfinite(data[name][selected]))
        for data, selected in ((position, window), (truth, truth_window))
        for name in ('x', 'y', 'z', 'vx', 'vy', 'vz'))
    pose_sample_age = pose_t[window] - position['timestamp_sample'][window].astype(np.int64)
    pose_sample_fresh = (np.all(position['timestamp_sample'][window] > 0)
        and np.all((pose_sample_age >= 0) & (pose_sample_age <= 750000)))
    for times in (pose_t[window], truth_t[truth_window]):
        if (len(times) < 2 or times[0] - start > 750000 or pursuit_end - times[-1] > 750000
                or np.any(np.diff(times) <= 0) or int(np.diff(times).max()) > 750000):
            raise ValueError("native_guidance_full_pursuit_pose_window_missing")
    if not np.all(np.isfinite(altitude)) or not np.all(np.isfinite(ground)):
        raise ValueError("native_guidance_nonfinite_pursuit_pose")
    maximum = float(np.max(np.abs(altitude - initial_altitude_m)))
    ground_maximum = float(np.max(np.abs(ground)))
    checks = dict(pursuit_altitude_within_2m=maximum <= 2., truth_pursuit_altitude_within_2m=ground_maximum <= 2.,
        source_pose_flags_and_reference_stable=bool(pose_flags and pose_reference_stable),
        full_raw_pose_finite_and_fresh=bool(raw_pose_finite and pose_sample_fresh),
        actual_attitude_fresh=bool(attitude_fresh), native_publication_source_attributed=source_attributed,
        authority_publication_gaps_within_100ms=all(item['maximum_gap_s'] <= .100 for item in gaps.values()))
    return dict(passed=all(checks.values()), checks=checks,
        pursuit_interval_us=[start, pursuit_end], retained_authority_interval_us=[start, end],
        first_active_status_publication_us=int(stamp[first[0]]),
        inactive_status_publication_us=inactive_witness, native_mode_exit_epoch_us=end,
        native_phase_exit_us=phase_end, maximum_pursuit_altitude_error_m=maximum,
        maximum_truth_pursuit_excursion_m=ground_maximum, truth_reference_native_us=int(truth_t[anchor]),
        publication_gaps=gaps, original_owner_reactivation=False,
        source_attribution='exclusive reviewed producer; received-topic cadence' if source_attributed else 'UNKNOWN; not qualified',
        publication_provenance=source, publication_provenance_error=source_error,
        native_counter_delta=publication_counter_delta, native_topic_samples=publication_samples,
        native_right_edge=right_edge,
        fw_exact_timestamp_matches_diagnostic=fw_timestamp_matches,
        per_command_delivery='UNKNOWN; API calls and logged receipts are different observations',
        full_native_transition_excluded_from_pursuit_gate=True,
        same_tick_publication_order='not resolved by shared topic timestamps; wire/counter fences are independent')
