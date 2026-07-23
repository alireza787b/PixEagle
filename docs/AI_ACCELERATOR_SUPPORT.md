# AI Accelerator Support

PixEagle selects its PyTorch runtime from
`scripts/setup/pytorch_matrix.json`. The installer detects platform facts,
selects one reviewed profile, installs exact top-level versions, and then
executes a real accelerator kernel. A visible GPU or a successful
`torch.cuda.is_available()` call is not accepted as proof by itself.

## Maintained Paths

| Host | SmartTracker path | Setup behavior |
|---|---|---|
| Ubuntu/Debian x86_64 with NVIDIA GPU | CUDA with a trusted `.pt` model | Selects a matrix profile from driver CUDA level and compute capability |
| Ubuntu/Debian x86_64 without supported NVIDIA CUDA | CPU with `.pt`; optional NCNN | `auto` selects the CPU profile |
| Raspberry Pi 4/5 and Linux ARM64 | CPU with `.pt`; optional NCNN | Uses official Linux ARM64 CPU wheels |
| NVIDIA Jetson | CPU, or JetPack-specific CUDA wheels | JetPack is detected; GPU setup requires reviewed, digest-verified wheel overrides when the matrix has no pinned NVIDIA wheel |
| Apple Silicon | CPU | MPS model execution is not yet a maintained SmartTracker backend |
| AMD/Intel GPU on Linux | CPU with `.pt`; optional NCNN | No maintained ROCm/XPU SmartTracker backend is currently claimed |

The matrix is the source of truth for exact versions and selectors. Update that
file and its policy tests when upstream support changes; do not add card names
or wheel versions to installer conditionals.

## Verify Or Repair A Host

Stop the runtime that owns the environment, then run:

```bash
make stop
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh
bash scripts/setup/check-ai-runtime.sh --require-smart-tracker
```

Use `--mode gpu` instead of `--mode auto` when CPU fallback during installation
would hide an unacceptable GPU setup failure. The report includes the selected
profile, GPU name, driver CUDA level, compute capability, compiled
architectures, and CUDA kernel result.

For NVIDIA desktop GPUs, `nvidia-smi` must work for the runtime user. Its
reported CUDA value describes the maximum CUDA runtime supported by the driver;
installing a separate CUDA toolkit does not repair an old driver. If no matrix
rule matches, use CPU temporarily or update the driver and rerun the commands
above.

Jetson CUDA packages are coupled to the installed JetPack/L4T release. Follow
the failure message and NVIDIA's
[Jetson PyTorch installation guide](https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/)
instead of installing an x86 or generic PyPI CUDA wheel. Operator wheel
overrides require immutable sources and SHA-256 digests.

Upstream compatibility references:

- [PyTorch 2.12 CUDA support policy](https://pytorch.org/blog/pytorch-2-12-release-blog/)
- [NVIDIA GPU compute capabilities](https://developer.nvidia.com/cuda/gpus)
- [NVIDIA Jetson PyTorch compatibility](https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform-release-notes/pytorch-jetson-rel.html)

## Dashboard Device State

The operational bar shows a compute badge while SmartTracker is active:

- `Compute: CUDA` or `CPU` is the loaded runtime.
- `Compute: CPU fallback` means GPU loading or execution failed; hover for the
  reason.
- `Compute: Loading` means SmartTracker is selected but has not published a
  loaded runtime yet.

The Models page may show `Selected Model` and `Runtime Device --` while Classic
tracking is active. That is a configured standby model, not evidence that CPU
or CUDA inference is running.

## CUDA And NCNN Are Different Paths

Uploading a `.pt` model does not create NCNN automatically. On an NVIDIA
workstation, CUDA runs the `.pt` model directly and NCNN is not required. NCNN
is an optional CPU/edge export for hosts where it benchmarks better. Install
its optional dependencies and export explicitly using
[SmartTracker Model Setup](MODEL_SETUP.md#optional-ncnn-export).

An unsupported accelerator can be added through the detection-backend
interface, but it must define installation policy, executable runtime
verification, fallback semantics, API state, dashboard labeling, and target
hardware evidence before being listed as maintained.
