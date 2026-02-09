# src/classes/yolo_model_manager.py

"""
YOLOModelManager - Clean, single class for all YOLO model operations

Handles:
- Model discovery (scan yolo/ folder)
- Validation (check .pt files, extract metadata, detect custom models)
- Upload handling (save, validate, auto-export)
- NCNN export (refactored from add_yolo_model.py)
- Model deletion
- Metadata caching

Project: PixEagle
Author: Alireza Ghaderi
Repository: https://github.com/alireza787b/PixEagle
"""

import os
import sys
import json
import time
import shutil
import logging
import asyncio
import requests
import re
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from datetime import datetime

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


class YOLOModelManager:
    """
    Centralized manager for YOLO model operations.

    Features:
    - Auto-discovery of models in yolo/ folder
    - Validation with custom model detection
    - Upload handling with auto-NCNN export
    - Model switching support
    - Metadata caching for performance
    """

    def __init__(self, yolo_folder: str = "yolo"):
        """
        Initialize YOLO Model Manager

        Args:
            yolo_folder: Path to folder containing YOLO models (default: "yolo")
        """
        self.yolo_folder = Path(yolo_folder)
        self.yolo_folder.mkdir(exist_ok=True)

        # Metadata cache file
        self.metadata_file = self.yolo_folder / ".models.json"

        # Logging
        self.logger = logging.getLogger(__name__)

        # Load cached metadata
        self.cache = self._load_cache()

        # Monkey-patch torch.load for PyTorch 2.6+ compatibility
        # (Required for loading YOLO checkpoints - same as add_yolo_model.py)
        self._patch_torch_load()

        self.logger.info(f"YOLOModelManager initialized (folder: {self.yolo_folder})")

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
                    "name": "YOLO11n",
                    "path": "yolo/yolo11n.pt",
                    "type": "gpu",  # gpu | cpu
                    "format": "pt",  # pt | ncnn
                    "size_mb": 5.35,
                    "num_classes": 80,
                    "class_names": ["person", "car", ...],
                    "is_custom": False,
                    "has_ncnn": True,
                    "ncnn_path": "yolo/yolo11n_ncnn_model",
                    "last_modified": 1234567890.0
                }
            }
        """
        models = {}

        try:
            # Scan for .pt files
            pt_files = list(self.yolo_folder.glob("*.pt"))

            for pt_file in pt_files:
                model_id = pt_file.stem

                # Use cached metadata if available and file not modified
                cached = self.cache.get(model_id)
                file_mtime = pt_file.stat().st_mtime

                if cached and not force_rescan:
                    if cached.get('last_modified') == file_mtime:
                        models[model_id] = cached
                        continue

                # Validate and extract metadata
                validation_result = self.validate_model(pt_file)

                if validation_result['valid']:
                    model_info = {
                        "name": self._generate_display_name(model_id, validation_result),
                        "path": str(pt_file),
                        "type": "gpu",  # .pt files are GPU-compatible
                        "format": "pt",
                        "size_mb": round(pt_file.stat().st_size / (1024 * 1024), 2),
                        "num_classes": validation_result.get('num_classes', 0),
                        "class_names": validation_result.get('class_names', []),
                        "is_custom": validation_result.get('is_custom', False),
                        "task": validation_result.get('task', 'unknown'),
                        "output_geometry": validation_result.get('output_geometry', 'aabb'),
                        "smarttracker_supported": validation_result.get('smarttracker_supported', True),
                        "compatibility_notes": validation_result.get('compatibility_notes', []),
                        "has_ncnn": self._check_ncnn_exists(pt_file),
                        "ncnn_path": str(self._get_ncnn_path(pt_file)) if self._check_ncnn_exists(pt_file) else None,
                        "last_modified": file_mtime,
                        "metadata": validation_result
                    }
                    models[model_id] = model_info
                else:
                    self.logger.warning(f"Skipping invalid model: {pt_file} ({validation_result.get('error')})")

            # Update cache
            self.cache = models
            self._save_cache()

            self.logger.info(f"Discovered {len(models)} model(s)")

        except Exception as e:
            self.logger.error(f"Error during model discovery: {e}")

        return models

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

    def _check_ncnn_exists(self, pt_file: Path) -> bool:
        """Check if NCNN export exists for this .pt file"""
        ncnn_folder = self._get_ncnn_path(pt_file)
        return self._verify_ncnn_files(ncnn_folder)
    
    def _verify_ncnn_files(self, ncnn_folder: Path) -> bool:
        """Verify that NCNN folder contains required files"""
        if not ncnn_folder or not ncnn_folder.exists() or not ncnn_folder.is_dir():
            return False

        # Check for required files with various possible names
        # Standard names: model.bin and model.param
        # Alternative: might be named after the model (e.g., yolo11n.bin, yolo11n.param)
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
    def _restore_env_var(name: str, value: Optional[str]) -> None:
        """Restore an environment variable to a previous value (or unset it)."""
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    @contextmanager
    def _preserve_env_vars(self, names: List[str]):
        """Preserve process env vars around code that mutates global runtime state."""
        snapshot = {name: os.environ.get(name) for name in names}
        try:
            yield
        finally:
            for name, value in snapshot.items():
                self._restore_env_var(name, value)

    @staticmethod
    def _pnnx_available() -> bool:
        """Check whether pnnx is import-discoverable."""
        return importlib.util.find_spec("pnnx") is not None

    # ==================== MODEL VALIDATION ====================

    def validate_model(self, pt_file: Path) -> Dict:
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
        try:
            if not ULTRALYTICS_AVAILABLE:
                return {
                    "valid": False,
                    "error": "Ultralytics not installed"
                }

            # Load model (minimal validation)
            model = YOLO(str(pt_file))

            # Extract basic metadata
            num_classes = len(model.names) if hasattr(model, 'names') else 0
            class_names = list(model.names.values()) if hasattr(model, 'names') else []
            task = getattr(model, 'task', 'unknown')

            # Detect custom models (non-COCO)
            is_custom = self._is_custom_model(class_names, num_classes)

            # Detect model type
            model_type = self._detect_model_type(pt_file.stem)

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
            self.logger.error(f"Model validation failed for {pt_file}: {e}")
            return {
                "valid": False,
                "error": str(e)
            }

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

    async def upload_model(self, file_data: bytes, filename: str, auto_export_ncnn: bool = True) -> Dict:
        """
        Handle model file upload from web UI

        Args:
            file_data: Raw file bytes
            filename: Original filename
            auto_export_ncnn: Automatically export to NCNN after upload

        Returns:
            {
                "success": bool,
                "model_id": str,
                "model_path": str,
                "validation": Dict,
                "ncnn_export": Optional[Dict],
                "error": Optional[str]
            }
        """
        try:
            # Validate filename
            if not filename.endswith('.pt'):
                return {
                    "success": False,
                    "error": "Only .pt files are supported"
                }

            # Get model ID
            model_id = Path(filename).stem
            model_path = self.yolo_folder / filename

            # Check if file already exists
            if model_path.exists():
                return {
                    "success": False,
                    "error": f"Model '{model_id}' already exists. Delete it first or rename your file."
                }

            # Write file
            with open(model_path, 'wb') as f:
                f.write(file_data)

            file_size_mb = len(file_data) / (1024 * 1024)
            self.logger.info(f"Model uploaded: {model_path} ({file_size_mb:.2f} MB)")

            # Validate uploaded model
            validation_result = self.validate_model(model_path)

            if not validation_result['valid']:
                # Delete invalid file
                model_path.unlink()
                return {
                    "success": False,
                    "error": f"Invalid model file: {validation_result.get('error')}"
                }

            # Log custom model info
            if validation_result['is_custom']:
                self.logger.info(f"✨ Custom model detected: {validation_result['num_classes']} classes")
                self.logger.info(f"   Classes: {', '.join(validation_result['class_names'][:10])}...")

            result = {
                "success": True,
                "model_id": model_id,
                "model_path": str(model_path),
                "validation": validation_result,
                "model_info": None,
                "ncnn_exported": False,
                "ncnn_export": None,
            }

            # Auto-export to NCNN if requested
            if auto_export_ncnn:
                self.logger.info(f"Starting automatic NCNN export for {model_id}...")
                export_result = await self._export_async(model_path)
                result["ncnn_export"] = export_result
                result["ncnn_exported"] = bool(export_result.get('success'))

                if export_result['success']:
                    self.logger.info(f"✅ NCNN export completed: {export_result['ncnn_path']}")
                else:
                    self.logger.warning(f"⚠️ NCNN export failed: {export_result.get('error')}")

            # Refresh model discovery
            discovered_models = self.discover_models(force_rescan=True)
            model_info = discovered_models.get(model_id)

            # Backward-compatible info if discovery cache misses unexpectedly.
            if not model_info:
                model_info = {
                    "name": self._generate_display_name(model_id, validation_result),
                    "path": str(model_path),
                    "type": "gpu",
                    "format": "pt",
                    "size_mb": round(model_path.stat().st_size / (1024 * 1024), 2),
                    "num_classes": validation_result.get('num_classes', 0),
                    "class_names": validation_result.get('class_names', []),
                    "is_custom": validation_result.get('is_custom', False),
                    "task": validation_result.get('task', 'unknown'),
                    "output_geometry": validation_result.get('output_geometry', 'aabb'),
                    "smarttracker_supported": validation_result.get('smarttracker_supported', True),
                    "compatibility_notes": validation_result.get('compatibility_notes', []),
                    "has_ncnn": self._check_ncnn_exists(model_path),
                    "ncnn_path": str(self._get_ncnn_path(model_path)) if self._check_ncnn_exists(model_path) else None,
                }

            result["model_info"] = model_info
            result["ncnn_exported"] = bool(result["ncnn_exported"] or model_info.get("has_ncnn"))
            result["ncnn_path"] = (
                (result.get("ncnn_export") or {}).get("ncnn_path")
                or model_info.get("ncnn_path")
            )
            result["message"] = (
                f"Model '{model_id}' uploaded successfully"
                + (" with NCNN export." if result["ncnn_exported"] else ".")
            )

            return result

        except Exception as e:
            self.logger.error(f"Upload failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # ==================== NCNN EXPORT (Refactored from add_yolo_model.py) ====================

    def export_to_ncnn(self, pt_file: Path) -> Dict:
        """
        Export YOLO model to NCNN format
        (Refactored from add_yolo_model.py export_model_to_ncnn function)

        Args:
            pt_file: Path to .pt file

        Returns:
            {
                "success": bool,
                "ncnn_path": str,
                "export_time": float,
                "error": Optional[str]
            }
        """
        start_time = time.time()

        try:
            if not ULTRALYTICS_AVAILABLE:
                return {
                    "success": False,
                    "error": "Ultralytics not installed"
                }

            if not self._pnnx_available():
                return {
                    "success": False,
                    "error": (
                        "NCNN export requires 'pnnx', but it is not installed in the active venv. "
                        "Run: source venv/bin/activate && pip install --prefer-binary pnnx"
                    ),
                }

            self.logger.info(f"Exporting {pt_file.name} to NCNN format...")

            # Ultralytics export(format="ncnn") internally calls select_device("cpu"),
            # which mutates CUDA_VISIBLE_DEVICES globally. Preserve and restore it so
            # SmartTracker GPU runtime remains unaffected after upload/export.
            with self._preserve_env_vars(["CUDA_VISIBLE_DEVICES"]):
                # Load model (torch.load is already patched in __init__)
                model = YOLO(str(pt_file))

                # Export to NCNN - returns the path to exported model
                export_result = model.export(format="ncnn")
            
            # Small delay to ensure files are fully written
            time.sleep(0.5)

            # The export_result can be a string path or Path object
            # Ultralytics exports to a folder relative to the model file location
            # Try multiple possible locations
            possible_ncnn_paths = []
            
            # 1. Use the path returned by export (if it's a path)
            if export_result:
                if isinstance(export_result, (str, Path)):
                    export_path = Path(export_result)
                    # Resolve relative paths
                    if not export_path.is_absolute():
                        # Try relative to model file location
                        possible_ncnn_paths.append(pt_file.parent / export_path)
                        # Try relative to current working directory
                        possible_ncnn_paths.append(Path.cwd() / export_path)
                        # Try as-is (might be relative to yolo folder)
                        possible_ncnn_paths.append(self.yolo_folder / export_path)
                    else:
                        possible_ncnn_paths.append(export_path)
                elif hasattr(export_result, 'path'):
                    export_path = Path(export_result.path)
                    if not export_path.is_absolute():
                        possible_ncnn_paths.append(pt_file.parent / export_path)
                        possible_ncnn_paths.append(Path.cwd() / export_path)
                        possible_ncnn_paths.append(self.yolo_folder / export_path)
                    else:
                        possible_ncnn_paths.append(export_path)
            
            # 2. Expected location: same directory as .pt file
            expected_ncnn_folder = self._get_ncnn_path(pt_file)
            possible_ncnn_paths.append(expected_ncnn_folder)
            
            # 3. Check if export saved relative to current working directory
            model_stem = pt_file.stem
            possible_ncnn_paths.append(Path(f"{model_stem}_ncnn_model"))
            possible_ncnn_paths.append(Path.cwd() / f"{model_stem}_ncnn_model")
            
            # 4. Check in the yolo folder (if pt_file is elsewhere)
            if pt_file.parent != self.yolo_folder:
                possible_ncnn_paths.append(self.yolo_folder / f"{model_stem}_ncnn_model")
            
            # Find the actual NCNN export location
            ncnn_folder = None
            for path in possible_ncnn_paths:
                if path and path.exists() and path.is_dir():
                    # Verify it has the required files
                    if self._verify_ncnn_files(path):
                        ncnn_folder = path
                        break
            
            # If found, verify it's in the right location and move if needed
            if ncnn_folder and ncnn_folder != expected_ncnn_folder:
                # Export was saved to a different location - move it to expected location
                if not expected_ncnn_folder.exists():
                    try:
                        shutil.move(str(ncnn_folder), str(expected_ncnn_folder))
                        ncnn_folder = expected_ncnn_folder
                        self.logger.info(f"Moved NCNN export to expected location: {expected_ncnn_folder}")
                    except Exception as e:
                        self.logger.warning(f"Could not move NCNN export: {e}, using original location")
            
            # Final verification
            if ncnn_folder and self._verify_ncnn_files(ncnn_folder):
                export_time = time.time() - start_time
                self.logger.info(f"✅ NCNN export successful ({export_time:.2f}s) at {ncnn_folder}")

                return {
                    "success": True,
                    "ncnn_path": str(ncnn_folder),
                    "export_time": export_time
                }
            else:
                # Log what we found for debugging
                self.logger.warning(f"NCNN export verification failed. Checked paths: {possible_ncnn_paths}")
                
                # Check if any of the paths exist but don't have the right files
                for path in possible_ncnn_paths:
                    if path and path.exists() and path.is_dir():
                        files_in_dir = list(path.iterdir())
                        self.logger.warning(f"Found directory {path} with files: {[f.name for f in files_in_dir]}")
                
                return {
                    "success": False,
                    "error": f"NCNN folder not found after export. Export may have succeeded but files not in expected location. Checked: {[str(p) for p in possible_ncnn_paths if p]}"
                }

        except Exception as e:
            self.logger.error(f"NCNN export failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _export_async(self, pt_file: Path) -> Dict:
        """Async wrapper for NCNN export (non-blocking for API calls)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.export_to_ncnn, pt_file)

    # ==================== MODEL DOWNLOAD (Refactored from add_yolo_model.py) ====================

    def download_model(self, model_name: str, download_url: Optional[str] = None) -> Dict:
        """
        Download YOLO model with robust fallback chain:
        1. Use provided URL if available
        2. Try automatic download via Ultralytics (YOLOv5, YOLO8, YOLO11)
        3. Try known GitHub release URLs
        4. Return suggested URLs if all automatic methods fail

        Args:
            model_name: Model filename (e.g., "yolo11n.pt")
            download_url: Optional custom URL (takes priority if provided)

        Returns:
            {
                "success": bool,
                "path": str,
                "error": Optional[str],
                "suggested_urls": Optional[List[str]]  # URLs to try if auto-download fails
            }
        """
        destination = self.yolo_folder / model_name

        # Check if model already exists locally
        if destination.exists():
            return {
                "success": True,
                "path": str(destination),
                "message": "Model already exists locally"
            }

        try:
            # Priority 1: Use provided URL if available
            if download_url:
                self.logger.info(f"Using provided URL: {download_url}")
                result = self._download_from_url(download_url, destination)
                if result['success']:
                    return result
                # If URL download fails, continue to fallback methods

            # Priority 2: Try automatic download methods
            model_name_lower = model_name.lower()
            
            # For YOLOv5: use torch.hub
            if model_name_lower.startswith("yolov5"):
                result = self._download_from_ultralytics(model_name, destination)
                if result['success']:
                    return result

            # For YOLO8/YOLO11 and future versions: use Ultralytics YOLO class (auto-downloads)
            # This handles yolo8, yolo11, yolo12, yolo13, etc. (future-proof)
            # Check for known YOLO versions first
            known_yolo_patterns = [
                'yolo8', 'yolo-8', 'yolov8', 'yolo-v8',
                'yolo11', 'yolo-11',
            ]
            
            if any(prefix in model_name_lower for prefix in known_yolo_patterns):
                result = self._download_via_yolo_class(model_name, destination)
                if result['success']:
                    return result
            
            # Future-proof: Try YOLO class for any model matching "yolo[number]" pattern
            # This will catch yolo12, yolo13, yolo16, etc. automatically
            if re.match(r'^yolo-?\d+', model_name_lower) and not model_name_lower.startswith('yolov5'):
                result = self._download_via_yolo_class(model_name, destination)
                if result['success']:
                    return result

            # Priority 3: Try known GitHub release URLs
            result = self._download_from_known_urls(model_name, destination)
            if result['success']:
                return result

            # All automatic methods failed - return suggested URLs
            suggested_urls = self._get_suggested_urls(model_name)
            return {
                "success": False,
                "error": "Automatic download failed. Please provide a download URL.",
                "suggested_urls": suggested_urls
            }

        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            suggested_urls = self._get_suggested_urls(model_name)
            return {
                "success": False,
                "error": str(e),
                "suggested_urls": suggested_urls
            }

    def _download_from_url(self, url: str, destination: Path) -> Dict:
        """Download model from URL (refactored from add_yolo_model.py)"""
        try:
            self.logger.info(f"Downloading model from {url}...")

            response = requests.get(url, stream=True)
            if response.status_code == 200:
                with open(destination, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)

                self.logger.info(f"✅ Download successful: {destination}")
                return {
                    "success": True,
                    "path": str(destination)
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _download_from_ultralytics(self, model_name: str, destination: Path) -> Dict:
        """Download YOLOv5 model from Ultralytics hub (refactored from add_yolo_model.py)"""
        if not TORCH_AVAILABLE:
            return {
                "success": False,
                "error": "PyTorch not installed - cannot download from Ultralytics hub"
            }

        try:
            self.logger.info(f"Downloading {model_name} from Ultralytics hub...")

            model_type = os.path.splitext(model_name)[0]  # e.g., "yolov5s"
            _ = torch.hub.load('ultralytics/yolov5', model_type, pretrained=True)

            # Find cached model
            hub_dir = torch.hub.get_dir()
            cached_model_path = os.path.join(hub_dir, 'ultralytics_yolov5_master', model_name)

            if os.path.exists(cached_model_path):
                shutil.copy(cached_model_path, destination)
                self.logger.info(f"✅ Model downloaded: {destination}")
                return {
                    "success": True,
                    "path": str(destination)
                }
            else:
                return {
                    "success": False,
                    "error": f"Cached model not found at {cached_model_path}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _download_via_yolo_class(self, model_name: str, destination: Path) -> Dict:
        """
        Download YOLO8/YOLO11 model via Ultralytics YOLO class (auto-downloads)
        The YOLO() class automatically downloads models from Ultralytics hub
        """
        if not ULTRALYTICS_AVAILABLE:
            return {
                "success": False,
                "error": "Ultralytics not installed"
            }

        try:
            self.logger.info(f"Downloading {model_name} via Ultralytics YOLO class...")
            
            # Remove .pt extension for model name (YOLO class expects "yolo11n", not "yolo11n.pt")
            model_id = os.path.splitext(model_name)[0]
            
            # YOLO class will auto-download if model not in cache
            model = YOLO(model_id)
            
            # Try multiple methods to find the downloaded model file
            possible_paths = []
            
            # Method 1: Check model.ckpt_path (most reliable)
            if hasattr(model, 'ckpt_path') and model.ckpt_path:
                possible_paths.append(Path(model.ckpt_path))
            
            # Method 2: Check model.weights attribute
            if hasattr(model, 'weights') and model.weights:
                if isinstance(model.weights, str):
                    possible_paths.append(Path(model.weights))
                elif isinstance(model.weights, Path):
                    possible_paths.append(model.weights)
            
            # Method 3: Check Ultralytics cache directories
            try:
                from ultralytics.utils import SETTINGS
                weights_dir = Path(SETTINGS.get('weights_dir', Path.home() / '.ultralytics' / 'weights'))
                possible_paths.append(weights_dir / model_name)
            except:
                pass
            
            # Method 4: Common cache locations
            possible_paths.extend([
                Path.home() / '.ultralytics' / 'weights' / model_name,
                Path.home() / '.cache' / 'ultralytics' / model_name,
                Path.home() / '.cache' / 'torch' / 'hub' / 'checkpoints' / model_name,
            ])
            
            # Method 5: Check if model was downloaded to current directory
            possible_paths.append(Path(model_name))
            
            # Try to find and copy the model
            for cache_path in possible_paths:
                if cache_path and cache_path.exists() and cache_path.is_file():
                    try:
                        shutil.copy(cache_path, destination)
                        self.logger.info(f"✅ Model downloaded from {cache_path} to {destination}")
                        return {
                            "success": True,
                            "path": str(destination)
                        }
                    except Exception as e:
                        self.logger.debug(f"Failed to copy from {cache_path}: {e}")
                        continue
            
            # If model was loaded but file not found, try to get it from model's internal state
            # Some YOLO versions store the path differently
            if hasattr(model, 'model') and hasattr(model.model, 'yaml_file'):
                yaml_dir = Path(model.model.yaml_file).parent if model.model.yaml_file else None
                if yaml_dir:
                    possible_paths.append(yaml_dir / model_name)
                    if (yaml_dir / model_name).exists():
                        shutil.copy(yaml_dir / model_name, destination)
                        return {
                            "success": True,
                            "path": str(destination)
                        }
            
            return {
                "success": False,
                "error": f"Model loaded but file not found in expected cache locations. Model may be in-memory only."
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _download_from_known_urls(self, model_name: str, destination: Path) -> Dict:
        """
        Try downloading from known GitHub release URLs for common YOLO models
        """
        known_urls = self._get_suggested_urls(model_name)
        
        for url in known_urls:
            self.logger.info(f"Trying known URL: {url}")
            result = self._download_from_url(url, destination)
            if result['success']:
                return result
        
        return {
            "success": False,
            "error": "All known URLs failed"
        }

    def _get_suggested_urls(self, model_name: str) -> List[str]:
        """
        Generate suggested download URLs for common YOLO models
        Returns list of URLs user can try (future-proof for new YOLO versions)
        """
        model_name_lower = model_name.lower()
        suggested = []
        model_id = os.path.splitext(model_name)[0]  # e.g., "yolo11n"
        
        # Extract YOLO version number if possible (for future versions)
        version_match = re.search(r'yolo-?(\d+)', model_name_lower)
        version_num = int(version_match.group(1)) if version_match else None
        
        # YOLO11 models (latest stable)
        if 'yolo11' in model_name_lower or 'yolo-11' in model_name_lower:
            suggested.extend([
                f"https://github.com/ultralytics/assets/releases/download/v8.3.0/{model_name}",
                f"https://github.com/ultralytics/ultralytics/releases/download/v8.3.0/{model_name}",
                f"https://github.com/ultralytics/assets/releases/download/v0.0.0/{model_name}",
            ])
        
        # YOLO8 models
        elif 'yolo8' in model_name_lower or 'yolov8' in model_name_lower or 'yolo-8' in model_name_lower:
            suggested.extend([
                f"https://github.com/ultralytics/assets/releases/download/v8.2.0/{model_name}",
                f"https://github.com/ultralytics/ultralytics/releases/download/v8.2.0/{model_name}",
                f"https://github.com/ultralytics/assets/releases/download/v0.0.0/{model_name}",
            ])
        
        # YOLOv5 models
        elif 'yolov5' in model_name_lower or 'yolo5' in model_name_lower:
            suggested.extend([
                f"https://github.com/ultralytics/yolov5/releases/download/v7.0/{model_name}",
                f"https://github.com/ultralytics/yolov5/releases/download/v6.2/{model_name}",
                f"https://github.com/ultralytics/yolov5/releases/download/v7.1/{model_name}",
            ])
        
        # Future YOLO versions (yolo12, yolo13, etc.) - generic pattern
        elif version_num and version_num >= 12:
            # For future versions, try latest assets and ultralytics releases
            suggested.extend([
                f"https://github.com/ultralytics/assets/releases/download/v0.0.0/{model_name}",
                f"https://github.com/ultralytics/ultralytics/releases/download/v0.0.0/{model_name}",
                f"https://github.com/ultralytics/assets/releases/latest/download/{model_name}",
            ])
            # Add helpful message in comments (not in URL list)
            self.logger.info(f"Future YOLO version detected (v{version_num}). Trying latest releases...")
        
        # Generic fallback for any YOLO model
        suggested.extend([
            f"https://github.com/ultralytics/assets/releases/download/v0.0.0/{model_name}",
            f"https://github.com/ultralytics/ultralytics/releases/download/v0.0.0/{model_name}",
        ])
        
        # Add PyTorch Hub as last resort (works for many models)
        if not model_name_lower.startswith('yolov5'):
            suggested.append(
                f"Try: python -c \"from ultralytics import YOLO; YOLO('{model_id}')\""
            )
        
        return suggested

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
            deleted = []

            # Delete .pt file
            pt_file = self.yolo_folder / f"{model_id}.pt"
            if pt_file.exists():
                pt_file.unlink()
                deleted.append(str(pt_file))

            # Delete NCNN folder
            if delete_ncnn:
                ncnn_folder = self.yolo_folder / f"{model_id}_ncnn_model"
                if ncnn_folder.exists():
                    shutil.rmtree(ncnn_folder)
                    deleted.append(str(ncnn_folder))

            # Update metadata cache
            if model_id in self.cache:
                del self.cache[model_id]
                self._save_cache()

            self.logger.info(f"Deleted model '{model_id}': {', '.join(deleted)}")

            return {
                "success": True,
                "deleted_files": deleted
            }

        except Exception as e:
            self.logger.error(f"Delete failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # ==================== METADATA CACHE ====================

    def _load_cache(self) -> Dict:
        """Load metadata cache from JSON file"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load metadata cache: {e}")
        return {}

    def _save_cache(self):
        """Save metadata cache to JSON file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save metadata cache: {e}")

    # ==================== TORCH.LOAD MONKEY-PATCH ====================

    def _patch_torch_load(self):
        """
        Apply torch.load monkey-patch for PyTorch 2.6+ compatibility
        (Same as add_yolo_model.py - required for loading YOLO checkpoints)

        SECURITY NOTE:
        This bypasses PyTorch's weights_only=True safety mechanism.
        Only use with trusted model files.
        """
        if not TORCH_AVAILABLE:
            self.logger.debug("torch not available, skipping torch.load patch")
            return

        _original_torch_load = torch.load

        def patched_torch_load(*args, **kwargs):
            kwargs["weights_only"] = False
            return _original_torch_load(*args, **kwargs)

        torch.load = patched_torch_load
        self.logger.debug("torch.load patched for PyTorch 2.6+ compatibility")
