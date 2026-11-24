#!/usr/bin/env python3
"""Small operator/agent front end to the canonical isolated Gazebo runner."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import sys
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path.home() / '.config/pixeagle/training.json'
RESERVED = ('--execute', '--runtime', '--no-operator-ui')


def argument_list(value):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v or '\0' in v for v in value):
        raise ValueError('Launch arguments must be a list of nonempty strings')
    if any(v.split('=', 1)[0] in RESERVED for v in value):
        raise ValueError('Execute, runtime and UI ownership belong to the launcher')
    return value


def load_config(path):
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) != {'version', 'python', 'runtime_root', 'environment', 'arguments', 'profiles'}:
        raise ValueError('Training configuration must match the documented version-1 format')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Unsupported training configuration version')
    for name in ('python', 'runtime_root'):
        if not isinstance(value[name], str) or not Path(value[name]).is_absolute():
            raise ValueError(f'{name} must be an absolute path')
    env = value['environment']
    if not isinstance(env, dict) or set(env) - {'PATH', 'LD_LIBRARY_PATH', 'PYTHONPATH'}:
        raise ValueError('Only explicit tool/library/module search paths are supported')
    if any(not isinstance(v, str) or '\0' in v for v in env.values()):
        raise ValueError('Environment search paths must be strings')
    argument_list(value['arguments'])
    profiles = value['profiles']
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError('Declare at least one prepared training profile')
    for key, profile in profiles.items():
        if (not isinstance(key, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', key)
                or not isinstance(profile, dict) or not {'label', 'arguments'} <= set(profile)
                or set(profile) - {'label', 'arguments', 'audience', 'unavailable_reason'}
                or not isinstance(profile['label'], str) or not profile['label'].strip()
                or any(ord(c) < 32 for c in profile['label'])):
            raise ValueError('Each profile needs an ID, a single-line label and arguments')
        if profile.get('audience', 'beginner') not in ('beginner', 'advanced'):
            raise ValueError('Profile audience must be beginner or advanced')
        reason = profile.get('unavailable_reason')
        if reason is not None and (not isinstance(reason, str) or not reason.strip() or any(ord(c) < 32 for c in reason)):
            raise ValueError('Unavailable reason must be a nonempty single line')
        argument_list(profile['arguments'])
        flags = [v.split('=', 1)[0] for v in value['arguments'] + profile['arguments'] if v.startswith('--')]
        if len(flags) != len(set(flags)):
            raise ValueError(f'Duplicate launch option in profile {key}; declare each option once')
    return value


def banner(stream):
    stream.write((ROOT / 'scripts/banner.txt').read_text())
    stream.write('\n  Simulator training · isolated PX4 / Gazebo / PixEagle\n\n')


def choose_profile(profiles, *, read=input, stream=sys.stdout):
    banner(stream)
    keys = [key for key, profile in profiles.items() if profile.get('audience', 'beginner') == 'beginner']
    if not keys:
        raise ValueError('No beginner profiles configured; agents can select explicit profile IDs')
    for index, key in enumerate(keys, 1):
        pending = ' (pending)' if profiles[key].get('unavailable_reason') else ''
        stream.write(f'  {index}. {profiles[key]["label"]}{pending}\n')
    stream.write('\n  q. Exit\n')
    while True:
        choice = read('\nChoose: ').strip().lower()
        if choice in ('q', 'quit'):
            return None
        if choice.isascii() and choice.isdecimal() and 1 <= int(choice) <= len(keys):
            key = keys[int(choice)-1]
            if profiles[key].get('unavailable_reason'):
                stream.write(profiles[key]['unavailable_reason'] + '\n')
                continue
            return key
        stream.write('Choose a listed number, or q.\n')


def launch_plan(config, profile, *, headless=False, runtime=None):
    if profile not in config['profiles']:
        raise ValueError(f'Unknown profile: {profile}')
    if config['profiles'][profile].get('unavailable_reason'):
        raise ValueError(config['profiles'][profile]['unavailable_reason'])
    runtime = runtime or Path(config['runtime_root']) / (
        profile + '-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    if not runtime.is_absolute() or runtime.exists():
        raise ValueError('Use a fresh absolute runtime directory; existing evidence is never replaced')
    argv = [config['python'], str(ROOT / 'tools/run_gazebo_training.py'),
            *config['arguments'], *config['profiles'][profile]['arguments'], '--execute', '--runtime', str(runtime)]
    if headless:
        argv.append('--no-operator-ui')
    return argv, {**os.environ, **config['environment']}, runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--profile', help='Prepared profile ID; omit for the operator menu')
    parser.add_argument('--headless', action='store_true', help='No operator windows; renderer is still required')
    parser.add_argument('--list', action='store_true', help='Print prepared profiles without launching')
    parser.add_argument('--dry-run', action='store_true', help='Print argv without launching or creating files')
    parser.add_argument('--runtime', type=Path, help='Fresh evidence directory; normally generated automatically')
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.list:
            for key, profile in config['profiles'].items():
                if not args.headless and profile.get('audience', 'beginner') == 'advanced':
                    continue
                pending = ' (pending)' if profile.get('unavailable_reason') else ''
                print(f'{key}: {profile["label"]}{pending}')
            return 0
        if not args.profile and (args.headless or not sys.stdin.isatty()):
            raise ValueError('Agent/headless invocation requires --profile; use --list for IDs')
        profile = args.profile or choose_profile(config['profiles'])
        if profile is None:
            return 0
        command, environment, runtime = launch_plan(config, profile, headless=args.headless, runtime=args.runtime)
        if args.dry_run:
            print(shlex.join(command))
            return 0
        print(f'\n  {config["profiles"][profile]["label"]}\n  Evidence: {runtime}')
        print('  Flight commands start blocked. Takeoff is manual. Ctrl+C closes this run.\n', flush=True)
        os.execve(command[0], command, environment)
    except KeyboardInterrupt:
        print()
        return 130
    except (OSError, ValueError, EOFError) as error:
        print(f'Training launcher: {error}\nSetup: docs/followers/05-development/ubuntu-training-platform.md', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
