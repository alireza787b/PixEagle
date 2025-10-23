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
import torch
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from datetime import datetime

# Import YOLO from ultralytics
try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False
    logging.warning("Ultralytics not available - YOLO functionality limited")


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
        if not ncnn_folder.exists():
            return False

        # Verify required files exist
        required_files = [
            ncnn_folder / "model.bin",
            ncnn_folder / "model.param"
        ]
        return all(f.exists() for f in required_files)

    def _get_ncnn_path(self, pt_file: Path) -> Path:
        """Get NCNN folder path for a .pt file"""
        return pt_file.parent / f"{pt_file.stem}_ncnn_model"

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

            # Detect custom models (non-COCO)
            is_custom = self._is_custom_model(class_names, num_classes)

            # Detect model type
            model_type = self._detect_model_type(pt_file.stem)

            return {
                "valid": True,
                "model_type": model_type,
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
                "validation": validation_result
            }

            # Auto-export to NCNN if requested
            if auto_export_ncnn:
                self.logger.info(f"Starting automatic NCNN export for {model_id}...")
                export_result = await self._export_async(model_path)
                result["ncnn_export"] = export_result

                if export_result['success']:
                    self.logger.info(f"✅ NCNN export completed: {export_result['ncnn_path']}")
                else:
                    self.logger.warning(f"⚠️ NCNN export failed: {export_result.get('error')}")

            # Refresh model discovery
            self.discover_models(force_rescan=True)

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

            self.logger.info(f"Exporting {pt_file.name} to NCNN format...")

            # Load model (torch.load is already patched in __init__)
            model = YOLO(str(pt_file))

            # Export to NCNN
            export_result = model.export(format="ncnn")

            # Verify export success
            ncnn_folder = self._get_ncnn_path(pt_file)
            if self._check_ncnn_exists(pt_file):
                export_time = time.time() - start_time

                self.logger.info(f"✅ NCNN export successful ({export_time:.2f}s)")

                return {
                    "success": True,
                    "ncnn_path": str(ncnn_folder),
                    "export_time": export_time
                }
            else:
                return {
                    "success": False,
                    "error": "NCNN folder not created after export"
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
        Download YOLO model from URL or Ultralytics hub
        (Refactored from add_yolo_model.py download functions)

        Args:
            model_name: Model filename (e.g., "yolo11n.pt")
            download_url: Optional custom URL (if None, tries Ultralytics hub for yolov5)

        Returns:
            {
                "success": bool,
                "path": str,
                "error": Optional[str]
            }
        """
        destination = self.yolo_folder / model_name

        try:
            # If model is yolov5*, use torch.hub downloader
            if model_name.lower().startswith("yolov5"):
                return self._download_from_ultralytics(model_name, destination)

            # Otherwise, use custom URL download
            if download_url:
                return self._download_from_url(download_url, destination)
            else:
                return {
                    "success": False,
                    "error": "No download URL provided. For non-YOLOv5 models, please provide a URL."
                }

        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return {
                "success": False,
                "error": str(e)
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
        _original_torch_load = torch.load

        def patched_torch_load(*args, **kwargs):
            kwargs["weights_only"] = False
            return _original_torch_load(*args, **kwargs)

        torch.load = patched_torch_load
        self.logger.debug("torch.load patched for PyTorch 2.6+ compatibility")
