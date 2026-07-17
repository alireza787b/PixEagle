#!/usr/bin/env python3
"""Capture process stdout/stderr lines into PixEagle runtime JSONL logs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from classes.runtime_logging import RuntimeLogSessionManager  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture line-oriented component output into runtime logs."
    )
    parser.add_argument(
        "--component",
        help="Runtime log component name for stdin capture.",
    )
    parser.add_argument(
        "--stream",
        default="stdout",
        help="Stream label recorded on each entry. Default: stdout.",
    )
    parser.add_argument(
        "--source",
        default="process-pipe",
        help="Source label recorded on each entry. Default: process-pipe.",
    )
    parser.add_argument(
        "--level",
        default="INFO",
        help="Runtime log level for captured lines. Default: INFO.",
    )
    parser.add_argument(
        "--prepare-components",
        nargs="*",
        default=None,
        help="Create the runtime session and register these component files.",
    )
    parser.add_argument(
        "--mirror",
        action="store_true",
        help="Also mirror stdin to stdout for launcher process pipes.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    manager = RuntimeLogSessionManager()

    if args.prepare_components is not None:
        manager.initialize_session(components=args.prepare_components)

    if not args.component:
        return 0

    manager.register_component(args.component)
    for line in sys.stdin:
        if args.mirror:
            print(line, end="", flush=True)
        message = line.rstrip("\r\n")
        if not message:
            continue
        manager.append_component_message(
            args.component,
            message,
            level=args.level,
            stream=args.stream,
            source=args.source,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
