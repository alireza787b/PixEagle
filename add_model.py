#!/usr/bin/env python3
"""Register a trusted local SmartTracker model."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from classes.model_artifact_policy import (  # noqa: E402
    ModelArtifactPolicyError,
    ModelIngestLease,
    normalize_sha256,
    sha256_descriptor,
)
from classes.parameters import Parameters  # noqa: E402
ModelManager = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Register an explicitly trusted local detect/OBB checkpoint. "
            "PyTorch .pt files may execute code while loading."
        )
    )
    parser.add_argument(
        "--model-name",
        required=True,
        help="Simple .pt filename under models/ (for example yolo26n.pt)",
    )
    parser.add_argument(
        "--source-file",
        help=(
            "External local .pt file to stage and atomically register without "
            "replacing an existing model; requires --sha256"
        ),
    )
    parser.add_argument(
        "--sha256",
        help="Expected 64-character SHA-256 digest from the model publisher",
    )
    parser.add_argument(
        "--trust-model",
        action="store_true",
        help="Confirm that you trust the checkpoint source and approve model loading",
    )
    parser.add_argument(
        "--export-ncnn",
        action="store_true",
        help="Explicitly export the registered model to NCNN",
    )
    return parser


class _LocalModelUpload:
    """Descriptor-bound adapter for the model manager's streaming ingest path."""

    def __init__(self, path: Path, *, max_bytes: int) -> None:
        self.path = path.expanduser()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags)
        except OSError as exc:
            raise ModelArtifactPolicyError(
                f"Source model could not be opened safely: {exc}"
            ) from exc
        try:
            expected_uid = getattr(os, "geteuid", lambda: os.fstat(descriptor).st_uid)()
            self.observed_sha256, _ = sha256_descriptor(
                descriptor,
                expected_uid=expected_uid,
                max_bytes=max_bytes,
            )
            self._stream = os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise

    async def read(self, size: int) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        self._stream.close()


def _print_observation(
    observation: Any,
    publisher_sha256: Optional[str],
) -> None:
    print(f"[INFO] Local artifact: {observation.path}")
    print(f"[INFO] Operator-observed SHA-256: {observation.observed_sha256}")
    if publisher_sha256:
        print(f"[INFO] Publisher SHA-256 supplied: {publisher_sha256.lower()}")
    else:
        print("[INFO] Publisher SHA-256 supplied: none")


def _confirm_local_trust(
    observation: Any,
    publisher_sha256: Optional[str],
) -> bool:
    _print_observation(observation, publisher_sha256)
    if not sys.stdin.isatty():
        print(
            "[ERROR] Non-interactive registration requires --trust-model. "
            "Use --sha256 as well for deployment evidence."
        )
        return False
    answer = input(
        "This .pt file may execute code while loading. Trust its source and continue? [y/N]: "
    )
    return answer.strip().lower() == "y"


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    manager_class = ModelManager
    if manager_class is None:
        from classes.model_manager import ModelManager as manager_class
    from classes.model_manager import model_manager_kwargs_from_parameters

    manager = manager_class(**model_manager_kwargs_from_parameters(Parameters))

    try:
        expected_sha256 = normalize_sha256(args.sha256)
    except ModelArtifactPolicyError as exc:
        print(f"[ERROR] {exc}")
        return 2
    if (
        getattr(manager, "trust_policy", "operator_ack_or_digest")
        == "digest_required"
        and expected_sha256 is None
    ):
        print("[ERROR] This deployment requires the model publisher's SHA-256 digest")
        return 2
    if args.source_file is not None and expected_sha256 is None:
        print("[ERROR] --source-file requires the model publisher's --sha256 digest")
        return 2

    trust_model = bool(args.trust_model)
    source_ingest = args.source_file is not None
    try:
        if source_ingest:
            upload = _LocalModelUpload(
                Path(args.source_file),
                max_bytes=manager.max_model_bytes,
            )
            try:
                observation = SimpleNamespace(
                    path=upload.path,
                    observed_sha256=upload.observed_sha256,
                )
                if (
                    expected_sha256 is not None
                    and upload.observed_sha256 != expected_sha256
                ):
                    _print_observation(observation, expected_sha256)
                    print("[ERROR] Source model SHA-256 does not match the publisher digest")
                    return 2
                if trust_model:
                    _print_observation(observation, expected_sha256)
                else:
                    trust_model = _confirm_local_trust(
                        observation,
                        expected_sha256,
                    )
                    if not trust_model:
                        print("[ERROR] Model trust was not approved; nothing was executed.")
                        return 2
                with ModelIngestLease(Path(manager.models_folder), timeout_seconds=0.0):
                    result = asyncio.run(
                        manager.upload_model_file(
                            upload_file=upload,
                            filename=args.model_name,
                            auto_export_ncnn=bool(args.export_ncnn),
                            expected_sha256=expected_sha256,
                            trust_model=True,
                            source="local_cli_source_file",
                        )
                    )
            finally:
                upload.close()
        else:
            with manager.observe_local_model(args.model_name) as observation:
                if trust_model:
                    _print_observation(observation, expected_sha256)
                else:
                    trust_model = _confirm_local_trust(observation, expected_sha256)
                    if not trust_model:
                        print("[ERROR] Model trust was not approved; nothing was executed.")
                        return 2
                result = manager.trust_observed_local_model(
                    observation,
                    expected_sha256=expected_sha256,
                    trust_model=True,
                    source="local_cli_existing_file",
                )
    except FileNotFoundError as exc:
        print(
            f"[ERROR] {exc}. Download it outside PixEagle, verify the publisher "
            "digest, and place it in models/."
        )
        return 2
    except (OSError, ModelArtifactPolicyError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not result.get("success"):
        print(f"[ERROR] {result.get('error', 'Model registration failed')}")
        return 1

    validation = result.get("validation") or {}
    print(f"[OK] Registered: {result['path']}")
    print(f"[OK] SHA-256: {result['artifact_sha256']}")
    print(f"[OK] Operator-observed SHA-256: {result.get('observed_sha256')}")
    print(
        "[OK] Publisher SHA-256: "
        f"{result.get('publisher_sha256') or 'not supplied'}"
    )
    print(f"[OK] Trust method: {result.get('trust_method', 'unknown')}")
    print(
        "[OK] Registration action: "
        f"{result.get('registration_action_id', 'unavailable')}"
    )
    print(f"[OK] Task: {validation.get('task', 'unknown')}")
    print(f"[OK] Classes: {validation.get('num_classes', 0)}")

    if args.export_ncnn and source_ingest:
        export_result = result.get("ncnn_export") or {}
        if not export_result.get("success"):
            print(f"[ERROR] NCNN export failed: {export_result.get('error')}")
            return 1
        print(f"[OK] NCNN export: {export_result['ncnn_path']}")
        print(f"[OK] NCNN SHA-256: {export_result['artifact_sha256']}")
    elif args.export_ncnn:
        export_result = manager.export_to_ncnn(Path(result["path"]))
        if not export_result.get("success"):
            print(f"[ERROR] NCNN export failed: {export_result.get('error')}")
            return 1
        print(f"[OK] NCNN export: {export_result['ncnn_path']}")
        print(f"[OK] NCNN SHA-256: {export_result['artifact_sha256']}")
    else:
        print("[INFO] NCNN export was not requested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
