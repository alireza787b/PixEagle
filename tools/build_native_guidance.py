#!/usr/bin/env python3
"""Build native contracts or the isolated SIH firmware image from pinned inputs.

This does not install a service, discover an aircraft or acquire control.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def prepare_sources(lock: dict, cache: Path, destination: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    for source in lock["sources"]:
        repository, commit = source["repository"], source["commit"]
        name = repository.split("/")[-1]
        archive = cache / f"{name}-{commit}.tar.gz"
        if not archive.exists():
            partial = archive.with_suffix(".partial")
            try:
                with urllib.request.urlopen(f"https://codeload.github.com/{repository}/tar.gz/{commit}", timeout=60) as response:
                    with partial.open("wb") as output:
                        shutil.copyfileobj(response, output)
                if hashlib.sha256(partial.read_bytes()).hexdigest() != source["sha256"]:
                    raise ValueError(f"Native dependency checksum mismatch: {name}")
                partial.replace(archive)
            finally:
                partial.unlink(missing_ok=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Native dependency checksum mismatch: {name}")
        with tarfile.open(archive) as bundle:
            expected = f"{name}-{commit}"
            if any(item.name.split("/")[0] != expected for item in bundle):
                raise ValueError(f"Unexpected native dependency archive layout: {name}")
            bundle.extractall(destination, filter="data")


def apply_message_overlay(destination: Path, lock: dict, overlay: Path) -> None:
    """Install the reviewed extension's message into the pinned ROS definitions."""
    commit = next(source["commit"] for source in lock["sources"] if source["repository"] == "PX4/px4_msgs")
    messages = destination / f"px4_msgs-{commit}" / "msg"
    if not messages.is_dir():
        raise ValueError("Pinned PX4 message source is missing")
    for source in sorted(overlay.glob("*.msg")):
        shutil.copyfile(source, messages / source.name)


def apply_sdk_extension(destination: Path, lock: dict, extension: Path) -> None:
    """Patch only the verified SDK source used to build its matching library."""
    source = next(item for item in lock["sources"]
                  if item["repository"] == "Auterion/px4-ros2-interface-lib")
    manifest_path = extension / "extension.json"
    if (not manifest_path.is_file() or hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            != source.get("extension_manifest_sha256")):
        raise ValueError("Native SDK extension manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text())
    if manifest["baseline_commit"] != source["commit"] or manifest["repository"] != source["repository"]:
        raise ValueError("Native SDK extension baseline mismatch")
    sdk = destination / f"px4-ros2-interface-lib-{source['commit']}"
    for root, files in ((extension, manifest["patches"]), (sdk, manifest["original_files"])):
        for name, checksum in files.items():
            candidate = root / name
            if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != checksum:
                raise ValueError(f"Native SDK extension checksum mismatch: {name}")
    for name in manifest["patches"]:
        subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str((extension / name).resolve())],
                       cwd=sdk, check=True, capture_output=True, text=True)
    for name, checksum in manifest["files"].items():
        candidate = sdk / name
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Native SDK patched source checksum mismatch: {name}")


def verify_extension(source: Path, extension: Path) -> None:
    manifest = json.loads((extension / "extension.json").read_text())
    revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    if revision != manifest["baseline_commit"]:
        raise ValueError("Native PX4 baseline does not match the pinned extension")
    for root, files in ((extension, manifest["patches"]), (source, manifest["files"])):
        for name, checksum in files.items():
            candidate = root / name
            if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != checksum:
                raise ValueError(f"Native PX4 extension checksum mismatch: {name}")
    for name in manifest.get("deleted_files", []):
        candidate = source / name
        if candidate.exists() or candidate.is_symlink():
            raise ValueError(f"Removed native PX4 extension source is still present: {name}")
    messages = extension / "messages"
    for message in messages.glob("*.msg"):
        if message.read_bytes() != (source / "msg/versioned" / message.name).read_bytes():
            raise ValueError(f"Native PX4 message overlay differs from firmware: {message.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/pixeagle-native-guidance")
    parser.add_argument("--prepare-only", action="store_true", help="Verify and prepare sources without starting Docker")
    parser.add_argument("--px4-source", type=Path,
                        help="Canonical patched pinned PX4 checkout; required for SIH and PX4 functional targets")
    parser.add_argument("--image", default="pixeagle-native-contracts:development", help="Contract-test image tag")
    parser.add_argument("--target", choices=("contracts", "sih", "px4-functional"), default="contracts")
    args = parser.parse_args()
    if args.target == "px4-functional":
        if args.px4_source is None:
            parser.error("--target px4-functional requires --px4-source with the canonical extension applied")
        from tools.px4_functional import build_functional

        build_functional(args.px4_source, args.output_dir, args.cache_dir,
                         prepare_only=args.prepare_only, verify_extension=verify_extension)
        return
    if args.target == "sih":
        if args.px4_source is None:
            parser.error("--target sih requires --px4-source with the reviewed extension applied")
        from tools.sih_baseline import build_sih

        build_sih(args.px4_source, args.output_dir, prepare_only=args.prepare_only,
                  verify_extension=verify_extension, cache=args.cache_dir.expanduser())
        return
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    context = output / "build-context"
    lock = json.loads((ROOT / "native/dependencies.lock.json").read_text())
    prepare_sources(lock, args.cache_dir.expanduser(), context / "dependencies")
    sdk_extension = ROOT / "native/ros2_interface"
    apply_sdk_extension(context / "dependencies", lock, sdk_extension)
    apply_message_overlay(context / "dependencies", lock, ROOT / "native/px4/messages")
    shutil.copytree(ROOT / "native/px4_guidance", context / "px4_guidance", dirs_exist_ok=True)
    shutil.copyfile(ROOT / "native/Dockerfile.tests", context / "Dockerfile")
    (output / "dependencies.lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    shutil.copyfile(sdk_extension / "extension.json", output / "sdk-extension.json")
    if args.px4_source:
        verify_extension(args.px4_source.resolve(), ROOT / "native/px4")
        commits = {source["repository"]: source["commit"] for source in lock["sources"]}
        interface = context / "dependencies" / f"px4-ros2-interface-lib-{commits['Auterion/px4-ros2-interface-lib']}"
        messages = context / "dependencies" / f"px4_msgs-{commits['PX4/px4_msgs']}"
        subprocess.run(["python3", str(interface / "scripts/check-message-compatibility.py"),
                        str(messages), str(args.px4_source.resolve())], check=True)
    if not args.prepare_only:
        subprocess.run(["docker", "build", "--progress=plain", "--build-arg", f"ROS_IMAGE={lock['ros_image']}",
                        "--build-arg", f"PX4_REVISION={lock['reference_px4_commit']}",
                        "-t", args.image, str(context)], check=True)
        image = subprocess.run(["docker", "image", "inspect", args.image], check=True, capture_output=True, text=True)
        (output / "image-inspect.json").write_text(image.stdout)
    print(f"Native contract build evidence: {output}")
    print("Development contracts only; SIH, ARM64 deployment and hardware qualification remain required.")


if __name__ == "__main__":
    main()
