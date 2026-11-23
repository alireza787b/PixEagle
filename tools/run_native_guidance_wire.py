#!/usr/bin/env python3
"""Private training byte recorder; never creates, authorizes or replays a command."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from tools.native_sih_wire import WireRecorder  # noqa: E402


async def serve(frontend: Path, backend: Path, output: Path, stopped: asyncio.Event):
    for directory in (frontend.parent, output):
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError('Native wire directories must be private and owned')
    if frontend.is_symlink() or not stat.S_ISSOCK(backend.lstat().st_mode):
        raise ValueError('Native wire endpoints must be original Unix sockets')
    descriptor = os.open(output / 'wire.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', buffering=1) as stream:
        def log(name, row):
            stream.write(json.dumps(dict(timestamp=time.monotonic(), **row)) + '\n')
        async with WireRecorder(frontend, backend, log):
            await stopped.wait()


async def run(args):
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)
    try:
        await serve(args.frontend, args.backend, args.output, stopped)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', type=Path, required=True)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
