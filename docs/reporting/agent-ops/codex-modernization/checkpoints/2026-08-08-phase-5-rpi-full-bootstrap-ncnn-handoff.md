# Phase 5 Raspberry Pi Full AI Bootstrap Handoff

Date: 2026-08-08
Issue: PXE-0155
Status: implementation and local validation complete; target repair pending

## Scope

- Repair the explicit Full AI dependency contract so requested NCNN export has
  its reviewed `ncnn` and `pnnx` tooling on maintained Linux x86_64/ARM64 hosts.
- Recover a missing bootstrap `git` or `python3` through the same controlling
  terminal used by the one-line installer.
- Show a usable active-network dashboard URL in the optional SSH login hint
  when the authenticated network-lab profile is configured.

## Decisions

- Core remains the beginner Enter-default and does not install NCNN.
- Full AI invokes the existing transactional `install-ai-deps.sh --with-ncnn`
  path. That path preserves the exact OpenCV provider and validated PyTorch
  runtime and verifies the reviewed dependency bundle before success.
- Installing export tooling does not export uploaded models automatically.
  CUDA continues to use `.pt`; NCNN remains an explicit per-model CPU/edge
  decision with its own provenance and runtime checks.
- A started worker that exits unsuccessfully writes only a bounded sanitized
  diagnostic tail to the normal runtime log. Its private workspace and raw log
  are still removed at the transaction boundary.
- Interactive bootstrap package repair defaults to Yes. Unattended apt mutation
  requires `PIXEAGLE_INSTALL_BOOTSTRAP_PACKAGES=1` plus root or a valid
  non-interactive sudo ticket.
- The SSH hint derives network reachability from the runtime exposure/auth
  config, prefers its exact allowed authorities, and falls back to the existing
  `browser_hosts.py` interface discovery. Wildcard and loopback addresses are
  never advertised as remote browser URLs.

## Validation

```text
installer/setup/dependency/model contracts
349 passed

Phase 0 API inventory and parameter reload
73 passed

infrastructure documentation contracts
31 passed

schema
39 sections / 518 parameters, current

bash -n and Python compilation
passed

ShellCheck --severity=warning
passed with three pre-existing dynamic-source SC1090 warnings

git diff --check
passed
```

Focused tests prove that Enter accepts missing-package recovery, unattended
mutation needs explicit policy, Full invokes and verifies the NCNN bundle,
`pnnx` without `ncnn` is rejected before worker launch, failed-worker
diagnostics are bounded, and a configured network dashboard URL appears in the
generated hint while wildcard/loopback authorities do not.

## Boundaries

- The operator report proves the pre-fix Raspberry Pi failure, not the repaired
  export/load path.
- Existing generated login hints require one explicit regeneration after source
  update; fresh hint installation uses the corrected generator.
- No model accuracy/latency benchmark, PX4, camera, flight, or field acceptance
  is claimed.
