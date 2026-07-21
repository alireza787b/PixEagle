# Detection Model Catalog

- **Status:** maintained selection guidance, not a runtime model registry
- **Last reviewed:** 2026-07-21
- **Runtime mechanics:** [SmartTracker Model Setup](MODEL_SETUP.md)

This page helps an operator choose a detector for PixEagle. It does not change
the configured model, download anything automatically, or make an accuracy,
flight, or safety claim. The runtime source of truth remains the
`SmartTracker` schema, the local model-provenance registry, and the readiness
check described in [Model Setup](MODEL_SETUP.md).

## Read This First

- A detector is one component in the pipeline. It does not replace target
  association, tracking-loss handling, follower readiness, command safety, or
  operator approval.
- PixEagle accepts a trusted local Ultralytics-compatible `detect` or `obb`
  artifact through the current backend contract. A model page saying
  "YOLO-compatible" is not proof that its task, labels, serialization, or
  installed framework version is compatible with this checkout.
- PixEagle never downloads a model implicitly. Download through an operator
  tool, verify the publisher's digest through a separate trusted channel, then
  register it with `add_model.py` as described in [Model Setup](MODEL_SETUP.md).
- A model trained on aerial, satellite, maritime, or defense imagery can still
  fail on a live UAV camera. Camera angle, altitude, ground sampling distance,
  compression, blur, weather, illumination, and class taxonomy all create
  domain shift.
- No public checkpoint in this catalog is "military grade", flight certified,
  or suitable as the sole basis for an autonomous decision. Those labels
  require target-domain data, reproducible evaluation, provenance review,
  safety analysis, and operator acceptance.

## Direct Answer: What Works Today

PixEagle currently supports trusted local checkpoints that load through
Ultralytics `YOLO(...)` and report a `detect` or `obb` task. The best practical
starting point depends on the scene:

- **Drone-view people and road vehicles, strongest reviewed community score:**
  `dronefreak/visdrone-yolov9e` has the highest publisher-reported score in the
  reviewed VisDrone collection (mAP50 40.02, mAP50-95 23.73). It is also a
  heavy 117 MB, 58.2M-parameter, 193 GFLOP candidate. It is appropriate for a
  desktop GPU evaluation, not the default Raspberry Pi choice. It still needs
  PixEagle registration, readiness, and target-video acceptance.
- **Drone-view people and vehicles on edge hardware:** start with the VisDrone
  YOLO26n or YOLO26s candidate. Move to `m` only after measured latency and
  thermal evidence says the target computer can sustain it.
- **Oriented planes, ships, harbors, and large/small vehicles in aerial-style
  imagery:** start with official YOLO26n/s-OBB. YOLO26x-OBB has the highest
  official DOTA score in that family, but its size and latency make it a GPU
  benchmark candidate rather than an edge default.
- **A specific coast, airframe class, camera, or altitude:** no public model is
  a reliable universal answer. Fine-tune a supported YOLO detect/OBB model on
  representative project data and compare it against these baselines.

This means PixEagle does have supported aerial candidates. It does not yet have
a universally best aerial-video model, and it should not pretend that a COCO,
VisDrone, DOTA, or satellite benchmark proves mission performance.

### Backend Support Matrix

| Model family or technique | Status in PixEagle | Reason |
| --- | --- | --- |
| Ultralytics YOLO `detect` checkpoints | Supported now | Current backend loads with `YOLO(...)` and normalizes axis-aligned results |
| Ultralytics YOLO `obb` checkpoints | Supported now | Current backend normalizes OBB plus enclosing AABB results |
| Trained Ultralytics YOLO26 P2 checkpoint | Expected through the current YOLO contract, but must be proven | Official P2 weights are not published; a project-trained artifact still needs registration/readiness evidence |
| Ultralytics RT-DETR | Not supported yet | It uses the separate `RTDETR(...)` class and different inference/tracking behavior |
| RF-DETR | Not supported yet | Separate package, model lifecycle, output, export, and license contract |
| YOLOX P2 | Not supported yet | Separate `.pth` format and YOLOX/ByteTrack runtime |
| SAHI tiled inference | Not supported yet | It is an inference pipeline around a detector, with tiling/merge latency and frame-age implications |

