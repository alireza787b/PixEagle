#!/usr/bin/env python3
"""Two explicit native component Starts around one pilot front transition.

One fresh isolated simulator; shared canonical bootstrap and vector runner.
No App startup, hardware, native maneuver tuning or target-clock reset.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from classes.aircraft_state import AircraftState, AirframePhase  # noqa: E402
from classes.native_guidance import NativeAcquisitionContext, NativeGuidanceClient  # noqa: E402
from tools import run_native_transition_baseline as base  # noqa: E402
from tools import run_native_vector_sih as vector  # noqa: E402
from tools.native_guidance_evidence import ownership_interval  # noqa: E402

CASE = base.SCENARIOS / 'gazebo-guidance-phase-exit.json'


def case(path):
    value = json.loads(Path(path).read_text())
    if (set(value) != {'schema_version', 'native_fixture', 'target', 'mc', 'fw'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['native_fixture'] != 'gazebo-quadtailsitter-hold-cycle.json'):
        raise ValueError('Explicit stock Gazebo guidance fixture required')
    expected = {'target': {'forward_m', 'right_m', 'speed_m_s', 'coverage_s'},
                'mc': {'duration_s', 'transition_at_s', 'requested_speed_m_s'}, 'fw': {'duration_s'}}
    if any(set(value[key]) != names or any(not base.finite(x) for x in value[key].values())
           for key, names in expected.items()):
        raise ValueError('Finite explicit world-target and timing fixture required')
    if (not 0. < value['mc']['transition_at_s'] < value['mc']['duration_s'] <= 60.
            or not 1. <= value['fw']['duration_s'] <= 60.
            or not 0. < value['mc']['requested_speed_m_s'] <= 5.
            or not 100. <= value['target']['forward_m'] <= 2000.
            or not 0. <= value['target']['speed_m_s'] < value['mc']['requested_speed_m_s']
            or not 240. <= value['target']['coverage_s'] <= 600.):
        raise ValueError('Bounded observable guidance fixture required')
    return value


def world_scenarios(output, initial, mount, fixture, *, clock=time.monotonic):
    """Anchor once to measured MC pose/heading, then preserve one world trajectory."""
    state = AircraftState.from_payload(initial['aircraft_state'])
    origin = initial['vehicle_pose']['vehicle_ned']
    yaw = state.navigation_heading_rad
    forward, right = (math.cos(yaw), math.sin(yaw)), (-math.sin(yaw), math.cos(yaw))
    target = fixture['target']
    first = [origin[i] + target['forward_m'] * forward[i] + target['right_m'] * right[i] for i in (0, 1)] + [origin[2]]
    last = [first[i] + target['speed_m_s'] * target['coverage_s'] * forward[i] for i in (0, 1)] + [first[2]]
    raw = yaml.safe_load(vector.component_profile('gm_velocity_vector').template.read_text())
    raw.update(airframe='vtol', mount_type=mount, evidence_provenance='px4_gazebo')
    raw['follower']['command_contract'] = 'vtol_external'
    raw['target']['waypoints'] = [dict(time_s=0., position_ned=first),
        dict(time_s=target['coverage_s'], position_ned=last)]
    original = output / 'original-world-target.yaml'
    original.write_text(yaml.safe_dump(raw, sort_keys=False))
    artifact = output / 'target-clock.json'
    base.write(artifact, dict(schema_version=1, target_id=output.name + '-world-target', frame='local_ned',
        host_monotonic_origin_s=clock(), host_boot_id=vector.host_boot_id(),
        scenario_yaml=original.name, scenario_sha256=base.digest(original)))
    base.write(output / 'target-anchor.json', dict(aircraft_state=initial['aircraft_state'],
        vehicle_pose=initial['vehicle_pose'], navigation_heading_rad=yaw, fixture=target,
        target_start_ned=first, target_end_ned=last))
    paths = []
    for name in ('mc', 'fw'):
        scenario = dict(raw)
        scenario['faults'] = ([dict(kind='pilot_transition', at_s=fixture['mc']['transition_at_s'],
                                   requested_phase='fixed_wing')] if name == 'mc' else [])
        path = output / (name + '-scenario.yaml')
        path.write_text(yaml.safe_dump(scenario, sort_keys=False))
        paths.append(path)
    return paths, artifact


def require_fresh_start(previous, current):
    first, second = map(NativeAcquisitionContext.from_payload, (previous, current))
    if (first.identity == second.identity or first.token == second.token
            or second.activation_timestamp <= first.activation_timestamp
            or first.firmware_incarnation != second.firmware_incarnation
            or first.identity.binding.aircraft_uid != second.identity.binding.aircraft_uid):
        raise ValueError('Fresh explicit Start requires a new identity/token/native activation')


def next_start_allowed(result, settled):
    checks = result.get('response_checks', {})
    packet = settled.get('last_packet', {})
    state = AircraftState.from_payload(packet['aircraft_state'])
    return (all(checks.get(key) is True for key in ('phase_exit_release_confirmed',
        'no_write_after_phase_witness', 'no_publication_after_stop', 'no_publication_failure',
        'pilot_transition_command_succeeded', 'requested_phase_settled', 'backend_transition_ended'))
        and state.phase is AirframePhase.FIXED_WING and not state.rescue_active
        and packet.get('owner_confirmed') is False and packet.get('rescue_active') is False
        and packet.get('phase_status_fresh') is True
        and packet.get('release_pending') is False and packet.get('neutral_drain_active') is False)


async def execute(args, fixture):
    from pyulog import ULog

    native = base.scenario(base.SCENARIOS / fixture['native_fixture'])
    runtime, boot, simulator = base.verified_runtime(args, native)
    if simulator != 'gazebo' or runtime.manifest['build'].get('resource_variant'):
        raise ValueError('This first guidance case requires the verified stock measured-model image')
    result = dict(passed=False, scope='native_guidance_ownership_component', mount=args.mount,
        application_startup_qualified=False, same_application_connection_qualified=False,
        new_observer_connection_per_start=True, hardware_qualified=False, errors=[], sessions=[])
    client = start = None
    try:
        runtime.start()
        client = NativeGuidanceClient(runtime.socket)
        capabilities, binding = await base.admit_native_runtime(runtime, client, native, boot)
        with (runtime.output / 'preparation-observations.jsonl').open('x') as stream:
            initial = await base.wait_stable(client, runtime, binding, capabilities.runtime_id, stream)
        start = runtime.clock('start')
        await client.close()
        client = None
        scenarios, target_clock = world_scenarios(runtime.output, initial, args.mount, fixture)
        for index, name in enumerate(('mc', 'fw')):
            if index:
                settled = json.loads((runtime.output / 'mc-follow/post-transition-settled.json').read_text())
                if not next_start_allowed(result['sessions'][0], settled):
                    raise ValueError('Original owner/phase not qualified for the next explicit Start')
            runtime.verify()
            stage = SimpleNamespace(socket=runtime.socket, output=runtime.output / (name + '-follow'),
                container=runtime.primary, instance=0, config=args.config, follower='gm_velocity_vector',
                mount=args.mount, altitude=False, duration=fixture[name]['duration_s'], stable_timeout=90.,
                test_altitude=30., altitude_tolerance=2., scenario=scenarios[index], target_clock=target_clock,
                expect_handoff='aircraft_transition_observed' if index == 0 else None,
                mc_request=fixture['mc']['requested_speed_m_s'] if index == 0 else None,
                initial_phase='multicopter' if index == 0 else 'fixed_wing',
                simulation_build_manifest=args.simulation_build_manifest, build_repository=args.build_repository)
            value = await vector.run(stage, runtime.isolation)
            result['sessions'].append(value)
            if index:
                require_fresh_start(json.loads((runtime.output / 'mc-follow/acquisition.json').read_text()),
                    json.loads((runtime.output / 'fw-follow/acquisition.json').read_text()))
    except BaseException as error:
        result['errors'].append(type(error).__name__ + ':' + str(error))
    finally:
        if client is not None:
            try:
                await client.close()
            except BaseException as error:
                result['errors'].append('observer_close:' + str(error))
        if runtime.output.exists():
            result['errors'].extend(runtime.cleanup())
    if start is not None:
        try:
            files = list((runtime.output / 'simulator/rootfs').rglob('*.ulg'))
            if len(files) != 1:
                raise ValueError('One closed original ULog required')
            log = ULog(str(files[0]))
            owned = log.get_dataset('owned_mode_status').data
            incarnations = {f'{int(a):016x}{int(b):016x}' for a, b in zip(owned['incarnation[0]'], owned['incarnation[1]'])}
            if incarnations != {start['incarnation']}:
                raise ValueError('Native incarnation changed within the full capture')
            end = dict(incarnation=start['incarnation'], source_clock_us=int(log.last_timestamp))
            result['full_native_capture'] = base.audit_ulog(runtime.output / 'simulator/rootfs', start, end, parser=lambda _: log)
            result['native_transition_performance_separate'] = True
            metrics = []
            contract = vector.transition_source_contract(runtime.isolation, build_repository=args.build_repository)
            for name, phase, value in zip(('mc', 'fw'), ('multicopter', 'fixed_wing'), result['sessions']):
                context = json.loads((runtime.output / (name + '-follow/acquisition.json')).read_text())
                metrics.append(ownership_interval(log, context, value['handoff']['release_receipt'],
                    vehicle_type=contract['vehicle_types'][phase], initial_altitude_m=value['initial_relative_altitude_m'],
                    publication_counter_delta=value['native_publication_counter']['after'] - value['native_publication_counter']['before'],
                    phase_exit_required=name == 'mc'))
            result['native_ownership_intervals'] = metrics
            tokens = {json.loads((runtime.output / (name + '-follow/acquisition.json')).read_text())['token']
                      for name in ('mc', 'fw') if (runtime.output / (name + '-follow/acquisition.json')).exists()}
            active_tokens = {f'{int(a):016x}{int(b):016x}' for a, b, active in
                zip(owned['token[0]'], owned['token[1]'], owned['owner_active']) if active}
            if active_tokens != tokens:
                raise ValueError('Native authority outside the two explicit acquisitions')
            result['passed'] = (len(metrics) == 2 and all(m['passed'] for m in metrics)
                and all(s['passed'] for s in result['sessions']) and not result['errors'])
        except BaseException as error:
            result['errors'].append('closed_ownership_audit:' + str(error))
    if runtime.output.exists():
        base.write(runtime.output / 'result.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--case-fixture', type=Path, default=CASE)
    parser.add_argument('--mount', choices=('HORIZONTAL', 'VERTICAL'), required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--simulation-build-manifest', type=Path)
    parser.add_argument('--build-repository', type=Path)
    parser.add_argument('--adapter-bundle', type=Path)
    parser.add_argument('--adapter-file-manifest', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/config_default.yaml')
    args = parser.parse_args(argv)
    fixture = case(args.case_fixture)
    if not args.execute:
        print(json.dumps(dict(execute=False, case=fixture, mount=args.mount, owner_altitude_gate_m=2.,
            retained_authority_gap_s=.100, application_startup_qualified=False), indent=2))
        return 0
    if any(getattr(args, key) is None for key in ('output', 'simulation_build_manifest', 'adapter_bundle', 'adapter_file_manifest')):
        parser.error('Explicit execution requires new output, verified build manifest and pinned adapter paths')
    if args.output.exists() or args.output.is_symlink():
        parser.error('Use a fresh output; old evidence is never overwritten')
    value = asyncio.run(execute(args, fixture))
    print(json.dumps(value, indent=2))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
