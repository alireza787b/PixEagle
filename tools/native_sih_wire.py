"""Transparent, same-UID native SIH evidence relay; no control policy or publisher."""
from __future__ import annotations

import asyncio
import hashlib
import os
import json
from pathlib import Path

from classes.native_guidance import MAX_MESSAGE_BYTES


def archive_wire_helper(output: Path) -> dict:
    source = Path(__file__)
    destination = output / source.name
    data = source.read_bytes()
    destination.write_bytes(data)
    return {"path": destination.name, "sha256": hashlib.sha256(data).hexdigest()}


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