Backend expansion is tracked as planned work, not as a promised or hidden
feature. The gate is benchmark-first: an unsupported architecture must beat a
supported YOLO baseline on representative aerial video and target hardware
before its integration complexity is accepted. The implementation gate is
tracked as PXE-0123 in the
[modernization issue register](reporting/agent-ops/codex-modernization/issue-register.md).

## Quick Recommendations

| Use case | Start with | PixEagle position | Hardware direction |
| --- | --- | --- | --- |
| First lab run, ordinary cars/people/vehicles | Official `yolo26n.pt` | Recommended baseline; directly matches the current `detect` contract | CPU, Raspberry Pi-class host with modest expectations, Jetson, or desktop |
| General live detector with more capacity | Official `yolo26s.pt` or `yolo26m.pt` | Compatible baseline; benchmark locally before selecting | Jetson or desktop GPU; `m` is usually not a sensible first Pi choice |
| Aerial objects where orientation matters | Official `yolo26n-obb.pt` or `yolo26s-obb.pt` | Current `obb` contract; labels are DOTA-style, not a universal vehicle taxonomy | GPU preferred; `n` is the first trial |
| Small vehicles and people in drone imagery | VisDrone YOLO26 `n`/`s`, or YOLOv9e for a maximum-capacity GPU trial | Community fine-tune; verify labels, license, and target video | `n` for constrained hardware, `s` for a stronger edge host, YOLOv9e for desktop GPU evaluation |
| RGB maritime search or boat detection | SeaDronesSee fine-tune, or the Argus candidate below | Prefer a project-trained checkpoint; community weights require independent validation | GPU preferred; profile latency and false alarms on water glare |
| Aircraft class recognition in satellite/remote-sensing imagery | MAR20 aircraft OBB candidate | Research candidate only; not evidence for oblique live UAV video | Desktop GPU or offline evaluation first |
| Tiny objects below a few pixels | A trained P2/tiled-inference pipeline | Not a drop-in PixEagle feature today; plan an adapter and measure latency | Usually GPU and higher memory |

The smallest model is not automatically the safest or fastest choice. Measure
end-to-end frame age, detector latency, tracker continuity, false detections,
thermal behavior, and recovery behavior on the target computer.

## Current PixEagle Compatibility

The current implementation is intentionally narrow and auditable:

1. Install the selected AI dependency profile.
2. Put the artifact in the owner-controlled `models/` store.
3. Record a publisher digest or an explicit lab trust assertion.
4. Register it with `add_model.py`.
5. Run `bash scripts/setup/check-ai-runtime.sh --require-smart-tracker`.
6. Confirm the model task, labels, effective device, and one local inference
   before testing SmartTracker on representative video.

In the dashboard Models page, the check action selects a validated artifact.
When Smart Mode is off, the row is labeled **selected** and that exact model is
used on the next activation; the dashboard action atomically stores the GPU and
CPU artifact variants plus any explicit device preference, so no application
reboot is required. Direct path edits through the generic Settings page retain
their system-restart requirement. When Smart Mode is already running, the same
action performs a guarded live switch. A row is
labeled **active** only after the runtime reports that model as loaded. Model
changes remain blocked while following or while a target selection owns model
label semantics.

The backend normalizes detector results into `NormalizedDetection`. Axis-aligned
models provide an enclosing AABB; OBB models may additionally provide angle and
polygon data. The downstream tracker still needs a stable target-selection
policy. Do not assume that a class named `vessel`, `ship`, `car`, or `person`
means the same thing across datasets.

The catalog is deliberately separate from configuration. Adding a row here
must never change `configs/config_default.yaml`, silently change the default
model, or create a new model-path setting.

## Official Baselines

These are the best starting points when a directly supported, reproducible
Ultralytics artifact is more important than domain specialization. The links
below are pinned to the Ultralytics `v8.4.0` assets release; they are download
links for an operator, not automatic PixEagle inputs.

### General Detection

| Model | Task | Approx. file size | Direct artifact | Best use |
| --- | --- | ---: | --- | --- |
| YOLO26n | `detect` | 5.5 MB | [download `yolo26n.pt`](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt) | Default lab baseline and constrained hardware |
| YOLO26s | `detect` | 20.4 MB | [download `yolo26s.pt`](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26s.pt) | More capacity when latency allows |
| YOLO26m | `detect` | 44.3 MB | [download `yolo26m.pt`](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26m.pt) | Desktop/GPU accuracy trial |

