"""The normal camera stack must not enter the recorded-video replay workflow."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('replay', [False, True])
def test_entry_uses_the_existing_supervisor_with_explicit_replay_opt_in(tmp_path, replay):
    runtime = tmp_path / 'runtime'
    (runtime / 'configs').mkdir(parents=True)
    (runtime / 'configs/config.yaml').write_text('{}\n')
    (runtime / 'profile-manifest.json').write_text(json.dumps(dict(
        version=2, kind='simulation-preflight', instance_id='isolated-unit-test',
        flight_commands_blocked=True, allow_recorded_sih_following=replay)))
    supervisor = runtime / 'src/classes/backend_supervisor.py'
    supervisor.parent.mkdir(parents=True)
    supervisor.write_text("""import json, os, pathlib, sys
pathlib.Path(os.environ['PIXEAGLE_PROJECT_ROOT'], 'supervisor-call.json').write_text(json.dumps({
    'argv': sys.argv[1:], 'injections': os.environ.get('PIXEAGLE_ENABLE_SITL_INJECTIONS'),
    'replay_binding': os.environ.get('PIXEAGLE_SIH_REPLAY_BINDING')}))
""")
    executable = tmp_path / 'owned-inert-sidecar'
    executable.write_text(f'#!{sys.executable}\nimport signal\nsignal.pause()\n')
    executable.chmod(0o700)
    binary_dir = tmp_path / 'bin'
    binary_dir.mkdir()
    for name in ['mavlink2rest', 'mavsdk_server_bin']:
        target = binary_dir / name
        target.write_bytes(executable.read_bytes())
        target.chmod(0o700)
    environment = os.environ | dict(
        PIXEAGLE_SIM_RUNTIME=str(runtime), PIXEAGLE_SIM_PYTHON=sys.executable,
        PIXEAGLE_SIM_BIN_DIR=str(binary_dir), PIXEAGLE_SIM_ROUTER=str(executable),
        PIXEAGLE_ENABLE_SITL_INJECTIONS='1', PIXEAGLE_SIH_REPLAY_BINDING='obsolete-binding')
    script = Path(__file__).resolve().parents[3] / 'tools/simulation_stack_entry.sh'
    result = subprocess.run(['bash', str(script)], env=environment, capture_output=True, text=True, timeout=8)
    assert result.returncode == 0, result.stderr
    call = json.loads((runtime / 'supervisor-call.json').read_text())
    assert ('--sih' in call['argv']) == replay
    assert call['injections'] is None
    assert call['replay_binding'] is None
