#!/usr/bin/env python3
"""Explicit, isolated PX4 native-ownership qualification; never arm or take off.

The production binding/commander publish phase-safe level-flight baselines only.
This is not target-tracking, application startup, VTOL or physical qualification.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from classes.aircraft_state import (
    AircraftBinding,
    AircraftState,
    AirframePhase,
    GuidanceSessionIdentity,
    finite_number,
)
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy
from classes.follower import FollowerFactory
from classes.native_follow_binding import NativeFollowBinding
from classes.native_guidance import (
    MAX_MESSAGE_BYTES,
    NativeAcquisitionContext,
    NativeGuidanceClient,
    NativeGuidanceError,
    NativeReleaseReceipt,
)
from classes.offboard_commander import OffboardCommander
from classes.parameters import Parameters
from classes.target_continuity import (
    ContinuityContext,
    ContinuityPolicy,
    IdentityVerdict,
    TargetContinuitySupervisor,
    TargetEvidenceSnapshot,
    TargetEvidenceState,
)
from tools.build_native_guidance import verify_extension
from tools.run_native_vector_sih import (
    ObservationConnection,
    archive_configuration,
    attach_component_observer,
    component_profile,
    native_parameters,
    observed_pose_record,
    stable_window,
    verify_simulator,
)
from tools.sih_baseline import verify_source

CASES = ('normal_stop', 'confirmed_owner_eof', 'same_mode_reselection', 'stale_cleanup_new_acquisition')


def source_contract(manifest_path: Path) -> dict:
    """Use constants from the exact verified source, never an assumed registration."""
    source = manifest_path.resolve().parent / 'context/source'
    verify_source(source, ROOT, verify_extension)
    message = source / 'msg/versioned/VehicleStatus.msg'
    values = re.findall(r'(?m)^uint8 NAVIGATION_STATE_EXTERNAL1\s*=\s*(\d+)\s*(?:#[^\n]*)?$', message.read_text())
    hold = re.findall(r'(?m)^uint8 NAVIGATION_STATE_AUTO_LOITER\s*=\s*(\d+)\s*(?:#[^\n]*)?$', message.read_text())
    if len(values) != 1 or len(hold) != 1:
        raise ValueError('ownership_fixture_external_constant_missing')
    owned = source / 'msg/versioned/OwnedModeStatus.msg'
    states = {}
    for name in ('ACQUIRED', 'SUPERSEDED'):
        found = re.findall(rf'(?m)^uint8 STATE_{name}\s*=\s*(\d+)\s*(?:#[^\n]*)?$', owned.read_text())
        if len(found) != 1:
            raise ValueError('ownership_fixture_status_constants_missing')
        states[name.lower()] = int(found[0])
    return {'external1': int(values[0]), 'hold': int(hold[0]), 'source': str(message),
            'sha256': hashlib.sha256(message.read_bytes()).hexdigest(), 'states': states,
            'owned_status_source': str(owned), 'owned_status_sha256': hashlib.sha256(owned.read_bytes()).hexdigest()}


def parse_owned_samples(text: str) -> list[dict]:
    """Only actual uORB publications count; repeated snapshots keep their clock."""
    fields = ('timestamp', 'contract_version', 'intention_revision', 'state', 'source_revision',
              'source_nav_state_timestamp', 'source_nav_state', 'mode_id', 'registration_id',
              'acquired_nav_state_timestamp', 'nav_state', 'nav_state_timestamp', 'source_clock_us')
    samples = []
    for block in re.split(r'(?m)^\s*TOPIC:\s*owned_mode_status[^\n]*\n', text)[1:]:
        sample = {}
        for field in fields:
            suffix = r'(?:\s+\(\d+(?:\.\d+)? seconds ago\))?' if field == 'timestamp' else ''
            match = re.findall(rf'(?m)^\s*{field}:\s*(\d+){suffix}\s*$', block)
            if len(match) != 1:
                raise ValueError(f'ownership_fixture_status_missing:{field}')
            sample[field] = int(match[0])
            bits = 8 if field in ('contract_version', 'state', 'source_nav_state', 'mode_id', 'nav_state') else 64
            if sample[field] >= 2**bits:
                raise ValueError(f'ownership_fixture_status_range:{field}')
        for field in ('available', 'owner_active', 'armed', 'rescue_active'):
            match = re.findall(rf'(?mi)^\s*{field}:\s*(true|false|0|1)\s*$', block)
            if len(match) != 1:
                raise ValueError(f'ownership_fixture_status_missing:{field}')
            sample[field] = match[0].lower() in ('true', '1')
        for field in ('token', 'incarnation'):
            match = re.findall(rf'(?m)^\s*{field}:\s*\[\s*(\d+)\s*,\s*(\d+)\s*\]\s*$', block)
            if len(match) != 1 or any(int(word) >= 2**64 for word in match[0]):
                raise ValueError(f'ownership_fixture_status_missing:{field}')
            sample[field] = ''.join(f'{int(word):016x}' for word in match[0])
        uid = re.findall(r'(?m)^\s*autopilot_uid:\s*(\d+)\s*$', block)
        if len(uid) > 1:
            raise ValueError('ownership_fixture_status_uid_ambiguous')
        sample['autopilot_uid'] = int(uid[0]) if uid else None
        samples.append(sample)
    if not samples:
        raise ValueError('ownership_fixture_status_not_observed')
    return samples


def matches_receipt(sample: dict, acquisition: NativeAcquisitionContext) -> bool:
    return (sample.get('autopilot_uid') is None
            or str(sample['autopilot_uid']) == acquisition.identity.binding.aircraft_uid) and all(sample.get(key) == value for key, value in {
        'token': acquisition.token, 'incarnation': acquisition.firmware_incarnation,
        'source_revision': acquisition.source_revision, 'source_nav_state': acquisition.source_nav_state,
        'source_nav_state_timestamp': acquisition.source_nav_state_timestamp, 'mode_id': acquisition.mode_id,
        'acquired_nav_state_timestamp': acquisition.activation_timestamp,
    }.items())


def takeover_witness(samples: list[dict], acquisition: NativeAcquisitionContext, acquired: dict, *, superseded_state: int) -> dict | None:
    return next((sample for sample in samples if matches_receipt(sample, acquisition)
        and sample['state'] == superseded_state and not sample['owner_active'] and sample['available']
        and sample['registration_id'] == acquired['registration_id'] and sample['registration_id'] != 0
        and sample['source_clock_us'] > acquired['source_clock_us'] and sample['timestamp'] > acquired['timestamp']
        and sample['intention_revision'] > acquired['intention_revision']
        and sample['nav_state'] == acquisition.mode_id
        and sample['nav_state_timestamp'] == acquisition.activation_timestamp), None)


def wire_requests(events, *, after, before=float('inf')):
    requests = []
    for event in events:
        if event.get('direction') != 'request_forward_attempt' or not after <= event['timestamp'] <= before:
            continue
        if 'eof' in event:
            if event['eof'] is True and 'value' not in event:
                continue
            raise ValueError('ownership_fixture_wire_eof_invalid')
        value = event.get('value')
        if (not isinstance(value, dict) or not isinstance(value.get('operation'), str)
                or not value['operation'] or not isinstance(value.get('payload'), dict)):
            raise ValueError('ownership_fixture_wire_request_invalid')
        requests.append(value)
    return requests


def eof_precedes_intent_expiry(events, *, after, run_started):
    intents = [event for event in events if event.get('direction') == 'request_forward_attempt'
               and event.get('value', {}).get('operation') == 'intent' and event['timestamp'] <= after]
    if not intents:
        return False
    last = intents[-1]
    expires = last['value']['payload']['expires_at_monotonic_s']
    return any(event.get('direction') == 'backend_socket_closed' and event['connection'] == last['connection']
               and after <= event['timestamp'] and run_started + event['timestamp'] < expires for event in events)


def isolated_cli(socket: Path, isolation: dict, alias: str, *arguments: str) -> dict:
    if isolation.get('firmware_build') is None or alias not in ('px4-listener', 'px4-commander'):
        raise ValueError('ownership_fixture_verified_build_required')
    executable = str(Path(isolation['process']['args'][0]).with_name(alias))
    argv = ['docker', 'exec', '--user', str(socket.stat().st_uid), isolation['container_id'],
            executable, '--instance', str(isolation['instance']), *arguments]
    started = time.monotonic()
    result = subprocess.run(argv, text=True, capture_output=True, timeout=15, check=False)
    return {'argv': argv, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
            'started_at_monotonic_s': started, 'finished_at_monotonic_s': time.monotonic()}


class WireRecorder:
    """Same-UID Unix byte relay; never creates a command, reply or publisher."""
    def __init__(self, frontend: Path, backend: Path, log):
        self.frontend, self.backend, self.log = frontend, backend, log
        self.server = None
        self.tasks = set()
        self.connection_id = 0

    async def __aenter__(self):
        if self.frontend.exists() or os.geteuid() != self.backend.stat().st_uid:
            raise ValueError('ownership_fixture_socket_owner_mismatch')
        self.server = await asyncio.start_unix_server(self._connection, str(self.frontend), limit=MAX_MESSAGE_BYTES)
        self.frontend.chmod(0o600)
        return self

    async def __aexit__(self, *_):
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        self.frontend.unlink(missing_ok=True)

    async def _connection(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.connection_id += 1
        connection = self.connection_id
        backend_writer = None
        peers = []
        try:
            backend_reader, backend_writer = await asyncio.open_unix_connection(str(self.backend), limit=MAX_MESSAGE_BYTES)

            async def forward(source, sink, direction):
                while raw := await source.readline():
                    if len(raw) > MAX_MESSAGE_BYTES:
                        raise ValueError('ownership_fixture_wire_oversized')
                    value = json.loads(raw)
                    self.log('wire.jsonl', {'connection': connection, 'direction': direction, 'value': value})
                    sink.write(raw)
                    await sink.drain()
                self.log('wire.jsonl', {'connection': connection, 'direction': direction, 'eof': True})

            peers = [asyncio.create_task(forward(reader, backend_writer, 'request_forward_attempt')),
                     asyncio.create_task(forward(backend_reader, writer, 'actual_backend_reply'))]
            done, _ = await asyncio.wait(peers, return_when=asyncio.FIRST_COMPLETED)
            for finished in done:
                finished.result()
        except (OSError, ValueError) as error:
            self.log('wire.jsonl', {'connection': connection, 'error': str(error)})
        finally:
            for peer in peers:
                peer.cancel()
            await asyncio.gather(*peers, return_exceptions=True)
            for stream in (writer, backend_writer):
                if stream is not None:
                    stream.close()
            if backend_writer is not None:
                self.log('wire.jsonl', {'connection': connection, 'direction': 'backend_socket_closed'})
            self.tasks.discard(task)


@dataclass
class Session:
    client: NativeGuidanceClient
    connection: ObservationConnection
    guidance: object
    binding: NativeFollowBinding
    commander: OffboardCommander
    follower: object
    run_started: float
    acquisition: NativeAcquisitionContext | None = None
    previous_pose_timestamp: int | None = None
    baseline_producer: asyncio.Task | None = None


async def stable_aircraft(client, connection, *, timeout, altitude, hold_mode, log):
    deadline = time.monotonic() + timeout
    window = []
    while time.monotonic() < deadline:
        packet = await client.observe()
        log('observations.jsonl', {'stage': 'stable_readiness', 'value': packet})
        if (packet['fresh'] and not packet['rescue_active'] and packet.get('vehicle_pose')
                and packet.get('nav_state') == hold_mode):
            state = AircraftState.from_payload(packet['aircraft_state'])
            if state.is_vtol or state.phase is not AirframePhase.FIXED_WING:
                raise ValueError('ownership_fixture_requires_pure_fixed_wing')
            connection.commit_aircraft_state(state)
            if connection.retain_packet(state, packet):
                if not window or state.sequence > window[-1].sequence:
                    window = (window + [state])[-7:]
                if stable_window(window, expected_altitude_m=altitude):
                    log('stable-flight.jsonl', {'states': [asdict(item) for item in window]})
                    return state
        else:
            window = []
        await asyncio.sleep(.5)
    raise ValueError('stable_airborne_window_not_reached')


def create_session(client, connection, capabilities, identity, config, profile, log, *, run_started) -> Session:
    follower = FollowerFactory.create_follower(profile.mode, connection, (.5, .5))
    supervisor = TargetContinuitySupervisor(ContinuityPolicy.resolve(config['TargetContinuity'], profile.mode,
                                                                   AirframePhase.FIXED_WING))
    supervisor.reset_session(session_epoch=1, reason='ownership_component_baseline')
    guidance = follower.create_airframe_session(identity, capabilities,
        confirmation_s=config['Follower']['AIRFRAME_PHASE_CONFIRMATION_S'], observation_timeout_s=.75,
        transition_timeout_s=config['Follower']['VTOL_TRANSITION_TIMEOUT_S'],
        fixed_wing_policy=FixedWingGuidancePolicy.from_mapping(config['FixedWingGuidance']))
    # No tracker or target is fabricated. The native phase-confirmation baseline is the test objective.
    def no_target():
        return TargetEvidenceSnapshot(TargetEvidenceState.ABSENT, time.monotonic(), 1, None,
                                      IdentityVerdict.UNCONFIRMED, 'ownership_qualification_no_target')
    base = ContinuityContext('PX4_NATIVE', AirframePhase.FIXED_WING, 'fixed_wing_external', True, False, True)
    binding = NativeFollowBinding(guidance, connection, client, supervisor, profile_name=profile.mode,
        continuity_config=config['TargetContinuity'], target_evidence=no_target, context=lambda: base,
        circuit_breaker=lambda: False)
    attach_component_observer(binding, connection, log, started=run_started)

    def published(event):
        log('trace/offboard_publish_trace.jsonl', {'record_type': 'offboard_publish',
            'publish_success': event['publish_status']['last_publish_success'],
            'command_intent': None if event['command_intent'] is None else asdict(event['command_intent'])})

    commander = OffboardCommander(connection, follower.setpoint_handler, command_rate_hz=20., command_ttl_s=.3,
                                  command_transport=binding.transport, on_publish_result=published)
    return Session(client, connection, guidance, binding, commander, follower, run_started)


async def activate_session(session, log):
    baseline = await session.binding.engage()
    session.acquisition = session.client.acquisition_context
    session.follower.bind_airframe_session(session.guidance)
    log('acquisitions.jsonl', {'acquisition': asdict(session.acquisition)})
    if not session.commander.submit_intent(baseline) or not await session.commander.start():
        raise ValueError('ownership_fixture_publisher_not_started')
    session.baseline_producer = asyncio.create_task(feed_baselines(session, log))


async def feed_baselines(session: Session, log):
    """Test stimulus only; OffboardCommander remains the sole publisher."""
    while session.commander.running:
        if not session.binding.owner_confirmed or session.commander.failed_publishes:
            raise ValueError('ownership_fixture_baseline_owner_unhealthy')
        if not session.commander.submit_intent(session.guidance.baseline()):
            raise ValueError('ownership_fixture_baseline_rejected')
        packet = session.connection.last_packet
        log('trace/follower_state.jsonl', {'baseline_only': True, 'guidance_identity': asdict(session.guidance.identity),
                                          'publisher': session.commander.get_status()})
        if packet is not None:
            pose = observed_pose_record(packet, follow_start=session.run_started,
                                        previous_timestamp_us=session.previous_pose_timestamp)
            if pose is not None:
                log('px4/pose_trace.jsonl', pose)
                session.previous_pose_timestamp = pose['px4_timestamp_us']
        await asyncio.sleep(.05)


async def drive(session: Session, duration, log):
    await asyncio.sleep(duration)
    if session.baseline_producer.done():
        session.baseline_producer.result()
        raise ValueError('ownership_fixture_baseline_stopped')
    if not session.binding.owner_confirmed or session.commander.failed_publishes:
        raise ValueError('ownership_fixture_baseline_owner_unhealthy')


async def quiesce(session: Session):
    producer = session.baseline_producer
    if producer is not None:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)
    if await session.commander.stop(publish_final=False) is False:
        raise ValueError('ownership_fixture_publisher_not_quiesced')


async def observe_status(args, isolation, log, *, count=1):
    command = await asyncio.to_thread(isolated_cli, args.socket, isolation, 'px4-listener',
                                      'owned_mode_status', '-n', str(count), '-r', '100')
    log('source-cli.jsonl', {'role': 'read_only_owned_status', **command})
    if command['returncode']:
        raise ValueError('ownership_fixture_status_command_failed')
    return parse_owned_samples(command['stdout'])


async def user_mode(args, isolation, log, mode, *, purpose='same_mode_reselection'):
    if mode not in ('ext1', 'auto:loiter'):
        raise ValueError('ownership_fixture_mode_not_supported')
    command = await asyncio.to_thread(isolated_cli, args.socket, isolation, 'px4-commander', 'mode', mode)
    log('source-cli.jsonl', {'role': 'independent_simulated_operator', 'purpose': purpose, **command})
    if command['returncode']:
        raise ValueError('ownership_fixture_mode_command_failed')


async def confirmed_source(args, isolation, session, contract, log):
    samples = await observe_status(args, isolation, log)
    sample = samples[-1]
    if not (matches_receipt(sample, session.acquisition) and sample['owner_active'] and sample['registration_id'] > 0
            and sample['state'] == contract['states']['acquired']):
        raise ValueError('ownership_fixture_confirmed_owner_not_observed')
    return sample


async def reconcile(session, log):
    result = await session.client.observe_after_release(session.acquisition.identity,
        runtime_id=session.acquisition.runtime_id, mode_id=session.acquisition.mode_id,
        ownership_token=session.acquisition.token, acquisition=session.acquisition)
    log('reconciliation.jsonl', result.wire_payload())
    return result


def coherent_hold(packet, acquisition, hold_mode):
    payload = packet.get('release_receipt')
    if payload is None:
        return False
    receipt = NativeReleaseReceipt.from_payload(payload).require_match(
        acquisition.identity, acquisition.runtime_id, acquisition.token, acquisition, mode_id=acquisition.mode_id)
    epoch = packet.get('nav_state_timestamp')
    return (packet.get('fresh') is True and packet.get('owner_confirmed') is False
            and packet.get('rescue_active') is False and packet.get('nav_state') == hold_mode
            and type(epoch) is int and acquisition.activation_timestamp < epoch < 2**64
            and receipt.released and receipt.observed_nav_state == hold_mode
            and receipt.observed_nav_state_timestamp == epoch)


async def wait_for_coherent_hold(client, acquisition, hold_mode, log, *, clock=time.monotonic, pause=asyncio.sleep):
    """Spend only the first VehicleStatus sample's remaining freshness allowance."""
    started = clock()
    packet = await client.observe()
    health = packet.get('phase_source_health') or {}
    budget = finite_number(health.get('vehicle_status_timeout_s'), 'ownership_status_budget')
    age = finite_number(health.get('vehicle_status_age_s'), 'ownership_status_age')
    if not 0. <= age < budget:
        raise ValueError('ownership_fixture_status_budget_unavailable')
    deadline = started + budget - age
    counts = []
    converged = False
    try:
        async with asyncio.timeout(max(0., deadline - clock())):
            while True:
                counts.append(packet.get('publications'))
                log('hold-coherence-observations.jsonl', packet)
                if clock() >= deadline:
                    raise TimeoutError
                if coherent_hold(packet, acquisition, hold_mode):
                    converged = True
                    return packet, counts
                remaining = deadline - clock()
                if remaining <= 0.:
                    raise TimeoutError
                await pause(min(.1, remaining))
                if clock() >= deadline:
                    raise TimeoutError
                packet = await client.observe()
    except TimeoutError as error:
        raise ValueError('ownership_fixture_hold_coherence_timeout') from error
    finally:
        log('hold-coherence-window.jsonl', {'budget_source': 'initial_vehicle_status_remaining_freshness',
            'vehicle_status_timeout_s': budget, 'initial_vehicle_status_age_s': age,
            'maximum_wait_s': budget - age, 'elapsed_s': clock() - started, 'converged': converged})


