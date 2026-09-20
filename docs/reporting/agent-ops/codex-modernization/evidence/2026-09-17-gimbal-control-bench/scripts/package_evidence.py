"""Package completed local bench sessions; never includes captured room images."""
import ast
import collections
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path('/home/alireza/PixEagle')
SOURCE = ROOT / 'reports/gimbal-bench'
DEST = ROOT / 'docs/reporting/agent-ops/codex-modernization/evidence/2026-09-17-gimbal-control-bench'
DEST.mkdir(parents=True, exist_ok=True)
(DEST / 'scripts').mkdir(exist_ok=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


sessions = []
overall = collections.Counter()
examples = {}
for path in sorted(SOURCE.glob('*/events.jsonl')):
    rows = list(map(json.loads, path.read_text().splitlines()))
    if not rows or rows[-1]['kind'] != 'end':
        raise ValueError(f'Unfinished evidence: {path}')
    script = path.parent / 'bench_probe.py'
    digest = sha(script)
    assert digest == rows[0]['script_sha256'], path
    ast.parse(script.read_text())
    dest = DEST / path.parent.name
    dest.mkdir(exist_ok=True)
    shutil.copyfile(path, dest / 'events.jsonl')
    for analysis_name in ('correlated.json', 'runtime-wire.jsonl', 'switch-motion-analysis.json'):
        analysis = path.parent / analysis_name
        if analysis.exists():
            shutil.copyfile(analysis, dest / analysis_name)
    shutil.copyfile(script, DEST / 'scripts' / f'{digest}.py')
    counts = collections.Counter()
    states = []
    actions = []
    for row in rows:
        if row['kind'] in ('tx', 'cleanup_tx', 'rx'):
            data = bytes.fromhex(row['hex'])
            valid = len(data) >= 2 and data[-2:] == f'{sum(data[:-2]) & 255:02X}'.encode()
            counts[row['kind']] += 1
            if not valid:
                counts[row['kind'] + '_invalid_checksum'] += 1
            if row['kind'] == 'rx':
                assert row['checksum_valid'] == valid
                family = data[7:10].decode('ascii')
                overall[family] += 1
                examples.setdefault(family, {'session': path.parent.name, 'hex': data.hex()})
                if family == 'TRC':
                    state = data[10:12].decode()
                    if not states or states[-1]['state'] != state:
                        states.append({'elapsed': row['elapsed'], 'state': state})
            elif row['kind'] == 'tx' and row.get('label') not in ('query_tracking', 'query_body_angles'):
                actions.append({'elapsed': row['elapsed'], 'label': row.get('label', 'query'), 'hex': row['hex']})
        if row['kind'] == 'decoded_frame':
            assert sha(path.parent / row['file']) == row['sha256'], row['file']
    sessions.append({
        'session': path.parent.name, 'phase': rows[0]['phase'], 'utc_start': rows[0]['utc'],
        'arguments': rows[0].get('arguments'), 'events_sha256': sha(path),
        'script_sha256': digest, 'counts': dict(counts), 'tracking_transitions': states,
        'actions': actions, 'errors': [r for r in rows if r['kind'].endswith('error')],
        'image_files_local_only': [r['file'] for r in rows if r['kind'] == 'decoded_frame'],
    })

shutil.copyfile(SOURCE / 'offline-parser-review.json', DEST / 'offline-parser-review.json')
replay_source = Path('/tmp/pixeagle_gimbal_offline_replay.py')
if replay_source.exists():
    shutil.copyfile(replay_source, DEST / 'scripts/offline_parser_replay.py')
if Path(__file__).resolve() != (DEST / 'scripts/package_evidence.py').resolve():
    shutil.copyfile(__file__, DEST / 'scripts/package_evidence.py')
manifest = {
    'runtime_commit': '463fbbc5acbc107d32cffc6c85cc3670923016ee',
    'evidence_type': 'standalone_camera_bench_not_flight_acceptance',
    'device_model': 'unknown', 'firmware': 'unknown',
    'mount_history': ['initial handheld', 'operator-reported inverted restart',
                      'operator restart after requested upright return; exact orientation not measured'],
    'sessions': sessions, 'received_families_including_duplicate_deliveries': dict(overall),
    'first_example_per_received_family': examples,
    'artifacts': {str(p.relative_to(DEST)): sha(p) for p in sorted(DEST.rglob('*'))
                  if p.is_file() and p.name != 'manifest.json'},
}
(DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'sessions': len(sessions), 'received_families': overall,
                  'invalid_checksums': sum(v for s in sessions for k,v in s['counts'].items() if 'invalid_checksum' in k),
                  'images_verified_local_only': sum(len(s['image_files_local_only']) for s in sessions)}, indent=2))
