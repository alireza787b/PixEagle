"""Replay captured packets and the query scheduler without opening any socket."""
import ast
import collections
import hashlib
import json
from pathlib import Path
import sys
import struct
from unittest.mock import patch

ROOT = Path('/home/alireza/PixEagle')
sys.path.insert(0, str(ROOT / 'src'))
from classes.gimbal_interface import GimbalInterface

source = ROOT / 'src/classes/gimbal_interface.py'
node = ast.parse(source.read_text())
intervals = next(ast.literal_eval(n.value) for n in ast.walk(node)
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute)
                 and t.attr == 'QUERY_INTERVALS' for t in n.targets))
client = object.__new__(GimbalInterface)
counts = collections.defaultdict(collections.Counter)
inputs = []
with patch('socket.socket', side_effect=AssertionError('Offline replay must not create sockets')):
    for session in ('20260917T044930Z-queries', '20260917T050911Z-queries'):
        p = ROOT / 'reports/gimbal-bench' / session / 'events.jsonl'
        inputs.append({'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
        for row in map(json.loads, p.read_text().splitlines()):
            if row['kind'] != 'rx':
                continue
            packet = bytes.fromhex(row['hex']).decode('ascii')
            family = packet[7:10]
            counts[family]['received'] += 1
            parsed = client._parse_gimbal_packet(packet)
            counts[family]['accepted' if parsed else 'rejected'] += 1
    corrupt = []
    for packet in ('#TPDP2rTRC0248', '#tpGPCrGACFFCC063202F300'):
        valid = packet[-2:] == f'{sum(packet[:-2].encode()) & 255:02X}'
        result = client._parse_gimbal_packet(packet)
        corrupt.append({'packet': packet, 'checksum_valid': valid, 'accepted': result is not None,
                        'tracking_state': result.tracking_status.state.name if result and result.tracking_status else None})
    client.QUERY_INTERVALS = intervals
    client.running = True
    queries = []
    client.query_tracking_status = lambda: queries.append('TRC')
    client.query_spatial_fixed_angles = lambda: queries.append('GIC')
    client.query_gimbal_body_angles = lambda: queries.append('GAC')

    def sleep(_):
        if len(queries) >= 30:
            client.running = False

    with patch('classes.gimbal_interface.time.sleep', sleep):
        client._query_loop()

result = {
    'offline_only': True,
    'runtime_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'inputs': inputs,
    'packet_results': dict(counts),
    'checksum_probes_never_transmitted': corrupt,
    'scheduler_intervals': intervals,
    'scheduler_30_iterations': dict(collections.Counter(queries)),
    'warning': 'Do not alias GIA to GIC for following: reference frame remains unverified; body and spatial samples currently share one slot.',
}
oft_counts = collections.Counter()
oft_examples = []
seen = set()
for p in sorted((ROOT / 'reports/gimbal-bench').glob('*-point/events.jsonl')):
    for row in map(json.loads, p.read_text().splitlines()):
        if row['kind'] != 'rx' or row['ascii'][7:10] != 'OFT':
            continue
        data = bytes.fromhex(row['hex'])
        parsed = client._parse_gimbal_packet(data.decode('utf-8', errors='replace'))
        accepted = bool(parsed and parsed.angles)
        oft_counts['received_including_duplicate_deliveries'] += 1
        oft_counts['accepted_as_angles' if accepted else 'rejected'] += 1
        if accepted and row['hex'] not in seen and len(oft_examples) < 5:
            seen.add(row['hex'])
            oft_examples.append({'session': p.parent.name, 'hex': row['hex'],
                                 'runtime_angles': parsed.angles.to_tuple(),
                                 'pixel_geometry_hypothesis_only': struct.unpack('<HHHHB', data[10:19])})
result['oft_replay_exact_runtime_utf8_decode'] = {
    'counts': dict(oft_counts), 'accepted_examples': oft_examples,
    'interpretation': 'OFT contents resemble image coordinates/sizes; exact meaning requires vendor specification. They are not established angle measurements.',
}
target = ROOT / 'reports/gimbal-bench/offline-parser-review.json'
target.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