async def retired_owner(args, isolation, session, contract, log):
    if session.acquisition.mode_id != contract['external1']:
        raise ValueError('ownership_fixture_ext1_registration_mismatch')
    before = await confirmed_source(args, isolation, session, contract, log)
    watcher = asyncio.create_task(observe_status(args, isolation, log, count=16))
    try:
        await user_mode(args, isolation, log, 'ext1')
        await quiesce(session)
        try:
            packet = await session.client.observe()
            log('observations.jsonl', {'stage': 'after_user_reselection', 'value': packet})
            if packet['owner_confirmed']:
                raise ValueError('ownership_fixture_reselection_did_not_revoke_owner')
        except NativeGuidanceError as error:
            if str(error) != 'native_disconnected' or session.client.session_identity is not None:
                raise
            log('observations.jsonl', {'stage': 'publisher_already_retired_socket', 'terminal_error': str(error)})
        samples = await watcher
        witness = takeover_witness(samples, session.acquisition, before, superseded_state=contract['states']['superseded'])
        if witness is None:
            raise ValueError('ownership_fixture_same_epoch_retirement_not_observed')
        log('takeover-witness.jsonl', witness)
        session.binding.abort('ownership_fixture_confirmed_source_release')
        cleanup_after = log('cleanup-boundaries.jsonl', {'event': 'original_owner_observed_released'})
        return witness, cleanup_after
    finally:
        if not watcher.done():
            await watcher


