# No-pitot guidance fixture software slice

This slice adds an explicit sensor-absent Gazebo guidance fixture using the
existing isolated Runtime, native parameter bounds/readback, observer and
cleanup. It binds `SYS_HAS_NUM_ASPD=0` to the strictly verified
`quadtailsitter-no-pitot-v1` resource variant before staging. `FW_USE_AIRSPD`
is not set; its pinned native default 1 must read back unchanged. The stock
installation remains the default, with one additive differential-pressure
logger subscription.

A fixed pre-arm/pre-takeoff listener probe checks all advertised differential
pressure instances without entering a polling loop. Exact source pins and raw
probe receipts are retained. This is point-in-time absence only. Full-flight
absence, native source selection, actual motion, ownership, cadence, recovery
and height remain separate actual evidence gates. No hardware, native build,
simulator, arm or following action was executed for this software slice.

Standalone native-transition execution rejects the no-pitot fixture before
launch because its FW capture still uses the measured-only stability predicate.
Guidance uses the separately reviewed per-sample native-feedback helper; neither
that helper nor this fixture turns groundspeed into measured airspeed or proves
stall margin. The no-pitot fixture independently requires observed forward
ground motion of at least 14 m/s through the original settled window and the
fresh FW Start window/refresh, using the canonical vector helper and pinned
zero-wind world assumption. The native airframe minimum is a numeric reference
only; stock/MC admission stays unchanged. The no-pitot package has distinct real image/ELF hashes and is not
claimed as a bitmatched stock comparison.

Validation and review inputs are retained under
`reports/sitl/follower-consolidation-20261111/software-gates-s7-no-pitot-fixture-code-r1/`.
Initial contract tests reproduced missing pairing/probe behavior; focused
fixture/runtime/guidance and Phase0 checks pass, and schema remains unchanged.
The author gate passes 303 checks. The merged root gate, including real motion
helpers, paired-window callers, source contracts, geometry, retarget admission
and documentation/hygiene, passes 769 checks in 14.12 s. This is tooling evidence;
the full backend runtime remains covered by its separately recorded R16 source.

Integration renews both the runtime-helper and runtime-assets hashes in the
single guidance evidence source contract after the coordinated changes merge.
Old captures remain bound to their frozen original authority. No compatibility
allowlist, source-hash normalization or production safety/default change is
introduced. Actual no-pitot following remains unqualified pending review and a
separate authorized capture.

The subsequent actual R1 capture passes both pre-action sensor probes and MC
following/release, but refuses FW Start: its original seven-sample settled window
includes forward speeds below 14 m/s. The FW motion condition had not been passed
to the read-only post-transition sampler. Its correction reuses the same
predicate there, so it waits within the original timeout for seven ready samples.
MC settling is unchanged, and the threshold is not lowered. The failed raw
capture remains retained; it proves no FW pursuit. A deterministic accelerating
packet regression checks that the sampler continues beyond the first seven
samples before declaring readiness.
