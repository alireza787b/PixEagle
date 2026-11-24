# Source-timed rendered camera bearings

Added explicit bounded source-time association beside the existing physical
receive-bound and synthetic-SIH contracts. The new adapter joins actual rendered
image timestamps with retained raw PX4 attitude samples under the verified
launcher clock identity. DDS-adjusted times, host receipt and latest attitude
remain distinct; no synthetic projection or aircraft path is introduced.

One bounded connection-owned history retains original sample receipts. Duplicate
polls cannot refresh them. Source/reset/clock changes, reordered or rewritten
samples and obsolete retarget generations refuse association. The first pair may
wait read-only within the existing native request deadline; this cannot recapture
a Start context or acquire control.

The 152 alignment regressions pass, including ten new source-time/resolver cases.
Actual combined native-camera/FW qualification and the normal application wiring
remain pending; the earlier disarmed camera and reconnect results alone do not
qualify flight guidance.
