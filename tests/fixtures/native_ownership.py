"""Explicit adapter/firmware-correlated ownership receipts for native fixtures."""

from classes.native_guidance import (
    NativeAcquisitionContext,
    NativeReleaseReceipt,
    NativeStartContext,
)

TOKEN = "00000000000000000000000000000001"
INCARNATION = "00000000000000000000000000000002"


def start_context(identity, *, runtime_id="test-adapter", phase="fixed_wing"):
    return NativeStartContext(1, runtime_id, identity.binding, INCARNATION, 23, 9000, 7, 4, 100,
                              phase, 7 if phase == 'multicopter' else 0, 1 if phase == 'multicopter' else 0)


def acquisition(identity, *, runtime_id="test-adapter", token=TOKEN, activation_timestamp=200, start=None):
    start = start or start_context(identity, runtime_id=runtime_id)
    return NativeAcquisitionContext(runtime_id, identity, token, start.firmware_incarnation,
                                    start.intention_revision, start.source_nav_state,
                                    start.source_nav_state_timestamp, start.mode_id, activation_timestamp, start)


def release_receipt(context, *, outcome="hold_confirmed", nav_state=4, timestamp=300):
    return NativeReleaseReceipt(context, outcome, nav_state, timestamp)