See the [official YOLO26 model documentation](https://docs.ultralytics.com/models/yolo26)
for the complete `n/s/m/l/x` family, supported tasks, export options, and
version-specific notes. PixEagle's existing reviewed beginner example is
`yolo26n.pt`; its publisher digest is recorded in
[Model Setup](MODEL_SETUP.md).

### Oriented Aerial Detection

| Model | Task | Approx. file size | Direct artifact | Important limitation |
| --- | --- | ---: | --- | --- |
| YOLO26n-OBB | `obb` | 5.9 MB | [download `yolo26n-obb.pt`](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n-obb.pt) | Fastest official OBB trial; DOTA classes |
| YOLO26s-OBB | `obb` | 21.7 MB | [download `yolo26s-obb.pt`](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26s-obb.pt) | More capacity; benchmark on the target computer |
| YOLO26m-OBB | `obb` | 48.4 MB | [download `yolo26m-obb.pt`](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26m-obb.pt) | GPU-oriented accuracy trial |
| YOLO26x-OBB | `obb` | 126.9 MB | [download `yolo26x-obb.pt`](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26x-obb.pt) | Highest official family DOTA score; desktop GPU benchmark candidate, not an edge default |

The official [Ultralytics OBB guide](https://docs.ultralytics.com/tasks/obb)
states that these checkpoints are pretrained on DOTAv1. DOTA uses oriented
boxes and categories such as plane, ship, large vehicle, and small vehicle;
its [official dataset page](https://captain-whu.github.io/DOTA/dataset) says
the images and annotations are for academic use and prohibit commercial use.
Review both the model/framework license and the training-data terms before
redistributing or using an OBB checkpoint commercially. DOTA performance is
not a live-camera performance guarantee.

Ultralytics publishes the framework and model-family terms on its
[license page](https://www.ultralytics.com/license) and in the
[upstream license file](https://github.com/ultralytics/ultralytics/blob/main/LICENSE).
Those terms are separate from dataset and fine-tune publisher terms.

## Domain-Tuned Candidates

The following entries are useful starting points for research, but they are
not PixEagle defaults and are not independently endorsed by this project.
The immutable Hugging Face URLs pin the repository commit observed during this
review. Recheck the model card, file digest, license, and current PixEagle
compatibility before use.

### Drone Imagery: VisDrone

The official [VisDrone dataset repository](https://github.com/VisDrone/VisDrone-Dataset)
contains drone video/image benchmarks with pedestrians, people, bicycles,
cars, vans, trucks, buses, tricycles, and motorcycles. The community
[VisDrone model collection](https://huggingface.co/collections/dronefreak/visdrone-detection-model-zoo)
provides Ultralytics fine-tunes. The reported scores below are the publisher's
VisDrone test-set results, not PixEagle field results.

| Candidate | Publisher report | Direct pinned artifact | Selection note |
| --- | --- | --- | --- |
| `dronefreak/visdrone-yolov9e` | mAP50 40.02; mAP50-95 23.73; 58.2M parameters; 193 GFLOPs | [download `best.pt`](https://huggingface.co/dronefreak/visdrone-yolov9e/resolve/4593a8ea82676f41c46a7cf3e89e39984ac7a2af/best.pt?download=true) | Highest publisher-reported score in this same-pipeline collection; 117 MB and intended for a desktop GPU trial |
| `dronefreak/visdrone-yolov26n` | mAP50 26.73; mAP50-95 14.64; 2.6M parameters | [download `best.pt`](https://huggingface.co/dronefreak/visdrone-yolov26n/resolve/886ea961330698ad6373756fe2f81b25e2e89ffc/best.pt?download=true) | First constrained-hardware candidate; expect small-object and night failures |
| `dronefreak/visdrone-yolov26s` | mAP50 32.10; mAP50-95 18.06; 10.0M parameters | [download `best.pt`](https://huggingface.co/dronefreak/visdrone-yolov26s/resolve/8a8dc530b08d3e147a81855353d453f125e84414/best.pt?download=true) | Better starting point for a GPU or stronger CPU |
| `dronefreak/visdrone-yolov26m` | mAP50 36.67; mAP50-95 21.22; 21.9M parameters | [download `best.pt`](https://huggingface.co/dronefreak/visdrone-yolov26m/resolve/20879fa2d2f351d1e032bfd0a38a5a6b735b0f03/best.pt?download=true) | Accuracy-oriented; likely too heavy for a Pi-first workflow |

The cards currently declare AGPL-3.0. Review the exact card, the VisDrone
dataset terms, and any additional toolkit terms before commercial use. A
community card's generated usage snippet may contain a stale repository name;
use the actual pinned repository/file link above and verify the downloaded
SHA-256 yourself.

### Maritime RGB Video

The official [SeaDronesSee benchmark](https://github.com/Ben93kie/SeaDronesSee)
targets UAV maritime search and rescue and includes object detection, single
object tracking, and multi-object tracking tracks. It is a strong training and
evaluation source, but it does not provide a PixEagle-ready universal maritime
checkpoint. For a serious maritime deployment, fine-tune a supported backend
on the project's representative camera data and retain held-out water,
weather, glare, vessel-size, and negative-scene evidence.

| Candidate | Direct pinned artifact | What it is and what it is not |
| --- | --- | --- |
| [Argus maritime YOLOv8s card](https://huggingface.co/alimkacar/argus-maritime-yolov8s) | [download `best.pt`](https://huggingface.co/alimkacar/argus-maritime-yolov8s/resolve/9a56703b72999951ae510ea0616c1217f2c06bb5/best.pt?download=true) | Community Ultralytics detect checkpoint for boat/sailboat/vessel/buoy; AGPL-3.0 card; reported inshore/daytime results and known cross-dataset class weakness require independent validation |
| [Coastguard vessel YOLO26l card](https://huggingface.co/MuayThaiLegz/yolo26l-vessel-coastguard-v1) | [download `best.pt`](https://huggingface.co/MuayThaiLegz/yolo26l-vessel-coastguard-v1/resolve/776415d5200505f6ecef6574a0f0388e8510b05f/best.pt?download=true) | Narrow community coast-surveillance experiment with few source frames; do not generalize its reported score to open water or other cameras |

Neither entry should be called a coast-guard, SAR, or autonomous-navigation
solution without an independent test set and an operational safety case.

### Aircraft And Remote Sensing

These candidates illustrate how a specialized model can be useful for offline
analysis while still being the wrong model for a live companion computer.

| Candidate | Direct pinned artifact | Boundary |
| --- | --- | --- |
| [MAR20 aircraft YOLO11m-OBB card](https://huggingface.co/Mercyiris/yolo11m-obb-aircraft) | [download `best.pt`](https://huggingface.co/Mercyiris/yolo11m-obb-aircraft/resolve/c9f67a1f7ca83c5ef4379da22b5d34acb6b6384c/best.pt?download=true) | Apache-2.0 is declared by the card; 20 aircraft classes and 1024 OBB training on remote-sensing/satellite imagery; not validated for oblique live UAV video |
| [YOLOv8m defence card](https://huggingface.co/spencercdz/YOLOv8m_defence) | [download `yolov8m_defence.pt`](https://huggingface.co/spencercdz/YOLOv8m_defence/resolve/335bdf0ddbeba9bd8464d83b66de53fc74f99567/yolov8m_defence.pt?download=true) | Community model with private-data claims and a broad defense taxonomy; treat as unverified until provenance, labels, license, and target-domain tests are complete |

The words "defence" and "military" in a model card describe its publisher's
intended domain, not a PixEagle certification. Do not deploy these candidates
to an autonomous follower without a separate approved validation process.

## Small-Object Options And Future Adapters

Small objects are often a data, optics, and geometry problem rather than a
model-size problem. Increasing image size can improve recall while increasing
latency and memory. It can also make an already-late tracker less useful.

- [Ultralytics YOLO26 with SAHI](https://docs.ultralytics.com/guides/sahi-tiled-inference)
  shows tiled inference for large images. Tiling can preserve small-object
  pixels, but it adds compute and duplicate-detection merging. PixEagle does
  not currently expose SAHI as a supported SmartTracker backend; treat it as a
  planned adapter with explicit frame-age and latency tests.
- Ultralytics publishes `yolo26-p2.yaml` as an architecture-only small-object
  head. The official docs explicitly state that scale-specific `yolo26*-p2.pt`
  weights are not released. Do not invent a download URL for a nonexistent
  official checkpoint.
- [YOLOX-Nano-P2-UAV-Small-Detection](https://huggingface.co/Ming233/YOLOX-Nano-P2-UAV-Small-Detection)
  is a useful research reference for a stride-4 UAV head, but its `.pth`
  artifact and YOLOX/ByteTrack pipeline need an adapter and are not a current
  PixEagle drop-in.
- [RF-DETR](https://github.com/roboflow/rf-detr) is a promising future backend
  candidate. Its package, model tasks, export paths, and license choices need a
  dedicated adapter and contract review before it can be registered as a
  PixEagle model option.
- [Ultralytics RT-DETR](https://docs.ultralytics.com/models/rtdetr) is also a
  separate backend candidate because it loads through `RTDETR(...)`, not the
  current `YOLO(...)` loader. In the reviewed VisDrone collection, the
  publisher-reported RT-DETR-L result was below the supported YOLO candidates;
  that is not evidence to prioritize an adapter without a new target-domain
  benchmark.

Do not add SAHI, P2, RF-DETR, ONNX, TensorRT, or another framework to the
default installation merely because it appears in this catalog. A future
backend slice must define normalized outputs, provenance, resource limits,
device fallback, tracker compatibility, and evidence before adding a setting.

## Selection Workflow

Use this short checklist for every candidate:

1. **Define the target.** Write the exact classes, size range in pixels,
   viewpoint, altitude, camera/lens, frame rate, and expected motion. Decide
   whether axis-aligned boxes are enough or OBB is actually needed.
2. **Check taxonomy.** Compare the model's class names with the operator's
   target vocabulary. Merge/split classes only in a reviewed dataset and
   configuration change; do not silently reinterpret labels.
3. **Check provenance and license.** Record publisher, repository, immutable
   commit or release, file name, SHA-256, model/framework license, dataset
   license, and any commercial restrictions.
4. **Benchmark the target host.** Measure cold load, steady-state inference,
   end-to-end frame age, memory, temperature, dropped frames, and recovery
   after a lost detection on the exact camera pipeline.
5. **Evaluate representative video.** Keep a held-out set covering positive,
   confusing negative, occlusion, blur, lighting, water, and background cases.
   Report precision/recall, false alarms per minute, missed detections,
   temporal stability, and target-switch behavior.
6. **Run PixEagle readiness.** Register the artifact, run the bounded AI
   readiness check, then test SmartTracker with Following disabled. Only after
   the detector/tracker evidence is accepted should a separate, approved
   follower or PX4 validation scenario begin.

## Safe Acquisition And Registration

The catalog intentionally does not provide a command that trusts arbitrary
URLs. For any entry:

1. Open the publisher page and verify the intended file and license.
2. Download to a private temporary file with an operator-controlled tool.
3. Compare the SHA-256 with a digest obtained through a separate trusted
   channel. A repository commit pins a page snapshot; it is not a substitute
   for the file digest.
4. Register with `add_model.py --source-file ... --sha256 ... --trust-model`.
5. Keep the registration receipt and run
   `check-ai-runtime.sh --require-smart-tracker`.

For the complete command, trust policy, collision behavior, NCNN rules, and
failure recovery, follow [Model Setup](MODEL_SETUP.md). Do not use a model
manager's implicit download feature inside PixEagle runtime code.

## Proposing A New Model

Open a documentation change with this information instead of adding an
unverifiable link to the default configuration:

```text
Name and stable model version:
Publisher and official model card/repository:
Immutable repository commit or release:
Exact file name and direct artifact URL:
SHA-256 and how it was independently obtained:
Task: detect or obb:
Class list and label mapping:
Training datasets and their licenses:
Model/framework license:
Reported evaluation protocol and metrics:
Target hardware, input size, and measured end-to-end latency:
Known failure cases and out-of-scope conditions:
PixEagle registration/readiness evidence path:
Date reviewed and reviewer:
```

A contributor may add a candidate to this catalog without making it a default.
Changing the default model, adding an automatic download, or adding a new
backend requires a separate reviewed implementation slice.

## Review And Maintenance Policy

- External links and model cards can change. Recheck them before each release;
  immutable URLs reduce drift but do not replace a current license/provenance
  review.
- Publisher-reported metrics remain publisher-reported metrics. PixEagle does
  not reproduce them by copying the number into this page.
- A stale, withdrawn, unsafe, license-conflicted, or unrepeatable candidate is
  marked as reference-only or removed from the recommendation tables. The
  default runtime remains unchanged until a separate acceptance gate passes.
- Never load a checkpoint solely because it has a plausible file extension.
  Malicious or research-only artifacts exist; provenance, digest, bounded
  registration, and local readiness checks are mandatory.
