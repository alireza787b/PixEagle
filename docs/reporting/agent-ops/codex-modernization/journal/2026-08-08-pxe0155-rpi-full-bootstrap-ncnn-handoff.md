# PXE-0155: Raspberry Pi Full AI Bootstrap Handoff

Date: 2026-08-08
Status: implementation and local validation complete; target repair pending

Raspberry Pi testing showed that Full AI installed the supported Ultralytics
runtime but omitted the separately managed NCNN/pnnx bundle. The model upload
correctly preserved its trusted `.pt` registration when the requested export
failed. Full AI now includes and verifies the reviewed bundle; Core and the
per-model export default are unchanged.

If conversion itself exits unsuccessfully, PixEagle now records a bounded
sanitized worker tail in its normal Logs view before removing private staging.
This preserves the failure cause without retaining an untrusted export tree.

The same bounded setup slice adds guided recovery for missing bootstrap
`git`/`python3` packages and makes the optional SSH login hint show truthful
configured network dashboard URLs, with active-interface discovery as its
fallback. Existing system-wide hints must be regenerated once after update.

Local setup/model contracts pass `349`; Phase 0 passes `73`; infrastructure
documentation passes `31`; schema remains current at `39/518`; Bash syntax,
Python compilation, whitespace, and warning-level ShellCheck gates pass with
only three pre-existing dynamic-source warnings. Raspberry Pi repair/export
evidence remains pending. No accelerator benchmark, PX4, camera, flight, or
field result is claimed.
