# src/classes/model_manager.py

"""
ModelManager - Clean, single class for all detection model operations

Handles:
- Model discovery (scan models/ folder)
- Validation (check .pt files, extract metadata, detect custom models)
- Bounded local upload ingestion and verified file download
- NCNN export
- Model deletion
- Metadata caching

Project: PixEagle
Author: Alireza Ghaderi
Repository: https://github.com/alireza787b/PixEagle
"""

import os
import json
import time
import shutil
import logging
import asyncio
import math
import secrets
import select
import signal
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
import importlib.util
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

from classes.model_artifact_policy import (
    DEFAULT_MODELS_ROOT,
    DEFAULT_MAX_EXPORT_BYTES,
    DEFAULT_MAX_EXPORT_FILES,
    DEFAULT_MAX_MODEL_BYTES,
    HARD_MAX_MODEL_BYTES,
    ModelArtifactNotFoundError,
    ModelArtifactPolicyError,
    ModelLoaderBinding,
    ModelProvenanceStore,
    ModelRegistryCorruptionError,
    ModelStoreBusyError,
    ModelStoreLease,
    normalize_sha256,
    publisher_digest_provenance_verified,
    resolve_model_path,
    sha256_descriptor,
    sha256_directory_descriptor,
    sha256_file,
    validate_models_root,
    validate_model_filename,
)

# Conditional AI imports - allows app to run without ultralytics/torch
# Catches ImportError (not installed) and other errors (incompatible on ARM, etc.)
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False
    logging.warning("PyTorch not installed - AI features disabled")
except Exception as e:
    torch = None
    TORCH_AVAILABLE = False
    logging.warning(f"PyTorch import failed: {e} - AI features disabled")

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False
    logging.warning("Ultralytics not installed - YOLO functionality disabled")
except Exception as e:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False
    logging.warning(f"Ultralytics import failed: {e} - YOLO functionality disabled")

AI_AVAILABLE = TORCH_AVAILABLE and ULTRALYTICS_AVAILABLE
MODEL_TRUST_POLICIES = {"operator_ack_or_digest", "digest_required"}
MODEL_MUTATION_LEASE_TIMEOUT_SECONDS = 0.1
MODEL_CACHE_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_NCNN_EXPORT_TIMEOUT_SECONDS = 900.0
HARD_MAX_NCNN_EXPORT_TIMEOUT_SECONDS = 3600.0
NCNN_EXPORT_MONITOR_INTERVAL_SECONDS = 0.05
NCNN_EXPORT_WORKSPACE_MAX_ENTRIES = 512
NCNN_EXPORT_WORKSPACE_OVERHEAD_BYTES = 16 * 1024 * 1024
NCNN_EXPORT_RESULT_MAX_BYTES = 16 * 1024
NCNN_EXPORT_CONTROL_RESULT_MAX_BYTES = 16 * 1024
NCNN_EXPORT_ADDRESS_SPACE_LIMIT_BYTES = 8 * 1024 * 1024 * 1024
NCNN_EXPORT_OPEN_FILES_LIMIT = 128
NCNN_EXPORT_ADDITIONAL_PROCESSES = 64
NCNN_EXPORT_MAX_UID_TASKS = 4096
MODEL_INSPECTION_CACHE_SCHEMA_VERSION = 1
NCNN_EXPORT_ADMISSION_TIMEOUT_SECONDS = 2.0
NCNN_EXPORT_CONTAINMENT_CLEANUP_SECONDS = 4.0
CGROUP_V2_ROOT = Path("/sys/fs/cgroup")


@dataclass
class LocalModelObservation:
    """Descriptor-bound digest shown to an operator before checkpoint execution."""

    model_name: str
    path: Path
    observed_sha256: str
    size_bytes: int
    descriptor: int
    lease: ModelStoreLease
    manager_token: object
    active: bool = True


@dataclass
class _LinuxCgroupContainment:
    """Transient cgroup-v2 boundary whose emptiness is required for success."""

    path: Path
    closed: bool = False

    @staticmethod
    def _read_events(path: Path) -> Dict[str, int]:
        try:
            lines = (path / "cgroup.events").read_text(encoding="ascii").splitlines()
            return {
                key: int(value)
                for key, value in (line.split(maxsplit=1) for line in lines)
            }
        except (OSError, UnicodeError, ValueError) as exc:
            raise ModelArtifactPolicyError(
                "NCNN export cgroup state is unreadable"
            ) from exc

    @staticmethod
    def _write_control(path: Path, value: str) -> None:
        flags = os.O_WRONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ModelArtifactPolicyError(
                f"NCNN export cgroup control is unavailable: {path.name}"
            ) from exc
        try:
            payload = value.encode("ascii")
            offset = 0
            while offset < len(payload):
                offset += os.write(descriptor, payload[offset:])
        finally:
            os.close(descriptor)

    def admit_process(self, pid: int) -> None:
        if self.closed or not isinstance(pid, int) or pid <= 0:
            raise ModelArtifactPolicyError("NCNN export cgroup admission is invalid")
        self._write_control(self.path / "cgroup.procs", f"{pid}\n")
        try:
            members = {
                int(value)
                for value in (self.path / "cgroup.procs")
                .read_text(encoding="ascii")
                .splitlines()
                if value.strip()
            }
        except (OSError, UnicodeError, ValueError) as exc:
            raise ModelArtifactPolicyError(
                "NCNN export cgroup membership could not be verified"
            ) from exc
        if pid not in members:
            raise ModelArtifactPolicyError(
                "NCNN export worker did not enter its containment cgroup"
            )

    def cleanup(self) -> None:
        if self.closed:
            return
        cleanup_error: Optional[BaseException] = None
        try:
            events = self._read_events(self.path)
            if events.get("populated") != 0:
                self._write_control(self.path / "cgroup.kill", "1\n")
                deadline = time.monotonic() + NCNN_EXPORT_CONTAINMENT_CLEANUP_SECONDS
                while time.monotonic() < deadline:
                    if self._read_events(self.path).get("populated") == 0:
                        break
                    time.sleep(0.02)
            if self._read_events(self.path).get("populated") != 0:
                raise ModelArtifactPolicyError(
                    "NCNN export descendants could not be terminated"
                )
        except BaseException as exc:
            cleanup_error = exc
        try:
            os.rmdir(self.path)
            self.closed = True
        except OSError as exc:
            cleanup_error = cleanup_error or ModelArtifactPolicyError(
                f"NCNN export cgroup could not be removed: {exc}"
            )
        if cleanup_error is not None:
            raise cleanup_error


def model_manager_kwargs_from_parameters(parameters: Any) -> Dict[str, Any]:
    """Resolve model-store policy from the grouped SmartTracker config section."""
    smart_tracker = getattr(parameters, "SmartTracker", {})
    if not isinstance(smart_tracker, dict):
        smart_tracker = {}
    return {
        "max_model_bytes": smart_tracker.get(
            "SMART_TRACKER_MODEL_MAX_BYTES",
            DEFAULT_MAX_MODEL_BYTES,
        ),
        "trust_policy": smart_tracker.get(
            "SMART_TRACKER_MODEL_TRUST_POLICY",
            "operator_ack_or_digest",
        ),
        "ncnn_export_timeout_seconds": smart_tracker.get(
            "SMART_TRACKER_NCNN_EXPORT_TIMEOUT_SECONDS",
            DEFAULT_NCNN_EXPORT_TIMEOUT_SECONDS,
        ),
    }


