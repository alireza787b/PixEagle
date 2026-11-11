"""Explicit adapter/firmware-correlated ownership receipts for native fixtures."""

from classes.native_guidance import (
    NativeAcquisitionContext,
    NativeReleaseReceipt,
)

TOKEN = "00000000000000000000000000000001"
INCARNATION = "00000000000000000000000000000002"


def acquisition(identity, *, runtime_id="test-adapter", token=TOKEN, activation_timestamp=200):
    return NativeAcquisitionContext(runtime_id, identity, token, INCARNATION, 7, 4, 100, 23, activation_timestamp)


def release_receipt(context, *, outcome="hold_confirmed", nav_state=4, timestamp=300):
    return NativeReleaseReceipt(context, outcome, nav_state, timestamp)
