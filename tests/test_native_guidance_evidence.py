"""Portable canonical-artifact parser tests; synthetic bytes are never flight evidence."""
from dataclasses import asdict
import hashlib
import json
from unittest.mock import Mock

import pytest

from tests.test_native_guidance_cycle import context, held_mc_log
from tools import native_guidance_evidence as evidence
from tools import run_native_transition_baseline as base
from tools import sih_baseline as builder


def anchor_wire(run):
    owner = context()
    capabilities = dict(runtime_id=owner.runtime_id, px4_firmware='synthetic', external_mode_api_version=2,
        fixed_wing_supported=True, multicopter_supported=True, unrestricted_speed_supported=False,
        owned_mode_supported=True, owned_mode_id=23, multicopter_altitude_hold_supported=True)
    reference = dict(altitude_amsl_m=530., reference_generation=7)
    rows = []
    def exchange(index, operation, request, response):
        header = dict(protocol_version=4, generation=1, request_id=index)
        rows.extend([dict(timestamp=float(index), connection=1, direction='request_forward_attempt',
            value=header | dict(operation=operation, payload=request)),
            dict(timestamp=index + .1, connection=1, direction='actual_backend_reply',
                value=header | dict(success=True, payload=response))])
    exchange(1, 'hello', {}, capabilities)
    exchange(2, 'observe', {}, dict(fresh=True, rescue_active=False,
        phase_source_health={'vehicle_status_timeout_s': 1.},
        aircraft_state=dict(binding=asdict(owner.identity.binding), altitude_amsl_m=530., altitude_reference_generation=7,
            velocity_ned_m_s=dict(x=2.5, y=0., z=0.)),
        vehicle_pose=dict(px4_timestamp_us=150000, vehicle_ned=[.125, 0., -30.], source='px4_dds_observed')))
    exchange(3, 'engage', dict(identity=asdict(owner.identity), token=owner.token, runtime_id=owner.runtime_id,
        altitude_reference=reference, expires_at_monotonic_s=4.),
        dict(owner_confirmed=True, runtime_id=owner.runtime_id, acquisition=owner.wire_payload()))
    exchange(4, 'intent', dict(identity=asdict(owner.identity), token=owner.token, sequence=1, phase='multicopter',
        command=dict(velocity_north_m_s=1., velocity_east_m_s=2., yaw_rate_rad_s=.1,
            altitude_amsl_m=530., altitude_reference_generation=7)), dict(accepted_sequence=1, owner_confirmed=True))
    path = run / 'mc-follow/wire.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    return path, rows, capabilities


@pytest.mark.parametrize('bad', [None, 'protocol', 'token', 'identity', 'activation', 'runtime',
    'missing_reference', 'nan_altitude', 'bool_generation', 'reply_key', 'duplicate_reply', 'duplicate_engage',
    'missing_observation', 'wrong_observed_generation', 'wrong_observed_altitude', 'zero_dds_timestamp',
    'missing_hello', 'changed_hold_altitude', 'changed_hold_generation', 'mixed_vertical', 'timeout', 'bool_timeout',
    'bool_ack', 'bool_sequence', 'nonobject_command', 'nan_velocity'])
