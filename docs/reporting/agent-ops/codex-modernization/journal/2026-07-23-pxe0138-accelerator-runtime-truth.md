# PXE-0138: Accelerator Runtime Truth

Resumed from the Ubuntu Full AI acceptance feedback. The model inventory showed
trusted `.pt` models but no live runtime device and no NCNN exports. Audit
separated the two concerns: NCNN is optional CPU/edge output, while the GPU path
was undermined by a stale all-CUDA-12 profile and a non-executable CUDA probe.

Implemented a matrix-driven NVIDIA selector, Blackwell-capable current and
compatibility profiles, executable CUDA verification, model-load fallback
truth, and the operator compute badge. Extended the policy across Raspberry
Pi/Linux ARM and Jetson without pretending target evidence: ARM defaults to
CPU, strict GPU fails when unsupported, and Jetson acceleration remains bound
to pinned profiles or digest-verified operator wheels.

The focused independent review produced five actionable findings; all were
closed. Local gates are green. The next action is one bounded RTX 5080 strict
GPU test, then beta tag/release only if that host proves kernel execution and
the live dashboard reports CUDA.
