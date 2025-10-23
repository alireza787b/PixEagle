#!/usr/bin/env python3
"""
add_yolo_model.py - CLI for adding YOLO models

This script manages YOLO model files by allowing the user to specify the name of a YOLO model.
It checks if the specified model file exists in the 'yolo' subfolder:
  - If it exists, the script exports the model to NCNN format using YOLO's built-in export().
  - If it does not exist, the script downloads the model using an appropriate method:
       - For models starting with "yolov5", it uses YOLO's built-in downloader via torch.hub.
       - For other versions (e.g., "yolo11n"), it asks the user to provide a download URL.
    Then it exports the model.

REFACTORED: Now uses YOLOModelManager class for consistency with web API.

Usage examples:
    python add_yolo_model.py --model_name yolov5s.pt
    python add_yolo_model.py --model_name yolo11n.pt

Dependencies:
    - Python 3.x
    - torch (pip install torch)
    - requests (pip install requests)
    - ultralytics (pip install ultralytics)

Author:
-------
Alireza Ghaderi  <p30planets@gmail.com>
📅 March 2025
🔗 LinkedIn: https://www.linkedin.com/in/alireza787b/

License & Disclaimer:
---------------------
This project is provided for educational and demonstration purposes only.
The author takes no responsibility for improper use or deployment in production systems.
Use at your own discretion. Contributions are welcome!
"""

import argparse
import os
import sys
from pathlib import Path

# Import the YOLOModelManager class (refactored core logic)
from src.classes.yolo_model_manager import YOLOModelManager

def main():
    """
    Main CLI entry point - now uses YOLOModelManager for consistency with web API.
    Maintains backward compatibility with original script usage.
    """
    parser = argparse.ArgumentParser(
        description="Add and export a YOLO model to NCNN format (CLI interface)"
    )
    parser.add_argument("--model_name", type=str, help="Name of the YOLO model file (e.g., yolov5s.pt or yolo11n.pt)")
    parser.add_argument("--download_url", type=str, help="Optional custom download URL for non-YOLOv5 models")
    parser.add_argument("--skip_export", action="store_true", help="Skip NCNN export (download only)")
    args = parser.parse_args()

    # Get model name (interactive if not provided)
    model_name = args.model_name.strip() if args.model_name else input(
        "\nPlease enter the YOLO model file name (e.g., yolov5s.pt or yolo11n.pt): "
    ).strip()

    print("\n" + "="*60)
    print("  YOLO Model Manager - CLI")
    print("="*60)

    # Initialize YOLOModelManager (uses clean class)
    manager = YOLOModelManager()
    model_path = manager.yolo_folder / model_name

    print(f"\n[INFO] YOLO folder: '{manager.yolo_folder}'")
    print(f"[INFO] Checking for model: '{model_name}'...")

    # Check if model exists
    if not model_path.exists():
        print(f"[WARNING] Model file '{model_name}' not found.")
        user_input = input("Do you want to download the model? (y/n): ").strip().lower()

        if user_input != 'y':
            print("[ERROR] Model download aborted by user. Exiting.")
            sys.exit(1)

        # Download using manager
        download_result = manager.download_model(model_name, args.download_url)

        if not download_result['success']:
            print(f"[ERROR] Download failed: {download_result['error']}")
            sys.exit(1)

        print(f"[INFO] ✅ Model downloaded successfully: {download_result['path']}")
    else:
        print(f"[INFO] ✅ Model file found: {model_path}")

    # Validate model
    print("\n[INFO] Validating model file...")
    validation = manager.validate_model(model_path)

    if not validation['valid']:
        print(f"[ERROR] Model validation failed: {validation['error']}")
        sys.exit(1)

    # Display validation results
    print(f"\n[INFO] ✅ Model validation successful:")
    print(f"       Model Type: {validation['model_type']}")
    print(f"       Classes: {validation['num_classes']}")

    if validation['is_custom']:
        print(f"       ✨ Custom trained model detected!")
        class_names = validation['class_names'][:10]
        print(f"       Class Names: {', '.join(class_names)}...")

    print(f"       File Size: {model_path.stat().st_size / (1024 * 1024):.2f} MB")

    # Export to NCNN (unless skipped)
    if not args.skip_export:
        print("\n[INFO] Exporting model to NCNN format...")
        export_result = manager.export_to_ncnn(model_path)

        if export_result['success']:
            print(f"\n[INFO] ✅ NCNN export successful!")
            print(f"       NCNN Folder: {export_result['ncnn_path']}")
            print(f"       Export Time: {export_result['export_time']:.2f}s")
        else:
            print(f"[ERROR] NCNN export failed: {export_result['error']}")
            sys.exit(1)
    else:
        print("[INFO] Skipping NCNN export (--skip_export flag)")

    print("\n" + "="*60)
    print("  ✅ All operations completed successfully!")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