def test_hold_anchor_requires_actual_correlated_protocol_four_wire(tmp_path, bad):
    path, rows, capabilities = anchor_wire(tmp_path)
    engage, ack = rows[4]['value'], rows[5]['value']
    if bad == 'protocol': engage['protocol_version'] = 3
    elif bad in ('token', 'identity', 'runtime'): engage['payload'][bad] = 'wrong'
    elif bad == 'activation': ack['payload']['acquisition']['activation_timestamp'] += 1
    elif bad == 'missing_reference': engage['payload'].pop('altitude_reference')
    elif bad == 'nan_altitude': engage['payload']['altitude_reference']['altitude_amsl_m'] = float('nan')
    elif bad == 'bool_generation': engage['payload']['altitude_reference']['reference_generation'] = True
    elif bad == 'reply_key': ack['request_id'] += 1
    elif bad == 'duplicate_reply': rows.append(rows[5])
    elif bad == 'duplicate_engage': rows.append(rows[4])
    elif bad == 'missing_observation': rows[3]['value']['success'] = False
    elif bad == 'wrong_observed_generation': rows[3]['value']['payload']['aircraft_state']['altitude_reference_generation'] = 8
    elif bad == 'wrong_observed_altitude': rows[3]['value']['payload']['aircraft_state']['altitude_amsl_m'] = 531.
    elif bad == 'zero_dds_timestamp': rows[3]['value']['payload']['vehicle_pose']['px4_timestamp_us'] = 0
    elif bad == 'missing_hello': rows[1]['value']['success'] = False
    elif bad == 'changed_hold_altitude': rows[6]['value']['payload']['command']['altitude_amsl_m'] = 531.
    elif bad == 'changed_hold_generation': rows[6]['value']['payload']['command']['altitude_reference_generation'] = 8
    elif bad == 'mixed_vertical': rows[6]['value']['payload']['command']['velocity_down_m_s'] = 0.
    elif bad == 'timeout': rows[3]['value']['payload']['phase_source_health']['vehicle_status_timeout_s'] = .5
    elif bad == 'bool_timeout': rows[3]['value']['payload']['phase_source_health']['vehicle_status_timeout_s'] = True
    elif bad == 'bool_ack': rows[7]['value']['payload']['accepted_sequence'] = True
    elif bad == 'bool_sequence': rows[6]['value']['payload']['sequence'] = True
    elif bad == 'nonobject_command': rows[6]['value']['payload']['command'] = []
    elif bad == 'nan_velocity': rows[6]['value']['payload']['command']['velocity_north_m_s'] = float('nan')
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    if bad is not None:
        with pytest.raises((ValueError, KeyError, TypeError)):
            evidence._engagement_reference(tmp_path, context(), capabilities, reference_timeout_s=1.)
    else:
        proof = evidence._engagement_reference(tmp_path, context(), capabilities, reference_timeout_s=1.)
        assert proof['altitude_amsl_m'] == 530. and proof['reference_generation'] == 7
        assert proof['dds_position_timestamp_us'] == 150000 and proof['aircraft_uid'] == '42'
        assert proof['wire_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_refused_rpc_is_retained_but_cannot_change_the_admitted_hold_anchor(tmp_path):
    path, rows, capabilities = anchor_wire(tmp_path)
    rows[6]['value']['payload']['command']['altitude_amsl_m'] = 531.
    rows[7]['value'].update(success=False, error_code='native_pursuit_ended', payload=None)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    proof = evidence._engagement_reference(tmp_path, context(), capabilities, reference_timeout_s=1.)
    assert proof['altitude_amsl_m'] == 530.
    assert json.loads(path.read_text().splitlines()[-1])['value']['success'] is False


def test_real_dds_epoch_scale_is_not_compared_to_native_activation_clock(tmp_path):
    path, rows, capabilities = anchor_wire(tmp_path)
    # Actual retained H-reacquire pose scale; this envelope remains a synthetic protocol4 test.
    rows[3]['value']['payload']['vehicle_pose']['px4_timestamp_us'] = 1794570356442135
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    proof = evidence._engagement_reference(tmp_path, context(), capabilities, reference_timeout_s=1.)
    assert proof['dds_position_timestamp_us'] == 1794570356442135
    assert proof['position_fingerprint'] == dict(x=.125, y=0., z=-30., vx=2.5, vy=0., vz=0., altitude_amsl_m=530.)
    assert 'position_timestamp_us' not in proof
    log, data, source = held_mc_log()
    source['mc_altitude_reference'] = proof
    assert evidence._native_reference_anchor(data['vehicle_local_position'], 200000, 1000000, proof) == 1
    assert evidence._held_reference_matches(log, 200000, 400000, data['trajectory_setpoint']['timestamp'],
        data['trajectory_setpoint']['position[2]'], source)


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    repository, run, bundle = (tmp_path / name for name in ('repository', 'run', 'bundle'))
    helper = repository / 'tools/run_native_transition_baseline.py'
    helper.parent.mkdir(parents=True);helper.write_text('SYNTHETIC locked Runtime source')
    recorder = repository / 'tools/native_sih_wire.py'
    recorder.write_text('SYNTHETIC reviewed transparent recorder')
    assets = dict(adapter_image='sha256:'+'2'*64, adapter_sha256='3'*64)
    assets_path = repository / 'native/baseline-runtime.json';write(assets_path, assets)
    sdk_header = bundle / 'sdk/trajectory.hpp';sdk_header.parent.mkdir(parents=True)
    sdk_header.write_text('SYNTHETIC reviewed SDK mixed trajectory form')
    sdk = dict(repository='synthetic-pinned-sdk', commit='4'*40)
    write(repository / 'native/dependencies.lock.json', {'sources': [sdk]})
    source = tmp_path / 'build/context/source'
    producer = source / 'src/producer.cpp';producer.parent.mkdir(parents=True)
    producer.write_text('SYNTHETIC reviewed producer gate')
    message = source / 'msg/versioned/VehicleStatus.msg';message.parent.mkdir(parents=True)
    message.write_text('uint8 NAVIGATION_STATE_EXTERNAL1 = 23\nuint8 NAVIGATION_STATE_EXTERNAL8 = 30\n'
                       'uint8 NAVIGATION_STATE_AUTO_LOITER = 4\nuint8 VEHICLE_TYPE_FIXED_WING = 2\n')
    script = run / 'simulator/adapter.sh';script.parent.mkdir(parents=True)
    script.write_text('SYNTHETIC sole compiled adapter')
    contract = dict(schema_version=2, protocol_version=4, source_review_sha256='a'*64, altitude_reference_timeout_s=1.,
        wire_recorder_sha256=digest(recorder),
        runtime_assets_sha256=digest(assets_path), runtime_helper_sha256=digest(helper),
        sdk_bundle_files={'sdk/trajectory.hpp': digest(sdk_header)},
        sdk_source=sdk, scripts={'adapter.sh': digest(script)}, firmware_files={
            'src/producer.cpp': digest(producer), 'msg/versioned/VehicleStatus.msg': digest(message)})
    contract_path = repository / 'native/guidance-evidence-source.json';write(contract_path, contract)
    firmware, spec, packaged = dict(commit='5'*40), dict(target='synthetic'), dict(binary_sha256='6'*64)
    manifest = dict(kind='pixeagle_sih_build', firmware=firmware, build=spec,
        artifacts=packaged, recipe_sha256='synthetic-recipe', image_id='sha256:'+'1'*64)
    manifest_path = tmp_path / 'build/manifest.json';write(manifest_path, manifest)
    build = dict(manifest=str(manifest_path), manifest_sha256=digest(manifest_path), firmware=firmware,
        image_id=manifest['image_id'], binary_sha256=packaged['binary_sha256'])
    host = dict(primary='a'*64, sidecar='b'*64, owner_token='c'*32, simulation_build=build,
        adapter_image=assets['adapter_image'], runtime_assets_sha256=digest(assets_path),
        tool_sha256=digest(helper), fixture={'model': 'sihsim_xvert'})
    write(run / 'host-manifest.json', host)
    _, _, capabilities = anchor_wire(run)
    archive = run / 'mc-follow/native_sih_wire.py';archive.write_bytes(recorder.read_bytes())
    write(run / 'mc-follow/manifest.json', dict(tool_helpers=dict(wire_recorder=dict(
        path='native_sih_wire.py', sha256=digest(recorder)))))
    write(run / 'capabilities.json', dict(capabilities=capabilities, binding=asdict(context().identity.binding)))
    write(run / 'adapter-bootstrap.json', dict(original_sidecar=host['sidecar'], launch_attempts=1,
        returncode=0, discovery_timeout_changed=False))
    witness = dict(checked=dict(container_id=host['primary'], image_id=build['image_id'], firmware_build=build,
        instance=0, aircraft_uid='42', process=dict(binary_sha256=build['binary_sha256'], model='sihsim_xvert')),
        sidecar_id=host['sidecar'], sidecar_image=assets['adapter_image'], sidecar_running=True)
    (run / 'isolation-verifications.jsonl').write_text((json.dumps(witness)+'\n')*2)
    monkeypatch.setattr(evidence, 'ROOT', repository)
    monkeypatch.setattr(evidence, 'SOURCE_CONTRACT', contract_path)
    monkeypatch.setattr(base, 'ASSETS', assets_path)
    verify = Mock();monkeypatch.setattr(base, 'verify_adapter', verify)
    authority = Mock(return_value=(firmware, spec));monkeypatch.setattr(builder, 'authority', authority)
    monkeypatch.setattr(builder, 'artifact_manifest', Mock(return_value=packaged))
    monkeypatch.setattr(builder, 'recipe_fingerprint', Mock(return_value='synthetic-recipe'))
    return dict(run=run, bundle=bundle, file_manifest=tmp_path/'bundle.json', repository=repository,
        producer=producer, message=message, script=script, sdk_header=sdk_header, recorder_archive=archive,
        verify=verify, authority=authority, write=write)


@pytest.mark.parametrize('bad', [None, 'source', 'message', 'script', 'assets', 'sdk', 'sdk_header',
    'capabilities', 'uid', 'image', 'restart', 'missing', 'old_schema', 'old_protocol', 'no_review', 'recorder'])
def test_canonical_artifacts_reuse_validators_and_refuse_changed_producer_or_identity(artifacts, bad):
    a = artifacts
    if bad == 'source': a['producer'].write_text('UNREVIEWED producer')
    elif bad == 'message': a['message'].write_text('UNREVIEWED field definitions')
    elif bad == 'script': a['script'].write_text('ANOTHER DDS publisher')
    elif bad == 'assets': (a['repository']/'native/baseline-runtime.json').write_text('{}')
    elif bad == 'sdk': a['write'](a['repository']/'native/dependencies.lock.json', {'sources': []})
    elif bad == 'sdk_header': a['sdk_header'].write_text('UNREVIEWED SDK payload form')
    elif bad == 'recorder': a['recorder_archive'].write_text('UNREVIEWED rewriting recorder')
    elif bad in ('old_schema', 'old_protocol', 'no_review'):
        path = a['repository']/'native/guidance-evidence-source.json'
        contract = json.loads(path.read_text())
        if bad == 'old_schema': contract['schema_version'] = 1
        elif bad == 'old_protocol': contract['protocol_version'] = 3
        else: contract.pop('source_review_sha256')
        a['write'](path, contract)
    elif bad == 'capabilities': a['write'](a['run']/'capabilities.json', {'runtime_id': 'wrong flat layout'})
    elif bad in ('uid', 'image'):
        path = a['run']/'isolation-verifications.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]['checked']['aircraft_uid' if bad == 'uid' else 'image_id'] = 'different'
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    elif bad == 'restart':
        path = a['run']/'adapter-bootstrap.json';value = json.loads(path.read_text());value['launch_attempts'] = 2
        a['write'](path, value)
    elif bad == 'missing': (a['run']/'isolation-verifications.jsonl').unlink()
    def validate():
        return evidence._source_provenance(a['run'], context(), adapter_bundle=a['bundle'],
            adapter_file_manifest=a['file_manifest'], build_repository=a['repository'])
    if bad is not None:
        with pytest.raises((ValueError, KeyError, OSError, StopIteration)):
            validate()
    else:
        proof = validate()
        assert proof['artifact_root'] == str(a['run']) and proof['compiled_adapter_sha256'] == '3'*64
        assert proof['native_hold_nav_state'] == 4 and proof['native_fixed_wing_type'] == 2
        a['verify'].assert_called_once_with(a['bundle'], a['file_manifest'],
            {'adapter_image': 'sha256:'+'2'*64, 'adapter_sha256': '3'*64})
        a['authority'].assert_called_once_with(a['repository'], simulator='sih', resource_variant='stock')