async def run(args, isolation, contract):
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for subdir in ('trace', 'px4'):
        (output / subdir).mkdir()
    config = yaml.safe_load(args.config.read_text())
    selected = component_profile(args.follower)
    config['FOLLOWER_CIRCUIT_BREAKER'] = False  # Isolated copied configuration only.
    config['Follower']['FOLLOWER_MODE'] = selected.profile.mode
    (output / 'config.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
    Parameters.load_config(output / 'config.yaml', strict_dependents=True)
    configuration = archive_configuration(output)
    tool_source = Path(__file__).read_bytes()
    (output / 'tool-source.py').write_bytes(tool_source)
    handles = {}
    wire = []
    started = time.monotonic()

    def log(name, value):
        record = {'timestamp': time.monotonic() - started, **value}
        if name not in handles:
            handles[name] = (output / name).open('x')
        handles[name].write(json.dumps(record, allow_nan=False) + '\n')
        handles[name].flush()
        if name == 'wire.jsonl':
            wire.append(record)
        return record['timestamp']

    manifest = {'evidence_kind': 'px4_observed_sih', 'qualification': 'native_causal_ownership_component',
        'case': args.case, 'isolation': isolation, 'source_contract': contract, 'configuration': configuration,
        'host_clock': {'basis': 'time.monotonic', 'origin_s': started,
                       'wire_timestamp_semantics': 'seconds_since_origin'},
        'profile': selected.profile.mode, 'baseline_only': True, 'target_tracking_qualified': False,
        'application_startup_qualified': False, 'vtol_qualified': False, 'hardware_qualified': False,
        'lost_engagement_ack_tested': False, 'argv': sys.argv,
        'tool_source_sha256': hashlib.sha256(tool_source).hexdigest(),
        'runtime_source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            'src/classes/native_guidance.py', 'src/classes/native_follow_binding.py',
            'src/classes/native_command_transport.py', 'src/classes/offboard_commander.py',
            'src/classes/vector_guidance_session.py', 'tools/run_native_vector_sih.py')},
        'revision': (await asyncio.to_thread(subprocess.check_output,
            ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True)).strip()}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'source.patch').write_text(await asyncio.to_thread(subprocess.check_output,
        ['git', '-C', str(ROOT), 'diff', 'HEAD'], text=True))
    result = {'passed': False, 'reason': 'not_started', 'case': args.case, 'lost_engagement_ack_tested': False}
    active = None
    client = None
    recorder = None
    socket_directory = None
    try:
        (output / 'px4/parameters-before.txt').write_text(await asyncio.to_thread(native_parameters, args.socket, isolation))
        socket_directory = tempfile.TemporaryDirectory(prefix='pe-own-')
        frontend = Path(socket_directory.name) / 'record.sock'
        recorder = WireRecorder(frontend, args.socket, log)
        await recorder.__aenter__()
        client = NativeGuidanceClient(frontend)
        capabilities = await client.connect()
        log('runtime.jsonl', {'capabilities': asdict(capabilities), 'baseline_only': True})
        if not capabilities.owned_mode_supported:
            raise ValueError('ownership_fixture_contract_unavailable')
        if args.case in ('same_mode_reselection', 'stale_cleanup_new_acquisition') and capabilities.owned_mode_id != contract['external1']:
            raise ValueError('ownership_fixture_ext1_registration_mismatch')
        aircraft = AircraftBinding(isolation['aircraft_uid'], f'ownership-{output.name}', 1)
        await client.bind(aircraft)
        connection = ObservationConnection(aircraft)
        await stable_aircraft(client, connection, timeout=args.stable_timeout, altitude=args.test_altitude,
                              hold_mode=contract['hold'], log=log)
        identity = GuidanceSessionIdentity(output.name, aircraft, 1)
        active = create_session(client, connection, capabilities, identity, config, selected.profile, log, run_started=started)
        await activate_session(active, log)
        await drive(active, args.duration, log)
        await confirmed_source(args, isolation, active, contract, log)
        checks = {'confirmed_acquisition': True, 'successful_publications': active.commander.successful_publishes > 0}
        if args.case == 'normal_stop':
            await quiesce(active)
            outcome = await active.binding.stop('ownership_fixture_normal_stop')
            checks['correlated_hold'] = outcome['executed'] and outcome['release_receipt']['acquisition'] == asdict(active.acquisition)
            log('handoff.jsonl', {'result': outcome})
        elif args.case == 'confirmed_owner_eof':
            await quiesce(active)
            after_eof = log('fault-events.jsonl', {'event': 'confirmed_owner_socket_abort', 'acquisition': asdict(active.acquisition)})
            active.binding.abort('ownership_fixture_confirmed_eof')
            receipt = await reconcile(active, log)
            checks['eof_original_receipt'] = receipt.outcome == 'hold_confirmed' and receipt.acquisition == active.acquisition
            checks['confirmed_socket_eof_before_intent_expiry'] = eof_precedes_intent_expiry(
                wire, after=after_eof, run_started=started)
            checks['eof_reconciliation_read_only'] = all(request['operation'] in ('hello', 'bind', 'observe')
                                                       for request in wire_requests(wire, after=after_eof))
        else:
            _, after_retirement = await retired_owner(args, isolation, active, contract, log)
            checks['same_epoch_retirement_observed'] = True
            receipt = await reconcile(active, log)
            checks['original_owner_retired'] = receipt.outcome == 'owner_already_released'
            if args.case == 'same_mode_reselection':
                outcome = await active.binding.stop('ownership_fixture_takeover_cleanup')
                checks['no_backend_hold_claim'] = not outcome['executed'] and outcome['reason'] == 'native_owner_already_released'
                checks['retired_cleanup_read_only'] = all(request['operation'] in ('hello', 'bind', 'observe')
                                                         for request in wire_requests(wire, after=after_retirement))
                log('handoff.jsonl', {'result': outcome})
            else:
                original = active
                await user_mode(args, isolation, log, 'auto:loiter', purpose='new_acquisition_stable_point')
                capabilities = await client.connect()
                await client.bind(aircraft)
                await stable_aircraft(client, connection, timeout=args.stable_timeout, altitude=args.test_altitude,
                                      hold_mode=contract['hold'], log=log)
                active = create_session(client, connection, capabilities, identity, config, selected.profile, log, run_started=started)
                await activate_session(active, log)
                await drive(active, args.duration, log)
                await confirmed_source(args, isolation, active, contract, log)
                rejected = False
                late_begin = log('cleanup-boundaries.jsonl', {'event': 'late_original_cleanup_begin'})
                try:
                    await original.binding.stop('late_original_cleanup')
                except NativeGuidanceError as error:
                    rejected = str(error) == 'native_session_replaced'
                original.binding.abort('late_original_abort')
                late_end = log('cleanup-boundaries.jsonl', {'event': 'late_original_cleanup_end', 'rejected': rejected})
                await drive(active, .3, log)
                await confirmed_source(args, isolation, active, contract, log)
                checks.update(late_cleanup_rejected=rejected, replacement_preserved=client.acquisition_context == active.acquisition,
                    distinct_acquisition=original.acquisition != active.acquisition and original.acquisition.token != active.acquisition.token,
                    same_semantic_identity=original.acquisition.identity == active.acquisition.identity,
                    newer_activation=active.acquisition.activation_timestamp > original.acquisition.activation_timestamp,
                    no_original_context_write=not any(request.get('payload', {}).get('token') == original.acquisition.token
                        for request in wire_requests(wire, after=late_begin, before=late_end)))
        result = {'passed': all(checks.values()), 'reason': 'ownership_case_complete', 'case': args.case,
            'response_checks': checks, 'lost_engagement_ack_tested': False}
        (output / 'pre-cleanup-result.json').write_text(json.dumps(result, indent=2) + '\n')
        if args.case == 'same_mode_reselection':
            await user_mode(args, isolation, log, 'auto:loiter', purpose='independent_cleanup_after_verdict')
        if active is not None:
            await quiesce(active)
            result['cleanup'] = await active.binding.stop('ownership_fixture_final_cleanup')
        await client.connect()
        await client.bind(aircraft)
        _, counts = await wait_for_coherent_hold(client, active.acquisition, contract['hold'], log)
        final_hold = True
        for _ in range(5):
            packet = await client.observe()
            counts.append(packet['publications'])
            final_hold &= coherent_hold(packet, active.acquisition, contract['hold'])
            log('post-stop-observations.jsonl', packet)
            await asyncio.sleep(.1)
        result['response_checks']['no_publication_after_cleanup'] = (
            all(type(value) is int and value >= 0 for value in counts) and len(set(counts)) == 1)
        result['response_checks']['observed_final_hold'] = final_hold
        result['passed'] &= all(result['response_checks'].values())
        await client.close()
    except Exception as error:  # noqa: BLE001 - qualification errors must retain failed evidence and original-owner cleanup.
        result.update(passed=False, reason=f'{type(error).__name__}:{error}')
    finally:
        if not (output / 'pre-cleanup-result.json').exists():
            (output / 'pre-cleanup-result.json').write_text(json.dumps(result, indent=2) + '\n')
        if active is not None:
            try:
                await quiesce(active)
                result['final_release'] = await active.binding.stop('ownership_fixture_finally')
            except Exception as error:  # noqa: BLE001 - failed cleanup remains explicit in the qualification result.
                result.update(passed=False, cleanup_error=str(error))
        if client is not None:
            await client.close()
        if recorder is not None:
            await recorder.__aexit__()
        if socket_directory is not None:
            socket_directory.cleanup()
        try:
            (output / 'px4/parameters-after.txt').write_text(await asyncio.to_thread(native_parameters, args.socket, isolation))
        except Exception as error:  # noqa: BLE001 - failed evidence collection cannot leave a successful verdict.
            result.update(passed=False, parameter_snapshot_error=str(error))
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        for handle in handles.values():
            handle.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--container', required=True)
    parser.add_argument('--instance', type=int, required=True)
    parser.add_argument('--socket', type=Path, required=True)
    parser.add_argument('--sih-build-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--follower', default='gm_velocity_vector')
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/config_default.yaml')
    parser.add_argument('--duration', type=float, default=3.)
    parser.add_argument('--test-altitude', type=float, default=30.)
    parser.add_argument('--stable-timeout', type=float, default=90.)
    args = parser.parse_args(argv)
    if not (1. <= args.duration <= 10. and 15. <= args.test_altitude <= 120. and 1. <= args.stable_timeout <= 180.):
        parser.error('Invalid bounded ownership fixture timing/altitude')
    component_profile(args.follower)
    isolation = verify_simulator(args.container, args.instance, args.socket, sih_build_manifest=args.sih_build_manifest)
    contract = source_contract(args.sih_build_manifest)
    if not args.execute:
        print(json.dumps({'execute': False, 'case': args.case, 'isolation': isolation, 'source_contract': contract}, indent=2))
        return 0
    result = asyncio.run(run(args, isolation, contract))
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
