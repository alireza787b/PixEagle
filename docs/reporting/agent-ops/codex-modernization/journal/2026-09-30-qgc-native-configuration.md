# 2026-09-30 — native configuration and OSD

The operator accepted the 4b.0 Smart checkpoint and authorized progression until
the physical camera gate. Added the 4b.1 typed configuration contract, persistent
OSD desired-state operation and guarded runtime apply on existing ConfigService.
The dashboard toggle shares that owner. Restart is explicitly unavailable without
supervisor proof; startup camera settings are not mislabeled as tracker reload.

See [checkpoint](../checkpoints/2026-09-30-qgc-native-configuration.md) and
[API contract](../../../../apis/native-configuration.md). Next: native QGC settings
validation and 4b.2 camera-provider mocks before the physical Ethernet checkpoint.

Camera review caught an authoritative reload-tier mismatch: the schema still
promised tracker reload for the independently owned camera transport. Corrected
the generator's eight startup-owned fields and regenerated schema. Native now
consumes those tiers directly; tracker-only adapter settings keep tracker reload.
Defaults and key names are unchanged. Schema/reload tests and provider-publication
regression passed; see the checkpoint for exact results.
