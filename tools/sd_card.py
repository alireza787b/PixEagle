#!/usr/bin/env python3
"""Offline SD image backup, PiShrink compression and verified restore on Linux."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request

PISHRINK_COMMIT = "5f358d03eed4b7334657ee93867826a2b42f112a"
PISHRINK_SHA256 = "71026f0c02ac099e588a3eb8f70760c1b680aa8ea3acde61a0141fbaeb68c777"
PISHRINK_URL = f"https://raw.githubusercontent.com/Drewsif/PiShrink/{PISHRINK_COMMIT}/pishrink.sh"
CHUNK = 4 * 1024 * 1024


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def privileged(args):
    return args if os.geteuid() == 0 else ["sudo", *args]


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            result.update(chunk)
    return result.hexdigest()


def checksum(path):
    path = Path(path)
    value = digest(path)
    Path(str(path) + ".sha256").write_text(f"{value}  {path.name}\n")
    return value


def verify(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Image not found: {path}")
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.is_file():
        raise ValueError(f"Missing checksum: {sidecar}. Obtain the checksum from the backup, not this unverified file.")
    fields = sidecar.read_text().split()
    if not fields:
        raise ValueError(f"Empty checksum file: {sidecar}")
    expected = fields[0]
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected) or digest(path) != expected.lower():
        raise ValueError(f"Checksum mismatch: {path}; no card will be written.")
    print(f"SHA-256 verified: {path.name}")
    return expected.lower()


def image_reader(path):
    if str(path).endswith(".xz"):
        return lzma.open(path, "rb")
    if str(path).endswith(".gz"):
        return gzip.open(path, "rb")
    if str(path).endswith(".img"):
        return Path(path).open("rb")
    raise ValueError("Select a .img, .img.xz or .img.gz file.")


def image_details(path):
    """Validate compressed data to EOF and measure the bytes actually restored."""
    size, result = 0, hashlib.sha256()
    with image_reader(path) as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            size += len(chunk)
            result.update(chunk)
    if not size:
        raise ValueError("Empty image")
    return size, result.hexdigest()


def nodes(device):
    yield device
    for child in device.get("children", []):
        yield from nodes(child)


def safe_device(device, writing=False):
    if device.get("type") != "disk" or not device.get("size", 0):
        raise ValueError("Select a whole physical card, not a partition or loop device.")
    if not (device.get("rm") or device.get("tran") in ("usb", "mmc")):
        raise ValueError("Only removable, USB or MMC disks are supported; internal disks are refused.")
    if writing and device.get("ro"):
        raise ValueError("The destination is write-protected.")
    for node in nodes(device):
        if node.get("type") not in ("disk", "part"):
            raise ValueError("Device has a mapped/RAID holder; close it explicitly before imaging.")
        for mount in node.get("mountpoints", []) or []:
            if mount and not mount.startswith(("/media/", "/run/media/", "/mnt/")):
                raise ValueError(f"Protected or active mount {mount}; refusing {device['path']}.")
    return device


def inventory():
    data = json.loads(subprocess.check_output([
        "lsblk", "--json", "--bytes", "--output",
        "PATH,TYPE,SIZE,MODEL,SERIAL,TRAN,RM,RO,MAJ:MIN,MOUNTPOINTS,FSTYPE",
    ], text=True))
    return [device for device in data["blockdevices"] if device["type"] == "disk"]


def show_devices(devices):
    print("\nWhole disks — select the SD reader; internal/system disks are refused:")
    for device in devices:
        label = f"{device['path']}  {device['size'] / 1024**3:.1f} GiB  {(device.get('model') or '').strip()}"
        try:
            safe_device(device)
            label += "  [SD/USB candidate]"
        except ValueError:
            label += "  [protected]"
        print(f"  {label}")


def choose_device(path=None, writing=False):
    devices = inventory()
    show_devices(devices)
    path = path or input("\nType the complete card device path: ").strip()
    path = str(Path(path).resolve())
    device = next((item for item in devices if item["path"] == path), None)
    if device is None:
        raise ValueError("Device not listed; reconnect the reader and run list again.")
    safe_device(device, writing=writing)
    if not stat.S_ISBLK(os.stat(path).st_mode):
        raise ValueError("Not a block device")
    return device


def recheck_device(device, writing=False):
    current = next((item for item in inventory() if item["path"] == device["path"]), None)
    keys = ("path", "size", "serial", "maj:min", "model")
    if current is None or any(current.get(key) != device.get(key) for key in keys):
        raise ValueError("Device identity changed. Reconnect and begin again.")
    safe_device(current, writing=writing)
    return current


def separate_storage(path, device):
    """Never unmount the filesystem holding the image/output directory."""
    path = Path(path).resolve()
    while not path.exists():
        path = path.parent
    data = json.loads(subprocess.check_output([
        "findmnt", "--json", "--target", str(path), "--output", "SOURCE",
    ], text=True))
    source = data["filesystems"][0]["source"].split("[", 1)[0]
    if source.startswith("/dev/") and str(Path(source).resolve()) in {node["path"] for node in nodes(device)}:
        raise ValueError("The image/output is on the selected card. Choose another storage device.")


def unmount_device(device):
    device = recheck_device(device)
    mounts = [(node["path"], mount) for node in nodes(device)
              for mount in node.get("mountpoints", []) or [] if mount]
    for part, mount in sorted(mounts, key=lambda item: len(item[1]), reverse=True):
        print(f"Unmounting {mount} ({part})", flush=True)
        run(privileged(["umount", "--", mount]))
    run(["udevadm", "settle"])
    current = recheck_device(device)
    if any(mount for node in nodes(current) for mount in node.get("mountpoints", []) or []):
        raise ValueError("The desktop remounted the card. Close file-manager windows and retry.")


def confirm(text):
    if input(f"\nType {text} to continue: ").strip() != text:
        raise ValueError("Cancelled; no image/card write performed.")


def pishrink_tool():
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "pixeagle" / "sd-tools"
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    tool = cache / f"pishrink-{PISHRINK_COMMIT}.sh"
    if tool.exists():
        if digest(tool) != PISHRINK_SHA256:
            raise ValueError(f"Cached PiShrink checksum differs; inspect/remove {tool} explicitly.")
    else:
        print("Downloading the reviewed PiShrink commit (SHA-256 checked).", flush=True)
        with urllib.request.urlopen(PISHRINK_URL, timeout=30) as response:
            content = response.read(256 * 1024)
        if hashlib.sha256(content).hexdigest() != PISHRINK_SHA256:
            raise ValueError("PiShrink checksum mismatch; nothing will be executed.")
        temporary = tool.with_suffix(".partial")
        with temporary.open("xb") as output:
            output.write(content)
        temporary.replace(tool)
    return tool


def check_tools(names):
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise ValueError("Missing tools: " + ", ".join(missing) +
                         ". See docs/setup/sd-card-backup.md for Ubuntu setup.")


def shrink(raw, output=None):
    raw = Path(raw).resolve()
    verify(raw)
    if raw.suffix != ".img":
        raise ValueError("Shrink needs an uncompressed .img; retain the original backup.")
    check_tools(["parted", "losetup", "tune2fs", "e2fsck", "resize2fs", "md5sum", "xz"])
    tool = pishrink_tool()
    output = Path(output).expanduser().resolve() if output else raw.with_name(raw.stem + "-shrunk.img")
    archive = Path(str(output) + ".xz")
    if output == raw or output.exists() or archive.exists():
        raise ValueError("Shrink output already exists or is the raw image; choose a new filename.")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if shutil.disk_usage(output.parent).free < raw.stat().st_size * 2:
        raise ValueError("Not enough free space for a separate shrink copy and compressed archive.")
    # Create as the invoking user so PiShrink preserves ownership; never shrink the raw file.
    run(["cp", "--reflink=auto", "--sparse=always", "--", str(raw), str(output)])
    run(privileged(["bash", str(tool), "-n", "-v", str(output)]))
    checksum(output)
    partial = Path(str(archive) + ".partial")
    with partial.open("xb") as destination:
        run(["xz", "-T2", "--memlimit-compress=1GiB", "-6", "-c", "--", str(output)], stdout=destination)
    partial.replace(archive)
    checksum(archive)
    print(f"\nCompressed clone image: {archive}")
    return output, archive


def backup(output=None, path=None):
    check_tools(["dd", "cp", "xz", "parted", "losetup", "tune2fs", "e2fsck", "resize2fs", "md5sum"])
    device = choose_device(path)
    output = Path(output).expanduser().resolve() if output else Path.home() / "Pi-images" / time.strftime("pixeagle-%Y%m%d-%H%M%S")
    separate_storage(output, device)
    if output.exists():
        raise ValueError("Backup directory already exists; select a new directory to prevent overwriting.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < device["size"] * 3:
        raise ValueError("Reserve three card capacities for raw, shrink copy and compression staging.")
    pishrink_tool()
    print(f"\nREAD ONLY: {device['path']} → {output}")
    confirm("BACKUP")
    unmount_device(device)
    output.mkdir(mode=0o700)
    raw = output / "pixeagle-full.img"
    partial = output / "pixeagle-full.img.partial"
    # Passing our file descriptor to sudo avoids root-owned output and shell interpolation.
    with partial.open("xb") as destination:
        run(privileged(["dd", f"if={device['path']}", "bs=16M", "iflag=fullblock", "status=progress"]), stdout=destination)
        destination.flush()
        os.fsync(destination.fileno())
    if partial.stat().st_size != device["size"]:
        raise ValueError("Read size differs from the card capacity; incomplete .partial retained.")
    partial.replace(raw)
    checksum(raw)
    shrunk, archive = shrink(raw)
    manifest = dict(created=time.strftime("%Y-%m-%dT%H:%M:%S%z"), source=device,
                    pishrink_commit=PISHRINK_COMMIT, raw=raw.name, shrunk=shrunk.name,
                    archive=archive.name, note="Offline private board snapshot, not a factory or sanitized release.")
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nBackup complete. Original card unchanged. Files: {output}")


def restore(image, path=None):
    check_tools(["dd"])
    image = Path(image).expanduser().resolve()
    verify(image)
    print("Checking compression integrity and the uncompressed size…", flush=True)
    size, expected = image_details(image)
    device = choose_device(path, writing=True)
    separate_storage(image, device)
    if size > device["size"]:
        raise ValueError("Image exceeds destination card capacity; no write performed.")
    print(f"\nERASE destination: {device['path']} ({device['size'] / 1024**3:.1f} GiB)")
    print(f"Image: {image.name} ({size / 1024**3:.1f} GiB restored)")
    confirm(f"ERASE {device['path']}")
    unmount_device(device)
    recheck_device(device, writing=True)
    verify(image)
    process = subprocess.Popen(privileged(["dd", f"of={device['path']}", "bs=4M", "iflag=fullblock",
                                          "conv=fsync", "status=progress"]), stdin=subprocess.PIPE)
    try:
        with image_reader(image) as source:
            for chunk in iter(lambda: source.read(CHUNK), b""):
                process.stdin.write(chunk)
        process.stdin.close()
        if process.wait() != 0:
            raise ValueError("Card write failed; do not use this card until restored again.")
    except BaseException:
        process.terminate()
        process.wait()
        raise
    print("Verifying bytes read back from the destination card…", flush=True)
    process = subprocess.Popen(privileged(["dd", f"if={device['path']}", "bs=4M", "iflag=count_bytes",
                                          f"count={size}", "status=none"]), stdout=subprocess.PIPE)
    observed, count = hashlib.sha256(), 0
    try:
        for chunk in iter(lambda: process.stdout.read(CHUNK), b""):
            observed.update(chunk)
            count += len(chunk)
    finally:
        process.stdout.close()
        returncode = process.wait()
    if returncode or count != size or observed.hexdigest() != expected:
        raise ValueError("Read-back verification failed; do not boot this destination.")
    print("Restore and read-back verified. Eject the reader, then boot the cloned Pi.")


def parser():
    result = argparse.ArgumentParser(description="PixEagle • SD backup / shrink / verified restore (Ubuntu/Linux)")
    commands = result.add_subparsers(dest="command")
    commands.add_parser("list", help="Show whole disks and protected/candidate state")
    commands.add_parser("setup", help="Download and verify pinned PiShrink; no card access")
    command = commands.add_parser("backup", help="Read card, keep raw image, shrink a copy and compress")
    command.add_argument("output", nargs="?")
    command.add_argument("--device", help="Optional whole disk; confirmation still required")
    command = commands.add_parser("shrink", help="Resume shrinking an existing checksummed raw backup")
    command.add_argument("image")
    command.add_argument("--output")
    command = commands.add_parser("restore", help="Write .img/.img.xz/.img.gz to a card, then read back")
    command.add_argument("image")
    command.add_argument("device", nargs="?")
    command = commands.add_parser("verify", help="Check archive checksum and decompression without writing")
    command.add_argument("image")
    return result


def main(argv=None):
    os.umask(0o077)
    if sys.platform != "linux":
        raise ValueError("Use Ubuntu/Linux for this workflow; Raspberry Pi Imager is the graphical alternative.")
    args = parser().parse_args(argv)
    print("\nPixEagle  |  Raspberry Pi SD tools\n")
    if args.command is None:
        parser().print_help()
        return 0
    if args.command in ("list", "backup", "restore"):
        check_tools(["lsblk", "findmnt", "udevadm"])
    if args.command == "list":
        show_devices(inventory())
    elif args.command == "setup":
        print(pishrink_tool())
    elif args.command == "backup":
        backup(args.output, args.device)
    elif args.command == "shrink":
        shrink(args.image, args.output)
    elif args.command == "restore":
        restore(args.image, args.device)
    elif args.command == "verify":
        verify(Path(args.image).expanduser())
        size, _ = image_details(Path(args.image).expanduser())
        print(f"Compression/integrity OK; restored size {size:,} bytes.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError, EOFError) as exc:
        print(f"\nStopped: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted. A partial image/card is not a verified backup; see the guide to resume.", file=sys.stderr)
        sys.exit(130)