class ModelManager:
    """
    Centralized manager for detection model operations.

    Features:
    - Auto-discovery of models in models/ folder
    - Validation with custom model detection
    - Atomic ingestion with provenance and opt-in NCNN export
    - Model switching support
    - Metadata caching for performance
    """

    def __init__(
        self,
        models_folder: Optional[str] = None,
        *,
        max_model_bytes: int = DEFAULT_MAX_MODEL_BYTES,
        trust_policy: str = "operator_ack_or_digest",
        ncnn_export_timeout_seconds: float = DEFAULT_NCNN_EXPORT_TIMEOUT_SECONDS,
    ):
        """
        Initialize Model Manager

        Args:
            models_folder: Optional injected model root. Runtime defaults to the
                canonical repository models folder.
        """
        requested_root = Path(models_folder) if models_folder else DEFAULT_MODELS_ROOT
        self.models_folder = validate_models_root(requested_root, create=True)
        self.max_model_bytes = int(max_model_bytes)
        if not 0 < self.max_model_bytes <= HARD_MAX_MODEL_BYTES:
            raise ValueError(
                f"max_model_bytes must be between 1 and {HARD_MAX_MODEL_BYTES}"
            )
        self.trust_policy = str(trust_policy or "").strip().lower()
        if self.trust_policy not in MODEL_TRUST_POLICIES:
            raise ValueError(
                "trust_policy must be one of: "
                + ", ".join(sorted(MODEL_TRUST_POLICIES))
            )
        self.ncnn_export_timeout_seconds = float(ncnn_export_timeout_seconds)
        if not (
            0.01
            <= self.ncnn_export_timeout_seconds
            <= HARD_MAX_NCNN_EXPORT_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "ncnn_export_timeout_seconds must be between 0.01 and "
                f"{HARD_MAX_NCNN_EXPORT_TIMEOUT_SECONDS}"
            )
        self.provenance = ModelProvenanceStore(self.models_folder)
        self._registration_token = object()
        self.quarantined_models: Dict[str, Dict[str, Any]] = {}

        # Metadata cache file
        self.metadata_file = self.models_folder / ".models.json"

        # Logging
        self.logger = logging.getLogger(__name__)

        # Load cached metadata
        self.cache = self._load_cache()

        self.logger.info(f"ModelManager initialized (folder: {self.models_folder})")

    # ==================== MODEL DISCOVERY ====================

    def discover_models(self, force_rescan: bool = False) -> Dict[str, Dict]:
        """
        Scan yolo/ folder for available models

        Args:
            force_rescan: If True, ignore cache and rescan all files

        Returns:
            Dictionary of models:
            {
                "model_id": {
                    "name": "YOLO26n",
                    "path": "models/yolo26n.pt",
                    "type": "gpu",  # gpu | cpu
                    "format": "pt",  # pt | ncnn
                    "size_mb": 5.35,
                    "num_classes": 80,
                    "class_names": ["person", "car", ...],
                    "is_custom": False,
                    "has_ncnn": True,
                    "ncnn_path": "models/yolo26n_ncnn_model",
                    "last_modified": 1234567890.0
                }
            }
        """
        # `force_rescan` means re-read and re-hash filesystem/provenance state. It
        # never authorizes checkpoint execution on a GET/inventory path.
        _ = force_rescan
        models: Dict[str, Dict[str, Any]] = {}
        quarantined: Dict[str, Dict[str, Any]] = {}
        with ModelStoreLease(
            self.models_folder,
            exclusive=False,
            timeout_seconds=MODEL_MUTATION_LEASE_TIMEOUT_SECONDS,
        ) as lease:
            # A corrupt registry is an availability/safety fault, not an empty inventory.
            self.provenance.load_locked(lease)
            pt_files = sorted(self.models_folder.glob("*.pt"))

            for pt_file in pt_files:
                model_id = pt_file.stem
                try:
                    provenance, artifact_stat = self.provenance.verify_pt_stat_locked(
                        pt_file,
                        lease,
                        max_bytes=self.max_model_bytes,
                    )
                except ModelRegistryCorruptionError:
                    raise
                except ModelArtifactPolicyError as exc:
                    self.logger.warning(
                        "Skipping untrusted model artifact %s: %s",
                        pt_file,
                        exc,
                    )
                    continue

                if not self._execution_provenance_allowed(provenance):
                    quarantined[model_id] = {
                        "artifact_sha256": provenance.get("sha256"),
                        "path": str(pt_file),
                        "reason": (
                            "digest_required requires a descriptor-bound publisher "
                            "digest registration"
                        ),
                        "trust_method": provenance.get("trust_method"),
                    }
                    self.logger.error(
                        "Quarantining model %s: production digest provenance is incomplete",
                        pt_file,
                    )
                    continue

                cached = self.cache.get(model_id)
                validation_result = self._cached_validation(
                    cached,
                    provenance=provenance,
                )
                if validation_result is None:
                    validation_result = self._uninspected_validation()
                models[model_id] = self._build_model_info(
                    pt_file,
                    validation_result,
                    provenance,
                    lease=lease,
                    artifact_stat=artifact_stat,
                )

        self.quarantined_models = quarantined
        self.cache = models
        self._save_cache()
        self.logger.info("Discovered %d model(s)", len(models))
        return models

    def _execution_provenance_allowed(self, record: Dict[str, Any]) -> bool:
        """Require unambiguous publisher provenance in digest-required mode."""
        if self.trust_policy != "digest_required":
            return True
        return publisher_digest_provenance_verified(record)

    def _require_execution_provenance(
        self,
        record: Dict[str, Any],
        *,
        operation: str,
    ) -> None:
        if not self._execution_provenance_allowed(record):
            raise ModelArtifactPolicyError(
                f"{operation} refused: digest_required needs a descriptor-bound "
                "publisher digest registration; re-register the artifact"
            )

    @staticmethod
    def _uninspected_validation() -> Dict[str, Any]:
        return {
            "checkpoint_executed": False,
            "compatibility_notes": [
                "Metadata inspection is available only during an explicit model action."
            ],
            "inspection_required": True,
            "is_custom": False,
            "model_type": "unknown",
            "num_classes": 0,
            "class_names": [],
            "output_geometry": "unknown",
            "smarttracker_supported": False,
            "task": "unknown",
            "valid": True,
        }

    @staticmethod
    def _cached_validation(
        cached: Any,
        *,
        provenance: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(cached, dict):
            return None
        metadata = cached.get("metadata")
        if (
            cached.get("inspection_schema_version")
            != MODEL_INSPECTION_CACHE_SCHEMA_VERSION
            or cached.get("inspection_artifact_sha256") != provenance.get("sha256")
            or not isinstance(metadata, dict)
            or metadata.get("checkpoint_executed") is not True
        ):
            return None
        class_names = metadata.get("class_names")
        if (
            not isinstance(class_names, list)
            or len(class_names) > 10000
            or any(not isinstance(value, str) or len(value) > 512 for value in class_names)
        ):
            return None
        return dict(metadata)

    def normalize_model_id(self, model_identifier: Optional[str]) -> str:
        """
        Normalize model identifiers to canonical model_id keys used by discover_models().

        Accepts values such as:
        - "yolo26n"
        - "yolo26n.pt"
        - "models/yolo26n.pt"
        - "models/yolo26n_ncnn_model"
        """
        if not model_identifier:
            return ""

        model_name = Path(str(model_identifier)).name.strip()
        if not model_name:
            return ""

        if model_name.endswith("_ncnn_model"):
            model_name = model_name[:-len("_ncnn_model")]
        elif model_name.lower().endswith(".pt"):
            model_name = model_name[:-3]

        return model_name

    def get_model_info(self, model_identifier: Optional[str], force_rescan: bool = False) -> Optional[Dict]:
        """Return discovered model metadata by flexible model identifier."""
        model_id = self.normalize_model_id(model_identifier)
        if not model_id:
            return None

        models = self.discover_models(force_rescan=force_rescan)
        return models.get(model_id)

    def get_model_labels(self, model_identifier: Optional[str], force_rescan: bool = False) -> Tuple[Optional[Dict], List[str]]:
        """
        Return model metadata and normalized label list.

        Returns:
            Tuple[model_info, labels]
        """
        model_info = self.get_model_info(model_identifier, force_rescan=force_rescan)
        if not model_info:
            return None, []

        raw_labels = model_info.get("class_names") or model_info.get("metadata", {}).get("class_names") or []
        labels = [str(label).strip() for label in raw_labels if str(label).strip()]
        return model_info, labels

    def _generate_display_name(self, model_id: str, validation: Dict) -> str:
        """Generate user-friendly display name"""
        base_name = model_id.upper()

        # Add custom indicator
        if validation.get('is_custom'):
            base_name += " (Custom)"

        # Add model type prefix if detected
        model_type = validation.get('model_type', '')
        if model_type and model_type != 'custom':
            base_name = f"{model_type.upper()} {base_name}"

        return base_name

    def _build_model_info(
        self,
        pt_file: Path,
        validation: Dict[str, Any],
        provenance: Dict[str, Any],
        *,
        lease: ModelStoreLease,
        artifact_stat: Optional[os.stat_result] = None,
    ) -> Dict[str, Any]:
        """Build the API/cache representation for a trusted model."""
        ncnn_path = self._get_ncnn_path(pt_file)
        has_ncnn = False
        try:
            self.provenance.verify_ncnn_locked(
                ncnn_path,
                lease,
                max_source_bytes=self.max_model_bytes,
            )
            has_ncnn = True
        except ModelRegistryCorruptionError:
            raise
        except ModelArtifactPolicyError as exc:
            if os.path.lexists(ncnn_path):
                self.logger.warning(
                    "Ignoring untrusted NCNN export %s: %s",
                    ncnn_path,
                    exc,
                )

        if artifact_stat is None:
            _, artifact_stat = self.provenance.verify_pt_stat_locked(
                pt_file,
                lease,
                max_bytes=self.max_model_bytes,
            )
        checkpoint_executed = validation.get("checkpoint_executed") is True

        return {
            "name": self._generate_display_name(pt_file.stem, validation),
            "path": str(pt_file),
            "type": "gpu",
            "format": "pt",
            "size_bytes": artifact_stat.st_size,
            "size_mb": round(artifact_stat.st_size / (1024 * 1024), 2),
            "num_classes": validation.get("num_classes", 0),
            "class_names": validation.get("class_names", []),
            "is_custom": validation.get("is_custom", False),
            "task": validation.get("task", "unknown"),
            "output_geometry": validation.get("output_geometry", "aabb"),
            "smarttracker_supported": validation.get("smarttracker_supported", False),
            "compatibility_notes": validation.get("compatibility_notes", []),
            "has_ncnn": has_ncnn,
            "ncnn_path": str(ncnn_path) if has_ncnn else None,
            "last_modified": artifact_stat.st_mtime,
            "last_modified_ns": artifact_stat.st_mtime_ns,
            "artifact_sha256": provenance.get("sha256"),
            "trust_method": provenance.get("trust_method"),
            "trusted_source": provenance.get("source"),
            "trusted_at": provenance.get("recorded_at"),
            "registration_action_id": (
                (provenance.get("registration_receipt") or {}).get("action_id")
            ),
            "inspection_schema_version": (
                MODEL_INSPECTION_CACHE_SCHEMA_VERSION if checkpoint_executed else None
            ),
            "inspection_artifact_sha256": (
                provenance.get("sha256") if checkpoint_executed else None
            ),
            "metadata": validation,
        }

    def _registration_result(
        self,
        *,
        destination: Path,
        validation: Dict[str, Any],
        provenance: Dict[str, Any],
        model_info: Dict[str, Any],
        idempotent_replay: bool,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "model_id": destination.stem,
            "model_path": str(destination),
            "path": str(destination),
            "artifact_sha256": provenance["sha256"],
            "observed_sha256": provenance.get("observed_sha256"),
            "publisher_sha256": provenance.get("publisher_sha256"),
            "trust_method": provenance.get("trust_method"),
            "registration_receipt": provenance.get("registration_receipt"),
            "registration_action_id": (
                (provenance.get("registration_receipt") or {}).get("action_id")
            ),
            "idempotent_replay": bool(idempotent_replay),
            "validation": validation,
            "model_info": model_info,
            "ncnn_exported": False,
            "ncnn_export": None,
            "ncnn_path": None,
        }

    def _replay_validation(
        self,
        model_id: str,
        provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._cached_validation(
            self.cache.get(model_id),
            provenance=provenance,
        ) or self._uninspected_validation()

    def _check_ncnn_exists(self, pt_file: Path) -> bool:
        """Check whether a complete, provenance-matched NCNN export exists."""
        ncnn_folder = self._get_ncnn_path(pt_file)
        try:
            with ModelStoreLease(self.models_folder, exclusive=False) as lease:
                self.provenance.verify_ncnn_locked(
                    ncnn_folder,
                    lease,
                    max_source_bytes=self.max_model_bytes,
                )
            return True
        except ModelRegistryCorruptionError:
            raise
        except ModelArtifactPolicyError:
            return False
    
    def _verify_ncnn_files(self, ncnn_folder: Path) -> bool:
        """Verify that NCNN folder contains required files"""
        if not ncnn_folder or not ncnn_folder.exists() or not ncnn_folder.is_dir():
            return False

        # Check for required files with various possible names
        # Standard names: model.bin and model.param
        # Alternative: might be named after the model (e.g., yolo26n.bin, yolo26n.param)
        bin_files = list(ncnn_folder.glob("*.bin"))
        param_files = list(ncnn_folder.glob("*.param"))
        
        # Must have at least one .bin and one .param file
        if len(bin_files) > 0 and len(param_files) > 0:
            return True
        
        # Also check for model.bin and model.param specifically (most common)
        required_files = [
            ncnn_folder / "model.bin",
            ncnn_folder / "model.param"
        ]
        if all(f.exists() and f.is_file() for f in required_files):
            return True
        
        return False

    def _get_ncnn_path(self, pt_file: Path) -> Path:
        """Get NCNN folder path for a .pt file"""
        return pt_file.parent / f"{pt_file.stem}_ncnn_model"

    @staticmethod
    def _pnnx_available() -> bool:
        """Require the exact pnnx release approved for the pinned exporter."""
        if importlib.util.find_spec("pnnx") is None:
            return False
        try:
            from importlib import metadata

            return metadata.version("pnnx") == "20260526"
        except metadata.PackageNotFoundError:
            return False

    # ==================== MODEL VALIDATION ====================

    def validate_model(
        self,
        pt_file: Path,
        *,
        allow_checkpoint_execution: bool = False,
    ) -> Dict:
        """
        Validate .pt file and extract metadata

        Args:
            pt_file: Path to .pt model file

        Returns:
            {
                "valid": bool,
                "model_type": str,  # "yolo11", "yolov8", "custom"
                "num_classes": int,
                "class_names": List[str],
                "is_custom": bool,
                "error": Optional[str]
            }
        """
        if not allow_checkpoint_execution:
            return {
                "valid": False,
                "checkpoint_executed": False,
                "error": (
                    "Checkpoint execution is disabled for read-only validation; "
                    "use an explicit activation/registration action"
                ),
            }

        try:
            trusted_path = resolve_model_path(self.models_folder, Path(pt_file).name)
            candidate = Path(pt_file).expanduser()
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            if trusted_path != candidate:
                raise ModelArtifactPolicyError(
                    "Model validation refuses lexical aliases of the configured models folder"
                )
            with ModelStoreLease(self.models_folder, exclusive=False) as lease:
                provenance, _, descriptor = self.provenance.verify_pt_pinned_locked(
                    trusted_path,
                    lease,
                    max_bytes=self.max_model_bytes,
                )
                try:
                    self._require_execution_provenance(
                        provenance,
                        operation="Checkpoint validation",
                    )
                    result = self._inspect_trusted_checkpoint(
                        lease.loader_binding(descriptor, trusted_path.name)
                    )
                    observed_after, _ = sha256_descriptor(
                        descriptor,
                        expected_uid=lease.expected_uid,
                        max_bytes=self.max_model_bytes,
                    )
                    lease.assert_descriptor_binding(trusted_path.name, descriptor)
                    if observed_after != provenance.get("sha256"):
                        raise ModelArtifactPolicyError(
                            "Model changed while checkpoint validation was running"
                        )
                finally:
                    lease.release_descriptor(descriptor)
            result["provenance"] = provenance
            return result
        except ModelRegistryCorruptionError:
            raise
        except Exception as e:
            self.logger.error(f"Model validation failed for {pt_file}: {e}")
            return {
                "valid": False,
                "error": str(e)
            }

    def _inspect_trusted_checkpoint(
        self,
        loader_binding: ModelLoaderBinding,
    ) -> Dict[str, Any]:
        """Load a checkpoint only after its caller has established explicit trust."""
        if not ULTRALYTICS_AVAILABLE:
            return {
                "valid": False,
                "error": "Ultralytics not installed",
            }

        model = None
        checkpoint_execution_started = False
        try:
            if not isinstance(loader_binding, ModelLoaderBinding):
                raise ModelArtifactPolicyError(
                    "Checkpoint inspection requires a verified format-preserving "
                    "loader binding"
                )
            pt_file = loader_binding.verified_path()
            checkpoint_execution_started = True
            model = YOLO(str(pt_file))
            loader_binding.verified_path()

            # Extract basic metadata
            num_classes = len(model.names) if hasattr(model, 'names') else 0
            class_names = list(model.names.values()) if hasattr(model, 'names') else []
            task = getattr(model, 'task', 'unknown')

            # Detect custom models (non-COCO)
            is_custom = self._is_custom_model(class_names, num_classes)

            # Detect model type
            model_type = self._detect_model_type(
                Path(loader_binding.artifact_name).stem
            )

            output_geometry = "obb" if task == "obb" else "aabb"
            compatibility_notes = []
            smarttracker_supported = True
            if task not in ("detect", "obb"):
                smarttracker_supported = False
                compatibility_notes.append(
                    f"SmartTracker currently supports detect/obb tasks, got '{task}'."
                )

            return {
                "valid": True,
                "checkpoint_executed": True,
                "model_type": model_type,
                "task": task,
                "output_geometry": output_geometry,
                "smarttracker_supported": smarttracker_supported,
                "compatibility_notes": compatibility_notes,
                "num_classes": num_classes,
                "class_names": class_names,
                "is_custom": is_custom
            }

        except Exception as e:
            self.logger.error(
                "Trusted model inspection failed for %s: %s",
                getattr(loader_binding, "artifact_name", "unbound artifact"),
                e,
            )
            return {
                "valid": False,
                "checkpoint_executed": checkpoint_execution_started,
                "error": str(e)
            }
        finally:
            model = None

    def _detect_model_type(self, filename: str) -> str:
        """Detect YOLO version from filename"""
        filename_lower = filename.lower()

        if 'yolo11' in filename_lower or 'yolo-11' in filename_lower:
            return "yolo11"
        elif 'yolov8' in filename_lower or 'yolo-v8' in filename_lower:
            return "yolov8"
        elif 'yolov5' in filename_lower or 'yolo-v5' in filename_lower:
            return "yolov5"
        else:
            return "custom"

    def _is_custom_model(self, class_names: List[str], num_classes: int) -> bool:
        """
        Detect if model is custom-trained (not standard COCO)

        Args:
            class_names: List of class names from model
            num_classes: Number of classes

        Returns:
            True if custom model, False if standard COCO
        """
        # Standard COCO has 80 classes
        if num_classes != 80:
            return True

        # Check if class names match COCO
        COCO_CLASSES = [
            "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
            "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
            "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
            "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
            "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
            "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
            "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
            "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
            "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
            "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"
        ]

        # If class names don't match COCO, it's custom
        if set(class_names) != set(COCO_CLASSES):
            return True

        return False

    # ==================== UPLOAD HANDLING ====================

    @contextmanager
    def _model_mutation_lock(self):
        """Serialize all model-store mutations across threads and processes."""
        with ModelStoreLease(
            self.models_folder,
            exclusive=True,
            timeout_seconds=MODEL_MUTATION_LEASE_TIMEOUT_SECONDS,
        ) as lease:
            yield lease

    def _new_staging_file(self) -> Tuple[int, Path]:
        descriptor, name = tempfile.mkstemp(
            prefix=".model-ingest-",
            suffix=".pt",
            dir=str(self.models_folder),
        )
        os.fchmod(descriptor, 0o600)
        return descriptor, Path(name)

    def _stage_bytes(self, file_data: bytes) -> Path:
        if not isinstance(file_data, (bytes, bytearray, memoryview)):
            raise ModelArtifactPolicyError("Uploaded model content must be bytes")
        if not file_data:
            raise ModelArtifactPolicyError("Uploaded model is empty")
        if len(file_data) > self.max_model_bytes:
            raise ModelArtifactPolicyError(
                f"Uploaded model exceeds the {self.max_model_bytes} byte safety limit"
            )
        descriptor, staged_path = self._new_staging_file()
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(file_data)
                stream.flush()
                os.fsync(stream.fileno())
            return staged_path
        except BaseException:
            staged_path.unlink(missing_ok=True)
            raise

    async def _await_worker_completion(self, awaitable: Any, *, operation: str) -> Any:
        """Do not release transaction ownership while non-cancellable worker code runs."""
        task = asyncio.create_task(awaitable)
        cancellation: Optional[asyncio.CancelledError] = None
        while True:
            try:
                result = await asyncio.shield(task)
                break
            except asyncio.CancelledError as exc:
                cancellation = cancellation or exc
                self.logger.warning(
                    "%s request cancelled; retaining ownership until worker completion",
                    operation,
                )
                if task.done():
                    break

        if cancellation is not None:
            try:
                task.result()
            except Exception as exc:
                self.logger.error(
                    "%s worker failed after request cancellation: %s",
                    operation,
                    exc,
                )
            raise cancellation
        return result

    async def _stage_upload_file(self, upload_file: Any) -> Path:
        descriptor, staged_path = self._new_staging_file()
        total = 0
        try:
            with os.fdopen(descriptor, "wb") as stream:
                while True:
                    chunk = await upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.max_model_bytes:
                        raise ModelArtifactPolicyError(
                            "Uploaded model exceeds the "
                            f"{self.max_model_bytes} byte safety limit"
                        )
                    stream.write(chunk)
                if total == 0:
                    raise ModelArtifactPolicyError("Uploaded model is empty")
                stream.flush()
                os.fsync(stream.fileno())
            return staged_path
        except BaseException:
            staged_path.unlink(missing_ok=True)
            raise

    def _commit_staged_model(
        self,
        staged_path: Path,
        *,
        filename: str,
        expected_sha256: Optional[str],
        trust_model: bool,
        source: str,
    ) -> Dict[str, Any]:
        with self._model_mutation_lock() as lease:
            return self._commit_staged_model_locked(
                staged_path,
                filename=filename,
                expected_sha256=expected_sha256,
                trust_model=trust_model,
                source=source,
                lease=lease,
            )

    @staticmethod
    def _exact_descriptor_path(descriptor: int) -> Path:
        path = Path(f"/proc/self/fd/{descriptor}")
        if os.name != "posix" or not path.exists():
            raise ModelArtifactPolicyError(
                "Exact checkpoint inspection requires procfs descriptor paths"
            )
        return path

    @staticmethod
    def _same_artifact_stat(left: os.stat_result, right: os.stat_result) -> bool:
        return (
            left.st_dev,
            left.st_ino,
            left.st_mode,
            left.st_uid,
            left.st_nlink,
            left.st_size,
            left.st_mtime_ns,
            left.st_ctime_ns,
        ) == (
            right.st_dev,
            right.st_ino,
            right.st_mode,
            right.st_uid,
            right.st_nlink,
            right.st_size,
            right.st_mtime_ns,
            right.st_ctime_ns,
        )

    def _assert_path_matches_descriptor(
        self,
        path: Path,
        descriptor: int,
        *,
        message: str,
    ) -> os.stat_result:
        descriptor_stat = os.fstat(descriptor)
        path_stat = os.stat(path, follow_symlinks=False)
        if not self._same_artifact_stat(descriptor_stat, path_stat):
            raise ModelArtifactPolicyError(message)
        return descriptor_stat

    def _commit_staged_model_locked(
        self,
        staged_path: Path,
        *,
        filename: str,
        expected_sha256: Optional[str],
        trust_model: bool,
        source: str,
        lease: ModelStoreLease,
    ) -> Dict[str, Any]:
        safe_name = validate_model_filename(filename)
        destination = resolve_model_path(self.models_folder, safe_name)
        if not trust_model:
            raise ModelArtifactPolicyError(
                "Explicit model trust acknowledgement is required before checkpoint execution"
            )

        expected = normalize_sha256(expected_sha256)
        if self.trust_policy == "digest_required" and expected is None:
            raise ModelArtifactPolicyError(
                "This deployment requires the model publisher's SHA-256 digest"
            )
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        staged_descriptor = os.open(staged_path, flags)
        try:
            observed, artifact_stat = sha256_descriptor(
                staged_descriptor,
                expected_uid=lease.expected_uid,
                max_bytes=self.max_model_bytes,
            )
            self._assert_path_matches_descriptor(
                staged_path,
                staged_descriptor,
                message="Staged model changed before checkpoint inspection",
            )
            if expected is not None and observed != expected:
                raise ModelArtifactPolicyError(
                    f"Model SHA-256 mismatch: expected {expected}, observed {observed}"
                )

            if destination.exists():
                if expected is None:
                    raise FileExistsError(
                        f"Model '{destination.stem}' already exists; delete or rename it first"
                    )
                try:
                    replay = self.provenance.find_registration_replay_locked(
                        destination,
                        observed_sha256=observed,
                        source=source,
                        publisher_sha256=expected,
                        lease=lease,
                        max_bytes=self.max_model_bytes,
                    )
                except ModelRegistryCorruptionError:
                    raise
                except ModelArtifactPolicyError:
                    result = self._reregister_existing_model_locked(
                        destination,
                        observed_sha256=observed,
                        publisher_sha256=expected,
                        size_bytes=artifact_stat.st_size,
                        source=source,
                        lease=lease,
                    )
                    staged_path.unlink(missing_ok=True)
                    return result
                if replay is None:
                    raise FileExistsError(
                        f"Model '{destination.stem}' already exists with a different "
                        "registration transaction"
                    )
                validation = self._replay_validation(destination.stem, replay)
                _, existing_stat = self.provenance.verify_pt_stat_locked(
                    destination,
                    lease,
                    max_bytes=self.max_model_bytes,
                )
                model_info = self._build_model_info(
                    destination,
                    validation,
                    replay,
                    lease=lease,
                    artifact_stat=existing_stat,
                )
                self.cache[destination.stem] = model_info
                self._save_cache()
                staged_path.unlink(missing_ok=True)
                return self._registration_result(
                    destination=destination,
                    validation=validation,
                    provenance=replay,
                    model_info=model_info,
                    idempotent_replay=True,
                )

            loader_descriptor = lease.pin_descriptor_copy(staged_descriptor)
            try:
                validation = self._inspect_trusted_checkpoint(
                    lease.loader_binding(loader_descriptor, safe_name)
                )
            finally:
                lease.release_descriptor(loader_descriptor)
            if not validation.get("valid", False):
                raise ModelArtifactPolicyError(
                    "Trusted checkpoint inspection failed: "
                    f"{validation.get('error', 'unknown error')}"
                )
            if not validation.get("smarttracker_supported", False):
                raise ModelArtifactPolicyError(
                    "SmartTracker supports only detect/obb models; "
                    f"received task={validation.get('task', 'unknown')}"
                )
            observed_after, artifact_stat_after = sha256_descriptor(
                staged_descriptor,
                expected_uid=lease.expected_uid,
                max_bytes=self.max_model_bytes,
            )
            if observed_after != observed:
                raise ModelArtifactPolicyError(
                    "Staged model changed while checkpoint inspection was running"
                )
            self._assert_path_matches_descriptor(
                staged_path,
                staged_descriptor,
                message="Staged model binding changed before registration",
            )

            try:
                os.link(staged_path, destination, follow_symlinks=False)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"Model '{destination.stem}' appeared during registration"
                ) from exc
            os.unlink(staged_path)
            os.chmod(destination, 0o600)
            try:
                provenance = self.provenance.trust_pt_descriptor_locked(
                    destination,
                    descriptor=staged_descriptor,
                    sha256=observed,
                    source=source,
                    expected_digest_verified=expected is not None,
                    publisher_sha256=expected,
                    operator_observed_sha256=observed,
                    lease=lease,
                    max_bytes=self.max_model_bytes,
                )
            except Exception:
                destination.unlink(missing_ok=True)
                raise
        finally:
            os.close(staged_descriptor)

        model_info = self._build_model_info(
            destination,
            validation,
            provenance,
            lease=lease,
            artifact_stat=artifact_stat_after,
        )
        self.cache[destination.stem] = model_info
        self._save_cache()
        return self._registration_result(
            destination=destination,
            validation=validation,
            provenance=provenance,
            model_info=model_info,
            idempotent_replay=False,
        )

    def _reregister_existing_model_locked(
        self,
        destination: Path,
        *,
        observed_sha256: str,
        publisher_sha256: str,
        size_bytes: int,
        source: str,
        lease: ModelStoreLease,
    ) -> Dict[str, Any]:
        """Replace only incomplete legacy provenance for the same pinned artifact."""
        descriptor = lease.pin_model(destination.name)
        try:
            existing_digest, existing_stat = sha256_descriptor(
                descriptor,
                expected_uid=lease.expected_uid,
                max_bytes=self.max_model_bytes,
            )
            lease.assert_descriptor_binding(destination.name, descriptor)
            if (
                existing_digest != observed_sha256
                or existing_stat.st_size != size_bytes
            ):
                raise FileExistsError(
                    f"Model '{destination.stem}' already exists with different bytes"
                )
            self.provenance.require_legacy_pt_reregistration_locked(
                destination,
                observed_sha256=existing_digest,
                publisher_sha256=publisher_sha256,
                size_bytes=existing_stat.st_size,
                lease=lease,
            )
            validation = self._inspect_trusted_checkpoint(
                lease.loader_binding(descriptor, destination.name)
            )
            if not validation.get("valid", False):
                raise ModelArtifactPolicyError(
                    "Trusted checkpoint inspection failed: "
                    f"{validation.get('error', 'unknown error')}"
                )
            if not validation.get("smarttracker_supported", False):
                raise ModelArtifactPolicyError(
                    "SmartTracker supports only detect/obb models; "
                    f"received task={validation.get('task', 'unknown')}"
                )
            observed_after, artifact_stat_after = sha256_descriptor(
                descriptor,
                expected_uid=lease.expected_uid,
                max_bytes=self.max_model_bytes,
            )
            lease.assert_descriptor_binding(destination.name, descriptor)
            if observed_after != existing_digest:
                raise ModelArtifactPolicyError(
                    "Model changed while legacy provenance was being replaced"
                )
            provenance = self.provenance.trust_pt_descriptor_locked(
                destination,
                descriptor=descriptor,
                sha256=existing_digest,
                source=source,
                expected_digest_verified=True,
                publisher_sha256=publisher_sha256,
                operator_observed_sha256=existing_digest,
                lease=lease,
                max_bytes=self.max_model_bytes,
            )
            model_info = self._build_model_info(
                destination,
                validation,
                provenance,
                lease=lease,
                artifact_stat=artifact_stat_after,
            )
            self.cache[destination.stem] = model_info
            self._save_cache()
            return self._registration_result(
                destination=destination,
                validation=validation,
                provenance=provenance,
                model_info=model_info,
                idempotent_replay=False,
            )
        finally:
            lease.release_descriptor(descriptor)

    async def _finish_model_ingest(
        self,
        staged_path: Path,
        *,
        filename: str,
        expected_sha256: Optional[str],
        trust_model: bool,
        source: str,
        auto_export_ncnn: bool,
    ) -> Dict[str, Any]:
        try:
            result = await self._await_worker_completion(
                asyncio.to_thread(
                    self._commit_staged_model,
                    staged_path,
                    filename=filename,
                    expected_sha256=expected_sha256,
                    trust_model=trust_model,
                    source=source,
                ),
                operation="model ingest commit",
            )
            model_path = Path(result["model_path"])
            if auto_export_ncnn:
                export_result = await self._await_worker_completion(
                    self._export_async(model_path),
                    operation="NCNN export",
                )
                result["ncnn_export"] = export_result
                result["ncnn_exported"] = bool(export_result.get("success"))

            discovered = await self._await_worker_completion(
                asyncio.to_thread(self.discover_models, force_rescan=True),
                operation="model inventory refresh",
            )
            model_info = discovered.get(result["model_id"])
            if model_info:
                result["model_info"] = model_info
                result["ncnn_exported"] = bool(
                    result["ncnn_exported"] or model_info.get("has_ncnn")
                )
            result["ncnn_path"] = (
                (result.get("ncnn_export") or {}).get("ncnn_path")
                or (result.get("model_info") or {}).get("ncnn_path")
            )
            result["message"] = (
                f"Model '{result['model_id']}' registered successfully"
                + (" with NCNN export." if result["ncnn_exported"] else ".")
            )
            return result
        except FileExistsError as exc:
            return {"success": False, "error": str(exc), "status_code": 409}
        except ModelRegistryCorruptionError as exc:
            return {"success": False, "error": str(exc), "status_code": 503}
        except ModelStoreBusyError as exc:
            return {"success": False, "error": str(exc), "status_code": 409}
        except ModelArtifactPolicyError as exc:
            return {"success": False, "error": str(exc), "status_code": 422}
        except Exception as exc:
            self.logger.error("Model ingestion failed: %s", exc)
            return {"success": False, "error": str(exc), "status_code": 500}
        finally:
            staged_path.unlink(missing_ok=True)

    async def upload_model(
        self,
        file_data: bytes,
        filename: str,
        auto_export_ncnn: bool = False,
        *,
        expected_sha256: Optional[str] = None,
        trust_model: bool = False,
        source: str = "api_upload",
    ) -> Dict[str, Any]:
        """Stage, inspect, and atomically register an explicitly trusted upload."""
        try:
            validate_model_filename(filename)
            staged_path = self._stage_bytes(file_data)
        except ModelArtifactPolicyError as exc:
            return {"success": False, "error": str(exc), "status_code": 422}
        return await self._finish_model_ingest(
            staged_path,
            filename=filename,
            expected_sha256=expected_sha256,
            trust_model=trust_model,
            source=source,
            auto_export_ncnn=auto_export_ncnn,
        )

    async def upload_model_file(
        self,
        upload_file: Any,
        filename: str,
        auto_export_ncnn: bool = False,
        *,
        expected_sha256: Optional[str] = None,
        trust_model: bool = False,
        source: str = "api_upload",
    ) -> Dict[str, Any]:
        """Stream an UploadFile into the bounded atomic ingestion path."""
        try:
            validate_model_filename(filename)
            staged_path = await self._stage_upload_file(upload_file)
        except ModelArtifactPolicyError as exc:
            return {"success": False, "error": str(exc), "status_code": 422}
        return await self._finish_model_ingest(
            staged_path,
            filename=filename,
            expected_sha256=expected_sha256,
            trust_model=trust_model,
            source=source,
            auto_export_ncnn=auto_export_ncnn,
        )

    def trust_local_model(
        self,
        model_name: str,
        *,
        expected_sha256: Optional[str] = None,
        trust_model: bool = False,
        source: str = "local_cli",
    ) -> Dict[str, Any]:
        """Register an existing local model after explicit operator approval."""
        try:
            with self.observe_local_model(model_name) as observation:
                return self.trust_observed_local_model(
                    observation,
                    expected_sha256=expected_sha256,
                    trust_model=trust_model,
                    source=source,
                )
        except ModelStoreBusyError as exc:
            return {"success": False, "error": str(exc), "status_code": 409}
        except ModelRegistryCorruptionError as exc:
            return {"success": False, "error": str(exc), "status_code": 503}
        except (FileNotFoundError, ModelArtifactPolicyError) as exc:
            return {"success": False, "error": str(exc), "status_code": 422}
        except Exception as exc:
            self.logger.error("Local model registration failed: %s", exc)
            return {"success": False, "error": str(exc), "status_code": 500}

    @contextmanager
    def observe_local_model(self, model_name: str):
        """Hold the exact local descriptor from operator observation to commit."""
        with self._model_mutation_lock() as lease:
            path = resolve_model_path(self.models_folder, model_name)
            if not path.is_file():
                raise FileNotFoundError(f"Model file not found: {path}")
            descriptor = lease.pin_model(path.name)
            try:
                observed, artifact_stat = sha256_descriptor(
                    descriptor,
                    expected_uid=lease.expected_uid,
                    max_bytes=self.max_model_bytes,
                )
                lease.assert_descriptor_binding(path.name, descriptor)
                observation = LocalModelObservation(
                    model_name=path.name,
                    path=path,
                    observed_sha256=observed,
                    size_bytes=artifact_stat.st_size,
                    descriptor=descriptor,
                    lease=lease,
                    manager_token=self._registration_token,
                )
                try:
                    yield observation
                finally:
                    observation.active = False
            finally:
                lease.release_descriptor(descriptor)

    def trust_observed_local_model(
        self,
        observation: LocalModelObservation,
        *,
        expected_sha256: Optional[str] = None,
        trust_model: bool = False,
        source: str = "local_cli",
    ) -> Dict[str, Any]:
        try:
            if (
                not isinstance(observation, LocalModelObservation)
                or observation.manager_token is not self._registration_token
                or not observation.active
            ):
                raise ModelArtifactPolicyError(
                    "Local model observation is not active for this manager"
                )
            lease = observation.lease
            path = observation.path
            if not trust_model:
                raise ModelArtifactPolicyError(
                    "Explicit model trust acknowledgement is required before checkpoint execution"
                )
            expected = normalize_sha256(expected_sha256)
            if self.trust_policy == "digest_required" and expected is None:
                raise ModelArtifactPolicyError(
                    "This deployment requires the model publisher's SHA-256 digest"
                )
            if expected is not None and expected != observation.observed_sha256:
                raise ModelArtifactPolicyError(
                    "Model SHA-256 mismatch: expected "
                    f"{expected}, observed {observation.observed_sha256}"
                )
            lease.assert_descriptor_binding(path.name, observation.descriptor)
            observed_before, artifact_stat = sha256_descriptor(
                observation.descriptor,
                expected_uid=lease.expected_uid,
                max_bytes=self.max_model_bytes,
            )
            if observed_before != observation.observed_sha256:
                raise ModelArtifactPolicyError(
                    "Model changed after the operator observed its digest"
                )

            replay = None
            try:
                replay = self.provenance.find_registration_replay_locked(
                    path,
                    observed_sha256=observation.observed_sha256,
                    source=source,
                    publisher_sha256=expected,
                    lease=lease,
                    max_bytes=self.max_model_bytes,
                )
            except ModelArtifactNotFoundError:
                pass
            except ModelRegistryCorruptionError:
                raise
            except ModelArtifactPolicyError:
                self.provenance.require_legacy_pt_reregistration_locked(
                    path,
                    observed_sha256=observation.observed_sha256,
                    publisher_sha256=expected or "",
                    size_bytes=artifact_stat.st_size,
                    lease=lease,
                )
            if replay is not None:
                validation = self._replay_validation(path.stem, replay)
                model_info = self._build_model_info(
                    path,
                    validation,
                    replay,
                    lease=lease,
                    artifact_stat=artifact_stat,
                )
                self.cache[path.stem] = model_info
                self._save_cache()
                return self._registration_result(
                    destination=path,
                    validation=validation,
                    provenance=replay,
                    model_info=model_info,
                    idempotent_replay=True,
                )

            validation = self._inspect_trusted_checkpoint(
                lease.loader_binding(observation.descriptor, path.name)
            )
            if not validation.get("valid", False):
                raise ModelArtifactPolicyError(
                    f"Trusted checkpoint inspection failed: {validation.get('error', 'unknown error')}"
                )
            if not validation.get("smarttracker_supported", False):
                raise ModelArtifactPolicyError(
                    "SmartTracker supports only detect/obb models; "
                    f"received task={validation.get('task', 'unknown')}"
                )
            observed_after, artifact_stat_after = sha256_descriptor(
                observation.descriptor,
                expected_uid=lease.expected_uid,
                max_bytes=self.max_model_bytes,
            )
            lease.assert_descriptor_binding(path.name, observation.descriptor)
            if observed_after != observation.observed_sha256:
                raise ModelArtifactPolicyError(
                    "Model changed while checkpoint inspection was running"
                )
            provenance = self.provenance.trust_pt_descriptor_locked(
                path,
                descriptor=observation.descriptor,
                sha256=observation.observed_sha256,
                source=source,
                expected_digest_verified=expected is not None,
                publisher_sha256=expected,
                operator_observed_sha256=observation.observed_sha256,
                lease=lease,
                max_bytes=self.max_model_bytes,
            )
            model_info = self._build_model_info(
                path,
                validation,
                provenance,
                lease=lease,
                artifact_stat=artifact_stat_after,
            )
            self.cache[path.stem] = model_info
            self._save_cache()
            return self._registration_result(
                destination=path,
                validation=validation,
                provenance=provenance,
                model_info=model_info,
                idempotent_replay=False,
            )
        except ModelRegistryCorruptionError as exc:
            return {"success": False, "error": str(exc), "status_code": 503}
        except (FileNotFoundError, ModelArtifactPolicyError) as exc:
            return {"success": False, "error": str(exc), "status_code": 422}
        except Exception as exc:
            self.logger.error("Local model registration failed: %s", exc)
            return {"success": False, "error": str(exc), "status_code": 500}

    # ==================== NCNN EXPORT (Refactored from add_model.py) ====================

    @staticmethod
    def _write_all(descriptor: int, payload: bytes) -> None:
        """Write one complete payload to a descriptor."""
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])

    def _copy_verified_model_to_workspace(
        self,
        source_name: str,
        destination: Path,
        expected_sha256: str,
        lease: ModelStoreLease,
    ) -> None:
        """Copy exactly the verified source descriptor into an owner-only workspace."""
        source_descriptor = lease.open_model(source_name)
        destination_descriptor = -1
        try:
            observed, _ = sha256_descriptor(
                source_descriptor,
                expected_uid=lease.expected_uid,
                max_bytes=self.max_model_bytes,
            )
            if observed != expected_sha256:
                raise ModelArtifactPolicyError(
                    "Model changed before NCNN export could start"
                )
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            destination_descriptor = os.open(destination, flags, 0o600)
            while True:
                chunk = os.read(source_descriptor, 1024 * 1024)
                if not chunk:
                    break
                self._write_all(destination_descriptor, chunk)
            os.fsync(destination_descriptor)
            observed_after, _ = sha256_descriptor(
                source_descriptor,
                expected_uid=lease.expected_uid,
                max_bytes=self.max_model_bytes,
            )
            lease.assert_descriptor_binding(source_name, source_descriptor)
            if observed_after != expected_sha256:
                raise ModelArtifactPolicyError(
                    "Model changed while its NCNN workspace copy was created"
                )
        finally:
            if destination_descriptor >= 0:
                os.close(destination_descriptor)
            os.close(source_descriptor)

        if sha256_file(destination, max_bytes=self.max_model_bytes) != expected_sha256:
            raise ModelArtifactPolicyError(
                "NCNN export workspace copy does not match the trusted source"
            )

    @staticmethod
    def _normalize_ncnn_export_result(
        export_result: Any,
        *,
        workspace: Path,
        expected_path: Path,
    ) -> Path:
        """Accept only the exact output location assigned to this export transaction."""
        raw_path = getattr(export_result, "path", export_result)
        if not isinstance(raw_path, (str, Path)) or not str(raw_path).strip():
            raise ModelArtifactPolicyError(
                "Ultralytics did not return an NCNN export path"
            )
        returned = Path(raw_path).expanduser()
        if returned.is_absolute():
            resolved = returned.resolve(strict=False)
        elif returned.parent == Path("."):
            resolved = (workspace / returned).resolve(strict=False)
        else:
            resolved = (Path.cwd() / returned).resolve(strict=False)
        if resolved != expected_path.resolve(strict=False):
            raise ModelArtifactPolicyError(
                "Ultralytics returned an NCNN path outside the dedicated export workspace"
            )
        return expected_path

    @staticmethod
    def _secure_ncnn_export_tree(path: Path, *, expected_uid: int) -> None:
        """Reject links/non-files and normalize an export tree to owner-only modes."""
        if path.is_symlink() or not path.is_dir():
            raise ModelArtifactPolicyError(
                "Ultralytics did not create the expected NCNN export directory"
            )
        stack = [path]
        entry_count = 0
        total_bytes = 0
        while stack:
            root_path = stack.pop()
            root_stat = os.lstat(root_path)
            if not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != expected_uid:
                raise ModelArtifactPolicyError("NCNN export contains an unsafe directory")
            os.chmod(root_path, 0o700)
            with os.scandir(root_path) as entries:
                for entry in entries:
                    entry_count += 1
                    if entry_count > DEFAULT_MAX_EXPORT_FILES:
                        raise ModelArtifactPolicyError(
                            "NCNN export exceeds the file/directory entry limit"
                        )
                    entry_path = Path(entry.path)
                    entry_stat = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(entry_stat.st_mode):
                        if entry_stat.st_uid != expected_uid:
                            raise ModelArtifactPolicyError(
                                "NCNN export contains an unsafe directory"
                            )
                        stack.append(entry_path)
                        continue
                    if (
                        not stat.S_ISREG(entry_stat.st_mode)
                        or entry_stat.st_uid != expected_uid
                        or entry_stat.st_nlink != 1
                    ):
                        raise ModelArtifactPolicyError(
                            "NCNN export contains an unsafe file"
                        )
                    total_bytes += entry_stat.st_size
                    if total_bytes > DEFAULT_MAX_EXPORT_BYTES:
                        raise ModelArtifactPolicyError(
                            "NCNN export exceeds the aggregate byte limit"
                        )
                    os.chmod(entry_path, 0o600)

        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        directory_descriptor = os.open(path, flags)
        try:
            sha256_directory_descriptor(
                directory_descriptor,
                expected_uid=expected_uid,
            )
        finally:
            os.close(directory_descriptor)

    @staticmethod
    def _measure_export_workspace(
        workspace: Path,
        *,
        max_entries: int,
        max_bytes: int,
    ) -> None:
        """Fail as soon as an export workspace exceeds its bounded resource envelope."""
        stack = [workspace]
        entry_count = 0
        total_bytes = 0
        while stack:
            current = stack.pop()
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        entry_stat = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    entry_count += 1
                    if entry_count > max_entries:
                        raise ModelArtifactPolicyError(
                            "NCNN export workspace exceeded its entry quota"
                        )
                    if stat.S_ISDIR(entry_stat.st_mode):
                        stack.append(Path(entry.path))
                    elif stat.S_ISREG(entry_stat.st_mode):
                        total_bytes += entry_stat.st_size
                        if total_bytes > max_bytes:
                            raise ModelArtifactPolicyError(
                                "NCNN export workspace exceeded its byte quota"
                            )
                    else:
                        raise ModelArtifactPolicyError(
                            "NCNN export workspace contains a link or special file"
                        )

    @staticmethod
    def _current_cgroup_v2_directory() -> Path:
        if sys.platform != "linux" or not CGROUP_V2_ROOT.is_dir():
            raise ModelArtifactPolicyError(
                "NCNN export requires a delegated Linux cgroup-v2 boundary"
            )
        try:
            payload = Path("/proc/self/cgroup").read_text(encoding="ascii")
        except (OSError, UnicodeError) as exc:
            raise ModelArtifactPolicyError(
                "NCNN export cannot resolve its current cgroup"
            ) from exc
        if len(payload) > 16 * 1024:
            raise ModelArtifactPolicyError("Current cgroup description is oversized")
        relative = None
        for line in payload.splitlines():
            hierarchy, separator, remainder = line.partition(":")
            controllers, second_separator, path = remainder.partition(":")
            if separator and second_separator and hierarchy == "0" and controllers == "":
                relative = path
                break
        if not relative or not relative.startswith("/"):
            raise ModelArtifactPolicyError(
                "NCNN export requires the unified cgroup-v2 hierarchy"
            )
        try:
            cgroup_root = CGROUP_V2_ROOT.resolve(strict=True)
            current = (cgroup_root / relative.lstrip("/")).resolve(strict=True)
            current.relative_to(cgroup_root)
        except (OSError, ValueError) as exc:
            raise ModelArtifactPolicyError(
                "Current cgroup path is outside the cgroup-v2 hierarchy"
            ) from exc
        return current

    @classmethod
    def _create_export_containment(cls) -> _LinuxCgroupContainment:
        current = cls._current_cgroup_v2_directory()
        current_stat = os.stat(current, follow_symlinks=False)
        expected_uid = os.geteuid()
        if (
            not stat.S_ISDIR(current_stat.st_mode)
            or current_stat.st_uid != expected_uid
            or not os.access(current, os.W_OK)
        ):
            raise ModelArtifactPolicyError(
                "NCNN export needs an owner-controlled delegated cgroup"
            )
        child = current / (
            f"pixeagle-ncnn-{os.getpid()}-{secrets.token_hex(8)}.scope"
        )
        try:
            os.mkdir(child, 0o700)
        except OSError as exc:
            raise ModelArtifactPolicyError(
                "NCNN export could not create a dedicated containment cgroup"
            ) from exc
        containment = _LinuxCgroupContainment(child)
        try:
            for name in ("cgroup.events", "cgroup.kill", "cgroup.procs"):
                control = child / name
                control_stat = os.stat(control, follow_symlinks=False)
                if (
                    not stat.S_ISREG(control_stat.st_mode)
                    or control_stat.st_uid != expected_uid
                ):
                    raise ModelArtifactPolicyError(
                        f"NCNN export cgroup control is unsafe: {name}"
                    )
            if not os.access(child / "cgroup.kill", os.W_OK):
                raise ModelArtifactPolicyError(
                    "NCNN export cgroup cannot terminate all descendants"
                )
            return containment
        except BaseException:
            containment.cleanup()
            raise

    @staticmethod
    def _contained_export_command(command: List[str], ready_fd: int) -> List[str]:
        if not command or ready_fd < 3:
            raise ModelArtifactPolicyError("NCNN export admission command is invalid")
        return [
            sys.executable,
            "-m",
            "classes.ncnn_export_worker",
            "--contain-command",
            "--ready-fd",
            str(ready_fd),
            "--",
            *command,
        ]

    @staticmethod
    def _wait_for_export_admission(
        process: subprocess.Popen,
        ready_fd: int,
    ) -> None:
        ready, _, _ = select.select(
            [ready_fd],
            [],
            [],
            NCNN_EXPORT_ADMISSION_TIMEOUT_SECONDS,
        )
        if not ready or os.read(ready_fd, 32) != b"ready\n":
            raise ModelArtifactPolicyError(
                "NCNN export worker did not stop for cgroup admission"
            )
        deadline = time.monotonic() + NCNN_EXPORT_ADMISSION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                status = Path(f"/proc/{process.pid}/status").read_text(
                    encoding="ascii"
                )
            except (FileNotFoundError, OSError, UnicodeError):
                break
            state_line = next(
                (line for line in status.splitlines() if line.startswith("State:")),
                "",
            )
            if "T" in state_line:
                return
            time.sleep(0.01)
        raise ModelArtifactPolicyError(
            "NCNN export worker admission stop could not be verified"
        )

    @staticmethod
    def _require_export_process_controls() -> None:
        """Fail closed unless required POSIX process controls are available."""
        if (
            os.name != "posix"
            or os.geteuid() == 0
            or not Path("/proc/self/fd").is_dir()
        ):
            raise ModelArtifactPolicyError(
                "NCNN export requires a non-root POSIX runtime, process groups, "
                "procfs, and resource limits"
            )
        try:
            import resource
        except ImportError as exc:
            raise ModelArtifactPolicyError(
                "NCNN export resource controls are unavailable"
            ) from exc
        required = (
            "RLIMIT_AS",
            "RLIMIT_CORE",
            "RLIMIT_CPU",
            "RLIMIT_FSIZE",
            "RLIMIT_NOFILE",
            "RLIMIT_NPROC",
        )
        if any(getattr(resource, name, None) is None for name in required):
            raise ModelArtifactPolicyError(
                "NCNN export cannot establish all required resource limits"
            )
        if not all(hasattr(os, name) for name in ("getpgid", "getsid", "killpg")):
            raise ModelArtifactPolicyError(
                "NCNN export process-group controls are unavailable"
            )
        ModelManager._current_cgroup_v2_directory()

    @staticmethod
    def _live_process_group_members(process_group_id: int) -> List[int]:
        """List non-zombie Linux processes still in the worker process group."""
        members: List[int] = []
        proc_root = Path("/proc")
        if not proc_root.is_dir():
            raise ModelArtifactPolicyError(
                "Cannot verify NCNN export process-group cleanup without procfs"
            )
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / "stat").read_text(encoding="ascii")
                _, separator, suffix = raw.rpartition(") ")
                if not separator:
                    continue
                fields = suffix.split()
                state = fields[0]
                group_id = int(fields[2])
            except (FileNotFoundError, PermissionError, OSError, ValueError, IndexError):
                continue
            if group_id == process_group_id and state not in {"X", "Z"}:
                members.append(int(entry.name))
        return members

    @classmethod
    def _reap_export_process_group(
        cls,
        process: subprocess.Popen,
        process_group_id: int,
    ) -> None:
        """Terminate every live member of the dedicated worker process group."""
        for termination_signal, timeout_seconds in (
            (signal.SIGTERM, 2.0),
            (signal.SIGKILL, 2.0),
        ):
            members = cls._live_process_group_members(process_group_id)
            if not members:
                break
            try:
                os.killpg(process_group_id, termination_signal)
            except ProcessLookupError:
                break
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if not cls._live_process_group_members(process_group_id):
                    break
                time.sleep(0.02)
        if process.poll() is None:
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        remaining = cls._live_process_group_members(process_group_id)
        if remaining:
            raise ModelArtifactPolicyError(
                "NCNN export process group could not be fully terminated"
            )

    def _ncnn_export_worker_command(self, source: Path, result_path: Path) -> List[str]:
        control_path = result_path.parent / ".ncnn-export-controls.json"
        process_limit = self._bounded_export_process_limit()
        return [
            sys.executable,
            "-m",
            "classes.ncnn_export_worker",
            "--source",
            str(source),
            "--result",
            str(result_path),
            "--control-result",
            str(control_path),
            "--cpu-seconds",
            str(max(1, math.ceil(self.ncnn_export_timeout_seconds) + 5)),
            "--address-space-bytes",
            str(NCNN_EXPORT_ADDRESS_SPACE_LIMIT_BYTES),
            "--file-size-bytes",
            str(DEFAULT_MAX_EXPORT_BYTES),
            "--open-files",
            str(NCNN_EXPORT_OPEN_FILES_LIMIT),
            "--processes",
            str(process_limit),
        ]

    @staticmethod
    def _bounded_export_process_limit() -> int:
        """Allow a bounded number of new UID tasks without assuming an idle host."""
        expected_uid = os.geteuid()
        task_count = 0
        try:
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    if entry.stat().st_uid != expected_uid:
                        continue
                    task_count += sum(
                        1
                        for task in (entry / "task").iterdir()
                        if task.name.isdigit()
                    )
                except (FileNotFoundError, PermissionError, OSError):
                    continue
                if task_count > (
                    NCNN_EXPORT_MAX_UID_TASKS - NCNN_EXPORT_ADDITIONAL_PROCESSES
                ):
                    raise ModelArtifactPolicyError(
                        "NCNN export cannot establish a bounded UID process limit"
                    )
        except ModelArtifactPolicyError:
            raise
        except OSError as exc:
            raise ModelArtifactPolicyError(
                "NCNN export cannot count current UID tasks"
            ) from exc
        return task_count + NCNN_EXPORT_ADDITIONAL_PROCESSES

    @staticmethod
    def _minimal_export_environment(workspace: Path) -> Dict[str, str]:
        executable_bin = str(Path(sys.executable).resolve().parent)
        src_root = str(Path(__file__).resolve().parents[1])
        return {
            "CUDA_VISIBLE_DEVICES": "",
            "HOME": str(workspace),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "MPLCONFIGDIR": str(workspace / ".matplotlib"),
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "PATH": os.pathsep.join((executable_bin, "/usr/bin", "/bin")),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": src_root,
            "TMPDIR": str(workspace),
            "YOLO_AUTOINSTALL": "false",
            "YOLO_CONFIG_DIR": str(workspace / ".ultralytics"),
            "YOLO_OFFLINE": "true",
        }

    @staticmethod
    def _read_worker_json(
        path: Path,
        *,
        expected_uid: int,
        max_bytes: int,
        label: str,
    ) -> Dict[str, Any]:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ModelArtifactPolicyError(
                f"NCNN export worker {label} is unavailable"
            ) from exc
        try:
            result_stat = os.fstat(descriptor)
            if (
                not stat.S_ISREG(result_stat.st_mode)
                or result_stat.st_uid != expected_uid
                or result_stat.st_nlink != 1
                or stat.S_IMODE(result_stat.st_mode) != 0o600
                or result_stat.st_size <= 0
                or result_stat.st_size > max_bytes
            ):
                raise ModelArtifactPolicyError(
                    f"NCNN export worker {label} is unsafe or oversized"
                )
            chunks = []
            remaining = result_stat.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            if remaining:
                raise ModelArtifactPolicyError(
                    f"NCNN export worker {label} changed while it was read"
                )
            payload = json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ModelArtifactPolicyError(
                f"NCNN export worker {label} is invalid"
            ) from exc
        finally:
            os.close(descriptor)
        if not isinstance(payload, dict):
            raise ModelArtifactPolicyError(
                f"NCNN export worker {label} is not an object"
            )
        return payload

    def _run_ncnn_export_subprocess(
        self,
        workspace_source: Path,
        expected_path: Path,
    ) -> Any:
        """Run third-party export code with hard limits and descendant containment."""
        workspace = workspace_source.parent
        if (
            expected_path.parent != workspace
            or expected_path.name != f"{workspace_source.stem}_ncnn_model"
            or os.path.lexists(expected_path)
        ):
            raise ModelArtifactPolicyError(
                "NCNN export worker destination is not an unused canonical workspace path"
            )
        result_path = workspace / ".ncnn-export-result.json"
        control_path = workspace / ".ncnn-export-controls.json"
        log_path = workspace / ".ncnn-export.log"
        self._require_export_process_controls()
        env = self._minimal_export_environment(workspace)
        log_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            log_flags |= os.O_NOFOLLOW
        log_descriptor = os.open(log_path, log_flags, 0o600)
        try:
            containment = self._create_export_containment()
        except BaseException:
            os.close(log_descriptor)
            raise
        process: Optional[subprocess.Popen] = None
        process_group_id: Optional[int] = None
        ready_read = -1
        ready_write = -1
        try:
            if hasattr(os, "pipe2"):
                ready_read, ready_write = os.pipe2(getattr(os, "O_CLOEXEC", 0))
            else:
                ready_read, ready_write = os.pipe()
                os.set_inheritable(ready_read, False)
            os.set_inheritable(ready_write, True)
            worker_command = self._ncnn_export_worker_command(
                workspace_source,
                result_path,
            )
            process = subprocess.Popen(
                self._contained_export_command(worker_command, ready_write),
                cwd=workspace,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_descriptor,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
                pass_fds=(ready_write,),
            )
            process_group_id = process.pid
            os.close(ready_write)
            ready_write = -1
            self._wait_for_export_admission(process, ready_read)
            try:
                if (
                    os.getpgid(process.pid) != process.pid
                    or os.getsid(process.pid) != process.pid
                ):
                    raise ModelArtifactPolicyError(
                        "NCNN export worker did not enter its private process group/session"
                    )
            except ProcessLookupError as exc:
                raise ModelArtifactPolicyError(
                    "NCNN export worker exited before process controls were established"
                ) from exc
            containment.admit_process(process.pid)
            os.kill(process.pid, signal.SIGCONT)
        except BaseException:
            cleanup_error: Optional[BaseException] = None
            try:
                containment.cleanup()
            except BaseException as exc:
                cleanup_error = exc
            if process is not None and process_group_id is not None:
                try:
                    self._reap_export_process_group(process, process_group_id)
                except BaseException as exc:
                    cleanup_error = cleanup_error or exc
            if cleanup_error is not None:
                raise cleanup_error
            raise
        finally:
            if ready_read >= 0:
                os.close(ready_read)
                ready_read = -1
            if ready_write >= 0:
                os.close(ready_write)
                ready_write = -1
            os.close(log_descriptor)

        deadline = time.monotonic() + self.ncnn_export_timeout_seconds
        workspace_limit = (
            self.max_model_bytes
            + DEFAULT_MAX_EXPORT_BYTES
            + NCNN_EXPORT_WORKSPACE_OVERHEAD_BYTES
        )
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise ModelArtifactPolicyError(
                        "NCNN export exceeded its configured timeout"
                    )
                self._measure_export_workspace(
                    workspace,
                    max_entries=NCNN_EXPORT_WORKSPACE_MAX_ENTRIES,
                    max_bytes=workspace_limit,
                )
                time.sleep(NCNN_EXPORT_MONITOR_INTERVAL_SECONDS)

            self._measure_export_workspace(
                workspace,
                max_entries=NCNN_EXPORT_WORKSPACE_MAX_ENTRIES,
                max_bytes=workspace_limit,
            )
            if process.returncode != 0:
                self.logger.error(
                    "NCNN export worker exited with status %s; log retained only until cleanup: %s",
                    process.returncode,
                    log_path,
                )
                raise ModelArtifactPolicyError("NCNN export worker failed")

            controls = self._read_worker_json(
                control_path,
                expected_uid=os.geteuid(),
                max_bytes=NCNN_EXPORT_CONTROL_RESULT_MAX_BYTES,
                label="control receipt",
            )
            if (
                controls.get("schema_version") != 1
                or controls.get("pid") != process.pid
                or controls.get("process_group_id") != process.pid
                or controls.get("session_id") != process.pid
                or not isinstance(controls.get("limits"), dict)
                or set(controls["limits"])
                != {
                    "address_space_bytes",
                    "core_bytes",
                    "cpu_seconds",
                    "file_size_bytes",
                    "open_files",
                    "processes",
                }
            ):
                raise ModelArtifactPolicyError(
                    "NCNN export worker control receipt is incomplete"
                )
            expected_limit_ceilings = {
                "address_space_bytes": NCNN_EXPORT_ADDRESS_SPACE_LIMIT_BYTES,
                "core_bytes": 0,
                "cpu_seconds": max(
                    1,
                    math.ceil(self.ncnn_export_timeout_seconds) + 5,
                ),
                "file_size_bytes": DEFAULT_MAX_EXPORT_BYTES,
                "open_files": NCNN_EXPORT_OPEN_FILES_LIMIT,
                "processes": NCNN_EXPORT_MAX_UID_TASKS,
            }
            for limit_name, ceiling in expected_limit_ceilings.items():
                applied = controls["limits"].get(limit_name)
                if not isinstance(applied, dict):
                    raise ModelArtifactPolicyError(
                        "NCNN export worker resource receipt is invalid"
                    )
                soft = applied.get("soft")
                hard = applied.get("hard")
                if (
                    not isinstance(soft, int)
                    or isinstance(soft, bool)
                    or soft != hard
                    or soft < 0
                    or soft > ceiling
                    or (limit_name != "core_bytes" and soft == 0)
                ):
                    raise ModelArtifactPolicyError(
                        "NCNN export worker resource controls were not established"
                    )
            payload = self._read_worker_json(
                result_path,
                expected_uid=os.geteuid(),
                max_bytes=NCNN_EXPORT_RESULT_MAX_BYTES,
                label="result",
            )
            if not isinstance(payload, dict) or not payload.get("returned_path"):
                raise ModelArtifactPolicyError("NCNN export worker returned no output path")
            return payload["returned_path"]
        finally:
            cleanup_error: Optional[BaseException] = None
            try:
                containment.cleanup()
            except BaseException as exc:
                cleanup_error = exc
            if process is not None and process_group_id is not None:
                try:
                    self._reap_export_process_group(process, process_group_id)
                except BaseException as exc:
                    cleanup_error = cleanup_error or exc
            if cleanup_error is not None:
                raise cleanup_error

    def export_to_ncnn(self, pt_file: Path) -> Dict[str, Any]:
        """Export one trusted checkpoint as an atomic model-store transaction."""
        start_time = time.monotonic()
        workspace: Optional[Path] = None
        published_path: Optional[Path] = None
        try:
            if not ULTRALYTICS_AVAILABLE:
                raise ModelArtifactPolicyError("Ultralytics is not installed")
            if not self._pnnx_available():
                raise ModelArtifactPolicyError(
                    "NCNN export requires 'pnnx' in the active PixEagle environment"
                )

            with self._model_mutation_lock() as lease:
                trusted_pt = resolve_model_path(self.models_folder, Path(pt_file).name)
                candidate = Path(pt_file).expanduser()
                if not candidate.is_absolute():
                    candidate = Path.cwd() / candidate
                if trusted_pt != candidate:
                    raise ModelArtifactPolicyError(
                        "NCNN export refuses lexical aliases of the trusted models folder"
                    )
                source_record = self.provenance.verify_pt_locked(
                    trusted_pt,
                    lease,
                    max_bytes=self.max_model_bytes,
                )
                self._require_execution_provenance(
                    source_record,
                    operation="NCNN export",
                )
                destination = self._get_ncnn_path(trusted_pt)
                if os.path.lexists(destination):
                    try:
                        provenance = self.provenance.verify_ncnn_locked(
                            destination,
                            lease,
                            max_source_bytes=self.max_model_bytes,
                        )
                    except ModelRegistryCorruptionError:
                        raise
                    except ModelArtifactPolicyError as exc:
                        raise FileExistsError(
                            f"NCNN export already exists for model '{trusted_pt.stem}' "
                            "but is not the verified prior export"
                        ) from exc
                    return {
                        "success": True,
                        "ncnn_path": str(destination),
                        "artifact_sha256": provenance["sha256"],
                        "source_pt_sha256": provenance["source_pt_sha256"],
                        "file_count": provenance["file_count"],
                        "size_bytes": provenance["size_bytes"],
                        "manifest_schema_version": provenance[
                            "manifest_schema_version"
                        ],
                        "export_receipt": provenance.get("export_receipt"),
                        "export_action_id": (
                            (provenance.get("export_receipt") or {}).get("action_id")
                        ),
                        "export_time": time.monotonic() - start_time,
                        "idempotent_replay": True,
                    }

                workspace = Path(
                    tempfile.mkdtemp(
                        prefix=f".ncnn-export-{trusted_pt.stem}-",
                        dir=str(self.models_folder),
                    )
                )
                os.chmod(workspace, 0o700)
                workspace_source = workspace / trusted_pt.name
                self._copy_verified_model_to_workspace(
                    trusted_pt.name,
                    workspace_source,
                    source_record["sha256"],
                    lease,
                )
                expected_workspace_export = workspace / destination.name

                self.logger.info("Exporting trusted model %s to NCNN", trusted_pt.name)
                export_result = self._run_ncnn_export_subprocess(
                    workspace_source,
                    expected_workspace_export,
                )

                workspace_export = self._normalize_ncnn_export_result(
                    export_result,
                    workspace=workspace,
                    expected_path=expected_workspace_export,
                )
                self._secure_ncnn_export_tree(
                    workspace_export,
                    expected_uid=lease.expected_uid,
                )
                if os.path.lexists(destination):
                    raise FileExistsError(
                        f"NCNN export appeared concurrently for model '{trusted_pt.stem}'"
                    )
                os.rename(workspace_export, destination)
                published_path = destination
                try:
                    provenance = self.provenance.trust_ncnn_locked(
                        trusted_pt,
                        destination,
                        lease,
                        max_source_bytes=self.max_model_bytes,
                    )
                except Exception:
                    shutil.rmtree(lease.bound_path(destination.name), ignore_errors=True)
                    published_path = None
                    raise

                export_time = time.monotonic() - start_time
                self.logger.info(
                    "NCNN export committed in %.2fs at %s",
                    export_time,
                    destination,
                )
                return {
                    "success": True,
                    "ncnn_path": str(destination),
                    "artifact_sha256": provenance["sha256"],
                    "source_pt_sha256": provenance["source_pt_sha256"],
                    "file_count": provenance["file_count"],
                    "size_bytes": provenance["size_bytes"],
                    "manifest_schema_version": provenance[
                        "manifest_schema_version"
                    ],
                    "export_receipt": provenance.get("export_receipt"),
                    "export_action_id": (
                        (provenance.get("export_receipt") or {}).get("action_id")
                    ),
                    "export_time": export_time,
                    "idempotent_replay": False,
                }
        except FileExistsError as exc:
            self.logger.warning("NCNN export refused: %s", exc)
            return {"success": False, "error": str(exc), "status_code": 409}
        except ModelRegistryCorruptionError as exc:
            self.logger.error("NCNN export provenance unavailable: %s", exc)
            return {"success": False, "error": str(exc), "status_code": 503}
        except ModelStoreBusyError as exc:
            self.logger.warning("NCNN export store busy: %s", exc)
            return {"success": False, "error": str(exc), "status_code": 409}
        except ModelArtifactPolicyError as exc:
            self.logger.warning("NCNN export rejected: %s", exc)
            return {"success": False, "error": str(exc), "status_code": 422}
        except Exception as exc:
            self.logger.error("NCNN export failed: %s", exc)
            return {"success": False, "error": str(exc), "status_code": 500}
        finally:
            if workspace is not None:
                shutil.rmtree(workspace, ignore_errors=True)
            if published_path is not None and not published_path.exists():
                self.logger.error("Committed NCNN path disappeared before export returned")

    async def _export_async(self, pt_file: Path) -> Dict:
        """Async wrapper for NCNN export (non-blocking for API calls)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.export_to_ncnn, pt_file)

    # ==================== MODEL DELETION ====================

    def delete_model(self, model_id: str, delete_ncnn: bool = True) -> Dict:
        """
        Delete model and optionally its NCNN export

        Args:
            model_id: Model identifier
            delete_ncnn: Also delete NCNN folder

        Returns:
            {"success": bool, "deleted_files": List[str], "error": Optional[str]}
        """
        try:
            with self._model_mutation_lock() as lease:
                return self._delete_model_locked(
                    model_id,
                    delete_ncnn=delete_ncnn,
                    lease=lease,
                )
        except ModelStoreBusyError as exc:
            return {"success": False, "error": str(exc), "status_code": 409}

    def _delete_model_locked(
        self,
        model_id: str,
        delete_ncnn: bool = True,
        *,
        lease: ModelStoreLease,
    ) -> Dict:
        try:
            if str(model_id).endswith(".pt"):
                raise ModelArtifactPolicyError("Model ID must not include the .pt suffix")
            safe_filename = validate_model_filename(f"{model_id}.pt")
            safe_model_id = Path(safe_filename).stem
            deleted = []

            pt_file = resolve_model_path(self.models_folder, safe_filename)
            ncnn_folder = self.models_folder / f"{safe_model_id}_ncnn_model"
            if ncnn_folder.is_symlink():
                raise ModelArtifactPolicyError("Refusing to delete a symlinked NCNN export")
            if ncnn_folder.resolve(strict=False).parent != self.models_folder:
                raise ModelArtifactPolicyError("NCNN export path escapes models/")

            # Remove trust first. If filesystem cleanup fails, the artifact remains
            # fail-closed rather than executable with stale provenance.
            self.provenance.remove_locked(safe_filename, lease)
            if pt_file.exists():
                os.unlink(safe_filename, dir_fd=lease.root_fd)
                deleted.append(str(pt_file))

            if delete_ncnn:
                if ncnn_folder.exists():
                    shutil.rmtree(lease.bound_path(ncnn_folder.name))
                    deleted.append(str(ncnn_folder))

            if safe_model_id in self.cache:
                del self.cache[safe_model_id]
                self._save_cache()

            self.logger.info(
                "Deleted model '%s': %s",
                safe_model_id,
                ", ".join(deleted),
            )

            return {
                "success": True,
                "deleted_files": deleted
            }

        except Exception as e:
            self.logger.error(f"Delete failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "status_code": (
                    503
                    if isinstance(e, ModelRegistryCorruptionError)
                    else 422
                    if isinstance(e, ModelArtifactPolicyError)
                    else 500
                ),
            }

    # ==================== METADATA CACHE ====================

    def _load_cache(self) -> Dict:
        """Load disposable metadata only from a bounded owner-only regular file."""
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = -1
        try:
            descriptor = os.open(self.metadata_file, flags)
            cache_stat = os.fstat(descriptor)
            expected_uid = getattr(os, "geteuid", lambda: cache_stat.st_uid)()
            if (
                not stat.S_ISREG(cache_stat.st_mode)
                or cache_stat.st_uid != expected_uid
                or cache_stat.st_nlink != 1
                or stat.S_IMODE(cache_stat.st_mode) != 0o600
                or cache_stat.st_size > MODEL_CACHE_MAX_BYTES
            ):
                raise ModelArtifactPolicyError(
                    "Model metadata cache is not an owner-only bounded regular file"
                )
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                descriptor = -1
                payload = json.load(stream)
            if not isinstance(payload, dict):
                raise ModelArtifactPolicyError("Model metadata cache must be a JSON object")
            return payload
        except FileNotFoundError:
            pass
        except Exception as exc:
            self.logger.warning("Ignoring unsafe or invalid model metadata cache: %s", exc)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        return {}

    def _save_cache(self):
        """Atomically save disposable model metadata without weakening provenance."""
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".models-cache-",
            suffix=".tmp",
            dir=str(self.models_folder),
        )
        temporary_path = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                descriptor = -1
                json.dump(self.cache, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.metadata_file)
        except Exception as e:
            self.logger.error(f"Failed to save metadata cache: {e}")
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)
