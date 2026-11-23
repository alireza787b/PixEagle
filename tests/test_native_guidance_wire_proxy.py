"""Local byte-relay tests only; no simulator, vehicle or Docker actions."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import run_native_guidance_wire as proxy
from tools import run_gazebo_training as training


async def test_recorder_preserves_bytes_and_reconnects_without_replaying(tmp_path):
    front, logs = tmp_path / 'front', tmp_path / 'logs'
    front.mkdir(mode=0o700); logs.mkdir(mode=0o700)
    received, connections = [], []
    async def backend(reader, writer):
        connections.append(True)
        while line := await reader.readline():
            received.append(line)
            writer.write(b'{ "success": true, "payload": {} }\n')
            await writer.drain()
        writer.close()
        await writer.wait_closed()
    server = await asyncio.start_unix_server(backend, str(tmp_path / 'backend.sock'))
    stopped = asyncio.Event()
    task = asyncio.create_task(proxy.serve(front / 'guidance.sock', tmp_path / 'backend.sock', logs, stopped))
    try:
        async with asyncio.timeout(1):
            while not (front / 'guidance.sock').exists():
                await asyncio.sleep(.001)
        assert connections == []  # Listening is not an observer or control-client connection.
        for index in (1, 2):
            reader, writer = await asyncio.open_unix_connection(str(front / 'guidance.sock'))
            message = b'{ "operation": "observe", "request_id": ' + str(index).encode() + b' }\n'
            writer.write(message); await writer.drain()
            assert await asyncio.wait_for(reader.readline(), 1) == b'{ "success": true, "payload": {} }\n'
            writer.close(); await writer.wait_closed()
        assert received == [b'{ "operation": "observe", "request_id": 1 }\n',
                            b'{ "operation": "observe", "request_id": 2 }\n']
    finally:
        stopped.set(); await task
        server.close(); await server.wait_closed()
    rows = [json.loads(line) for line in (logs / 'wire.jsonl').read_text().splitlines()]
    assert [row['value']['request_id'] for row in rows if row.get('direction') == 'request_forward_attempt'
            and 'value' in row] == [1, 2]
    assert all(row['timestamp'] > 0 for row in rows)
    assert {row['connection'] for row in rows} == {1, 2}
    assert (logs / 'wire.jsonl').stat().st_mode & 0o777 == 0o600
    assert not (front / 'guidance.sock').exists()
    assert (tmp_path / 'backend.sock').exists()


@pytest.mark.parametrize('bad', ['public_front', 'public_logs', 'backend_file', 'backend_symlink', 'existing_log'])
async def test_proxy_refuses_unowned_or_reused_evidence_without_socket(tmp_path, bad):
    front, logs = tmp_path / 'front', tmp_path / 'logs'
    front.mkdir(mode=0o700); logs.mkdir(mode=0o700)
    server = await asyncio.start_unix_server(lambda r, w: w.close(), str(tmp_path / 'backend.sock'))
    backend = tmp_path / 'backend.sock'
    if bad == 'public_front': front.chmod(0o755)
    elif bad == 'public_logs': logs.chmod(0o755)
    elif bad == 'backend_file': backend = tmp_path / 'file'; backend.write_text('not socket')
    elif bad == 'backend_symlink':
        backend = tmp_path / 'link'; backend.symlink_to(tmp_path / 'backend.sock')
    else: (logs / 'wire.jsonl').write_text('retained evidence')
    try:
        with pytest.raises((ValueError, FileExistsError)):
            await proxy.serve(front / 'guidance.sock', backend, logs, asyncio.Event())
        assert not (front / 'guidance.sock').exists()
        if bad == 'existing_log': assert (logs / 'wire.jsonl').read_text() == 'retained evidence'
    finally:
        server.close(); await server.wait_closed()



def proxy_info(argv):
    mounts = []
    for index, word in enumerate(argv):
        if word == '--mount':
            fields = dict(item.split('=', 1) for item in argv[index+1].split(',') if '=' in item)
            mounts.append(dict(Type='bind', Source=fields['src'], Destination=fields['dst'],
                               RW=not argv[index+1].endswith(',readonly')))
    return dict(State={'Running': True}, Image=training.host.WORKER_IMAGE,
        Config={'User': f'{os.getuid()}:{os.getgid()}'}, Mounts=mounts,
        HostConfig={'NetworkMode': 'container:original-primary', 'Privileged': False, 'Devices': [],
                    'ReadonlyRootfs': True}, NetworkSettings={'Ports': {}})

def test_launch_retains_original_cid_and_exact_mounts_for_cleanup(tmp_path, monkeypatch):
    import socket
    runtime, profile, venv = tmp_path / 'run', tmp_path / 'profile', tmp_path / 'venv'
    (runtime / 'simulator/private').mkdir(parents=True)
    (profile / 'src').mkdir(parents=True)
    (venv / 'bin').mkdir(parents=True)
    created, launches, sockets = [], [], []
    def launch(self, argv, name):
        launches.append(argv)
        self.created.append('original-proxy')
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(runtime / 'native-wire/front/guidance.sock'))
        sockets.append(sock)
        return 'original-proxy'
    def inspect(cid, token):
        assert cid == 'original-proxy' and token == 'owned-token'
        return proxy_info(launches[-1])
    monkeypatch.setattr(training.OwnedContainerLaunch, 'launch', launch)
    monkeypatch.setattr(training.host, 'owned_container_info', inspect)
    try:
        mounts = training.start_native_wire_recorder(SimpleNamespace(python=venv / 'bin/python'), runtime, profile,
                                                     'owned-token', 'original-primary', created)
        assert mounts == [(runtime / 'native-wire/front', Path('/run/pixeagle'), False)]
        assert created == ['original-proxy']
        assert '--publish' not in launches[0] and '--device' not in launches[0]
        assert launches[0][launches[0].index('--entrypoint')+1] == str(venv / 'bin/python')
        receipt = json.loads((runtime / 'native-wire/manifest.json').read_text())
        assert receipt['canonical_runtime_qualified'] is receipt['following_qualified'] is False
        assert (runtime / 'native-wire/native_sih_wire.py').read_bytes() == (training.ROOT / 'tools/native_sih_wire.py').read_bytes()
    finally:
        for sock in sockets: sock.close()


@pytest.mark.parametrize('bad', ['image', 'uid', 'stopped', 'namespace', 'mount', 'extra_volume', 'port', 'privileged', 'device', 'rootfs'])
def test_proxy_inspection_refusal_keeps_original_cleanup_id(tmp_path, monkeypatch, bad):
    runtime, profile, venv = tmp_path / 'run', tmp_path / 'profile', tmp_path / 'venv'
    (runtime / 'simulator/private').mkdir(parents=True)
    (profile / 'src').mkdir(parents=True)
    (venv / 'bin').mkdir(parents=True)
    created, original = [], []
    def launch(self, argv, name):
        self.created.append('original-proxy')
        original.append(proxy_info(argv))
        return 'original-proxy'
    def inspect(*args):
        info = original[0]
        if bad == 'image': info['Image'] = 'replacement'
        elif bad == 'uid': info['Config']['User'] = '0'
        elif bad == 'stopped': info['State']['Running'] = False
        elif bad == 'namespace': info['HostConfig']['NetworkMode'] = 'host'
        elif bad == 'mount': info['Mounts'][0]['RW'] = True
        elif bad == 'extra_volume':
            info['Mounts'].append(dict(Type='volume', Destination='/app/extra', Source='volume', RW=True))
        elif bad == 'port': info['NetworkSettings']['Ports'] = {'14550/udp': {}}
        elif bad == 'privileged': info['HostConfig']['Privileged'] = True
        elif bad == 'device': info['HostConfig']['Devices'] = ['/dev/ttyUSB0']
        elif bad == 'rootfs': info['HostConfig']['ReadonlyRootfs'] = False
        return info
    monkeypatch.setattr(training.OwnedContainerLaunch, 'launch', launch)
    monkeypatch.setattr(training.host, 'owned_container_info', inspect)
    with pytest.raises(ValueError, match='recorder identity or isolation'):
        training.start_native_wire_recorder(SimpleNamespace(python=venv / 'bin/python'), runtime, profile,
                                           'owned-token', 'original-primary', created)
    assert created == ['original-proxy']
    assert not (runtime / 'native-wire/manifest.json').exists()
