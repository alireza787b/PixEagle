#!/usr/bin/env python3
"""
add_yolo_model.py - CLI for adding YOLO models

This script manages YOLO model files with a robust, user-friendly download system.

Features:
  - Automatic local model detection (uses existing models if found)
  - Smart download with multiple fallback methods:
       * YOLOv5: Automatic download via torch.hub
       * YOLO8/YOLO11: Automatic download via Ultralytics YOLO class
       * Future versions (yolo12, yolo13, etc.): Automatic detection and download
       * URL suggestions: Provides helpful URLs if auto-download fails
       * Interactive prompt: Asks user for URL as final fallback
  - Automatic NCNN export for CPU inference
  - Full integration with PixEagle web dashboard

REFACTORED: Now uses YOLOModelManager class for consistency with web API.

Usage examples:
    python add_yolo_model.py --model_name yolov5s.pt
    python add_yolo_model.py --model_name yolo26n.pt

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
    parser.add_argument("--model_name", type=str, help="Name of the YOLO model file (e.g., yolov5s.pt or yolo26n.pt)")
    parser.add_argument("--download_url", type=str, help="Optional custom download URL for non-YOLOv5 models")
    parser.add_argument("--skip_export", action="store_true", help="Skip NCNN export (download only)")
    args = parser.parse_args()

    # Get model name (interactive if not provided)
    if args.model_name:
        model_name = args.model_name.strip()
    else:
        print("\n" + "="*60)
        print("  YOLO Model Manager - CLI")
        print("="*60)
        print("\n[INFO] Supported YOLO models:")
        print("  • YOLOv5: yolov5s.pt, yolov5m.pt, yolov5l.pt, yolov5x.pt")
        print("  • YOLO8:  yolov8n.pt, yolov8s.pt, yolov8m.pt, yolov8l.pt, yolov8x.pt")
        print("  • YOLO11: yolo11n.pt, yolo11s.pt, yolo11m.pt, yolo11l.pt, yolo11x.pt")
        print("  • YOLO26: yolo26n.pt, yolo26s.pt, yolo26m.pt, yolo26l.pt, yolo26x.pt")
        print("  • Future versions (yolo12, yolo13, etc.) are also supported!")
        print()
        model_name = input("Please enter the YOLO model file name (e.g., yolo26n.pt): ").strip()
        if not model_name:
            print("[ERROR] No model name provided. Exiting.")
            sys.exit(1)

    print("\n" + "="*60)
    print("  YOLO Model Manager - CLI")
    print("="*60)

    # Initialize YOLOModelManager (uses clean class)
    manager = YOLOModelManager()
    model_path = manager.yolo_folder / model_name

    print(f"\n[INFO] YOLO folder: '{manager.yolo_folder}'")
    print(f"[INFO] Checking for model: '{model_name}'...")

    # Check if model exists locally first
    if model_path.exists():
        print(f"[INFO] ✅ Model file found locally: {model_path}")
        file_size_mb = model_path.stat().st_size / (1024 * 1024)
        print(f"[INFO] File size: {file_size_mb:.2f} MB")
        print("[INFO] Skipping download - using existing model file.")
    else:
        print(f"[WARNING] Model file '{model_name}' not found locally.")
        user_input = input("Do you want to download the model? (y/n): ").strip().lower()

        if user_input != 'y':
            print("[ERROR] Model download aborted by user. Exiting.")
            sys.exit(1)

        # Try download with robust fallback chain
        print("\n[INFO] Attempting automatic download...")
        download_result = manager.download_model(model_name, args.download_url)

        if download_result['success']:
            print(f"[INFO] ✅ Model downloaded successfully: {download_result['path']}")
        else:
            # Automatic download failed - show suggested URLs
            print(f"\n[WARNING] Automatic download failed: {download_result['error']}")
            print("\n[INFO] Don't worry! We'll help you get the model.")
            
            suggested_urls = download_result.get('suggested_urls', [])
            if suggested_urls:
                print("\n[INFO] 💡 Suggested download URLs (try these in order):")
                # Filter out Python command suggestions
                url_list = [url for url in suggested_urls if url.startswith('http')][:5]
                for i, url in enumerate(url_list, 1):
                    print(f"   {i}. {url}")
                
                # Check for Python command suggestions
                python_cmds = [url for url in suggested_urls if url.startswith('Try:')]
                if python_cmds:
                    print(f"\n   Alternative: {python_cmds[0]}")
            
            # Ask user for URL as final fallback
            print("\n[INFO] Please provide a download URL for the model.")
            print("       You can:")
            print("       • Copy one of the URLs above and paste it here")
            print("       • Provide your own download URL")
            print("       • Press 'q' to quit and download manually")
            print()
            user_url = input("Enter download URL (or 'q' to quit): ").strip()
            
            if user_url.lower() == 'q':
                print("\n[INFO] Download aborted. You can:")
                print("   1. Download the model manually and place it in the 'yolo' folder")
                print("   2. Run this script again with: --download_url <URL>")
                print("   3. Use the web dashboard to upload the model")
                sys.exit(0)
            
            if not user_url:
                print("[ERROR] No URL provided. Exiting.")
                sys.exit(1)
            
            # Validate URL format
            if not (user_url.startswith('http://') or user_url.startswith('https://')):
                print("[WARNING] URL doesn't start with http:// or https://. Trying anyway...")
            
            # Try download with user-provided URL
            print(f"\n[INFO] Downloading from provided URL: {user_url}")
            print("[INFO] This may take a few moments depending on file size...")
            download_result = manager.download_model(model_name, user_url)
            
            if download_result['success']:
                print(f"[INFO] ✅ Model downloaded successfully: {download_result['path']}")
            else:
                print(f"\n[ERROR] Download failed: {download_result['error']}")
                print("\n[INFO] Troubleshooting tips:")
                print("   • Check if the URL is correct and accessible")
                print("   • Verify your internet connection")
                print("   • Try downloading the model manually from the Ultralytics website")
                print("   • Place the .pt file in the 'yolo' folder and run this script again")
                sys.exit(1)

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
    print("="*60)
    print(f"\n[INFO] Model ready: {model_path}")
    if not args.skip_export:
        ncnn_path = manager._get_ncnn_path(model_path)
        if ncnn_path.exists():
            print(f"[INFO] NCNN export available: {ncnn_path}")
    print("\n[INFO] You can now use this model in PixEagle!")
    print("       • Use the web dashboard to switch models")
    print("       • Or configure it in config_default.yaml")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
