#!/usr/bin/env python3
"""Tiny lab-only MJPEG/WebSocket JPEG source for QGC receiver tests.

This tool is intentionally anonymous and should only be bound to loopback or a
trusted lab network. It proves QGC network-video receiver behavior, not
PixEagle deployment, PX4, SITL, HIL, field, or aircraft behavior.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import socket
import sys
import time
from dataclasses import dataclass
from typing import Tuple


JPEG_FRAME = base64.b64decode(
    """
/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAwAFADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDyyiivTv8AhVf/AFGf/JX/AOzr5zF4/D4O3t5Wvto3t6I9ilRnVvyK9jzGivTv+FV/9Rn/AMlf/s6P+FV/9Rn/AMlf/s64/wC3sB/z8/CX+Rr9Srfy/ijzGivTv+FV/wDUZ/8AJX/7Oj/hVf8A1Gf/ACV/+zo/t7Af8/Pwl/kH1Kt/L+KPMaK9O/4VX/1Gf/JX/wCzrC8Y+Cv+Ec0yK7+3/ad8wi2eTsxlWOc7j/drWjnODrzVOnO7fk/8hTwtWC5pLT5HHUUUV6ZzBX1FZ27XVwsSkLwSWbooAySa+Xa+qdIkRLl0kYIs0TRbm6KSOCfxr5biOMZ1cPGezb/9tPRwLajNrfT9R/2W0uVdLGSbzkUtiUABwOuMdD3xTYba3it45r5pcS5MaRYzgHGST2q7YadcWBN9cJsihVtwI5zjAx6gk9RUEkL39rZvbRmYwp5ckafeGCSD9CD1rwnhmoqUqdp2do2equtbff8Ad5M6/aXdlL3e/wB+l/u+8gWxWW6VIJ1aAoZDIRyijruHqPSiWGykic2ksqyIMlZsDePbHf2q+RawXT28YELzW5jcF9wRycgE/gM+lZ76bPDFJJdKYFUcbxy59B6/Woq0ORNQgnve19Pv276+j2KjU5nrK3bz/wA/kUq4X4w/8izbf9fi/wDoD13VcL8Yf+RZtv8Ar8X/ANAes8o/32l6l4r+DI8eooor9NPngr6I/wCEg0b/AKC+nf8AgSn+NfO9FeVmeVQzDl5pNct/xt/kdOHxLoXsr3PotfEulL93WrEcY4uk6enWmr4i0dTldY08H2uk/wAa+dqK8z/Ven/z8Z0f2jL+VH0R/wAJBo3/AEF9O/8AAlP8aVvEWjtjdrGnnHTN0n+NfO1FL/Val/z8f4D/ALRl/KfRH/CQaN/0F9O/8CU/xrjPirqmn3vh63jsr61uJBdKxWKZXIGx+cA9ORXlVFb4Xh2nhq0aym3YipjpVIuLW4UUUV9EcB//2Q==
"""
)

BOUNDARY = "pixeagle-qgc-test"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def websocket_accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key.strip() + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def websocket_binary_frame(payload: bytes) -> bytes:
    length = len(payload)
    if length < 126:
        header = bytes([0x82, length])
    elif length <= 0xFFFF:
        header = bytes([0x82, 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([0x82, 127]) + length.to_bytes(8, "big")
    return header + payload


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    fps: float

    @property
    def interval(self) -> float:
        return max(0.02, 1.0 / max(self.fps, 0.1))


class QGCMediaTestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "PixEagleQGCTestSource/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write(
            f"{self.log_date_time_string()} {self.client_address[0]} {fmt % args}\n"
        )

    @property
    def config(self) -> ServerConfig:
        return self.server.config  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler naming
        if self.path in {"/", "/health"}:
            self._send_index()
            return
        if self.path == "/still.jpg":
            self._send_still()
            return
        if self.path == "/mjpeg":
            self._send_mjpeg()
            return
        if self.path == "/ws":
            self._send_ws()
            return
        self.send_error(404, "Use /mjpeg, /ws, /still.jpg, or /health")

    def _send_index(self) -> None:
        host = self.headers.get("Host") or f"{self.config.host}:{self.config.port}"
        body = (
            "PixEagle QGC lab media source\n"
            f"HTTP MJPEG: http://{host}/mjpeg\n"
            f"WebSocket JPEG: ws://{host}/ws\n"
            f"Still JPEG: http://{host}/still.jpg\n"
            "Anonymous lab source only. Do not expose to untrusted networks.\n"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_still(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(JPEG_FRAME)))
        self.end_headers()
        self.wfile.write(JPEG_FRAME)

    def _send_mjpeg(self) -> None:
        self.send_response(200)
        self.send_header(
            "Content-Type",
            f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                self.wfile.write(f"--{BOUNDARY}\r\n".encode("ascii"))
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(JPEG_FRAME)}\r\n\r\n".encode("ascii"))
                self.wfile.write(JPEG_FRAME)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                time.sleep(self.config.interval)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def _send_ws(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        upgrade = self.headers.get("Upgrade", "")
        if not key or upgrade.casefold() != "websocket":
            self.send_error(400, "WebSocket upgrade required")
            return

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", websocket_accept_key(key))
        self.end_headers()

        frame = websocket_binary_frame(JPEG_FRAME)
        self.connection.settimeout(1.0)
        try:
            while True:
                self.connection.sendall(frame)
                time.sleep(self.config.interval)
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            return


class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    config: ServerConfig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8095)
    parser.add_argument("--fps", type=float, default=5.0)
    return parser.parse_args(argv)


def make_server(config: ServerConfig) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((config.host, config.port), QGCMediaTestHandler)
    server.config = config
    return server


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = ServerConfig(args.host, args.port, args.fps)
    server = make_server(config)
    actual_host, actual_port = server.server_address[:2]
    display_host = actual_host if actual_host not in {"0.0.0.0", "::"} else "<host-ip>"
    print("PixEagle QGC lab media source", flush=True)
    print(f"HTTP MJPEG: http://{display_host}:{actual_port}/mjpeg", flush=True)
    print(f"WebSocket JPEG: ws://{display_host}:{actual_port}/ws", flush=True)
    print("Anonymous lab source only. Stop with Ctrl-C.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
