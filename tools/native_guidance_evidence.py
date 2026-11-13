"""Closed-log evidence for a native pursuit; no controller or runtime actions."""
from __future__ import annotations

import numpy as np

from classes.native_guidance import NativeAcquisitionContext, NativeReleaseReceipt


def ownership_interval(log, acquisition, receipt, *, vehicle_type, initial_altitude_m,
                       phase_exit_required=False, publication_counter_delta=None):
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
    gaps = {}
    for name in topics:
        published = log.get_dataset(name).data['timestamp'].astype(np.int64)
        ticks = published[(published >= start) & (published < end)]
        if not len(ticks) or np.any(np.diff(ticks) <= 0):
            raise ValueError("native_guidance_authority_publications_missing:" + name)
        gaps[name] = dict(samples=len(ticks), maximum_gap_s=int(np.diff(np.r_[start, ticks, end]).max()) / 1e6,
            samples_at_authority_end=int(np.sum(published == end)),
            interval_us=[start, end], includes_retained_authority_and_neutral_drain=True)
    if vehicle_type == 2:
        paired = np.intersect1d(log.get_dataset(topics[0]).data['timestamp'],
                               log.get_dataset(topics[1]).data['timestamp']).astype(np.int64)
        paired = paired[(paired >= start) & (paired < end)]
        if not len(paired):
            raise ValueError('native_guidance_coherent_fw_publications_missing')
        gaps['coherent_fw_pair'] = dict(samples=len(paired),
            maximum_gap_s=int(np.diff(np.r_[start, paired, end]).max()) / 1e6,
            interval_us=[start, end], includes_retained_authority_and_neutral_drain=True)
    publication_samples = gaps['trajectory_setpoint' if vehicle_type == 1 else 'coherent_fw_pair']['samples']
    source_attributed = (type(publication_counter_delta) is int and publication_counter_delta == publication_samples
        and (phase_end is None or end <= phase_end)
        and not any(item.get('samples_at_authority_end', 0) for item in gaps.values()))
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
        and np.all((np.diff(attitude_t[aq]) > 0) & (np.diff(attitude_t[aq]) <= 750000))
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
        source_attribution='counter+native-owner corroborated' if source_attributed else 'UNKNOWN; not qualified',
        native_counter_delta=publication_counter_delta, native_topic_samples=publication_samples,
        full_native_transition_excluded_from_pursuit_gate=True,
        same_tick_publication_order='not resolved by shared topic timestamps; wire/counter fences are independent')
