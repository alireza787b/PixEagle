#!/usr/bin/env python3
"""Reconcile the retired Python gRPC distribution without shadow imports."""

import argparse
import importlib
from importlib import metadata
import subprocess
import sys


def legacy_client_present():
    try:
        return int(metadata.version("mavsdk").split(".", 1)[0]) < 4
    except metadata.PackageNotFoundError:
        return False


def reconcile(*, migrate=False):
    importlib.import_module("mavsdk_grpc")
    if legacy_client_present():
        if not migrate:
            raise RuntimeError("Retired mavsdk gRPC distribution remains; rerun managed setup")
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "mavsdk"], check=True)
        if legacy_client_present():
            raise RuntimeError("Retired mavsdk gRPC distribution was not removed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate", action="store_true")
    args = parser.parse_args()
    reconcile(migrate=args.migrate)
