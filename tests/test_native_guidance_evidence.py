"""Portable canonical-artifact parser tests; synthetic bytes are never flight evidence."""
from dataclasses import asdict
import hashlib
import json
from unittest.mock import Mock

import pytest

from tests.test_native_guidance_cycle import context
from tools import native_guidance_evidence as evidence
from tools import run_native_transition_baseline as base
from tools import sih_baseline as builder


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
    assets = dict(adapter_image='sha256:'+'2'*64, adapter_sha256='3'*64)
    assets_path = repository / 'native/baseline-runtime.json';write(assets_path, assets)
    sdk = dict(repository='synthetic-pinned-sdk', commit='4'*40)
    write(repository / 'native/dependencies.lock.json', {'sources': [sdk]})
    source = tmp_path / 'build/context/source'
    producer = source / 'src/producer.cpp';producer.parent.mkdir(parents=True)
    producer.write_text('SYNTHETIC reviewed producer gate')
    message = source / 'msg/versioned/VehicleStatus.msg';message.parent.mkdir(parents=True)
    message.write_text('uint8 NAVIGATION_STATE_EXTERNAL1 = 23\nuint8 NAVIGATION_STATE_EXTERNAL8 = 30\n')
    script = run / 'simulator/adapter.sh';script.parent.mkdir(parents=True)
    script.write_text('SYNTHETIC sole compiled adapter')
    contract = dict(schema_version=1, runtime_assets_sha256=digest(assets_path), runtime_helper_sha256=digest(helper),
        sdk_source=sdk, scripts={'adapter.sh': digest(script)}, firmware_files={'src/producer.cpp': digest(producer)})
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
    write(run / 'capabilities.json', dict(capabilities=dict(runtime_id=context().runtime_id,
        owned_mode_id=23, owned_mode_supported=True), binding=asdict(context().identity.binding)))
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
        producer=producer, script=script, verify=verify, authority=authority, write=write)


@pytest.mark.parametrize('bad', [None, 'source', 'script', 'assets', 'sdk', 'capabilities', 'uid', 'image', 'restart', 'missing'])
def test_canonical_artifacts_reuse_validators_and_refuse_changed_producer_or_identity(artifacts, bad):
    a = artifacts
    if bad == 'source': a['producer'].write_text('UNREVIEWED producer')
    elif bad == 'script': a['script'].write_text('ANOTHER DDS publisher')
    elif bad == 'assets': (a['repository']/'native/baseline-runtime.json').write_text('{}')
    elif bad == 'sdk': a['write'](a['repository']/'native/dependencies.lock.json', {'sources': []})
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
        a['verify'].assert_called_once_with(a['bundle'], a['file_manifest'],
            {'adapter_image': 'sha256:'+'2'*64, 'adapter_sha256': '3'*64})
        a['authority'].assert_called_once_with(a['repository'], simulator='sih', resource_variant='stock')
