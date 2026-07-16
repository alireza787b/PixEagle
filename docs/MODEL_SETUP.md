# SmartTracker Model Setup

PixEagle never performs an implicit model download. SmartTracker becomes ready
only when its dependencies are installed and an explicitly registered local
`detect` or `obb` model passes provenance, digest, load, and inference checks on
the configured effective device.

## Before You Start

- Start with the Core installation unless AI tracking is required.
- Treat PyTorch `.pt` files as executable inputs. Use only a model you trust and
  whose origin and digest you can record.
- Review the licenses and notices for the exact Ultralytics, PyTorch, OpenCV,
  NCNN/pnnx, accelerator, model, and dataset components selected for the
  intended deployment. Component availability is not a licensing conclusion;
  the operator or distributor remains responsible for that review.
- Generic speed claims are not portable. Measure the selected model, input size,
  tracker settings, and thermal behavior on the target hardware.

Upstream references:

- [Ultralytics licensing options](https://www.ultralytics.com/license)
- [Ultralytics upstream license text](https://github.com/ultralytics/ultralytics/blob/main/LICENSE)
- [PyTorch `torch.load` security warning](https://docs.pytorch.org/docs/stable/generated/torch.load.html)

## Install AI Dependencies

From the PixEagle root:

```bash
EVIDENCE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/pixeagle/setup-evidence"
bash scripts/setup/setup-pytorch.sh --mode auto \
  --report-json "$EVIDENCE_DIR/pytorch.json"
bash scripts/setup/install-ai-deps.sh \
  --report-json "$EVIDENCE_DIR/ai-dependencies.json"
```

Requested report paths are owner/type/write checked before venv mutation. If
publication still fails after the verified AI environment is committed, the
installer reports `installed_evidence_failed`; the installed environment is
retained and the message does not claim rollback.

The first installer uses the platform matrix and verifies the selected runtime
and accelerator. Standard index profiles request exact PyTorch versions but do
not hash-lock the selected wheels or transitive dependencies. Digest-supplied
wheel overrides verify those direct artifacts only.

The second installer force-installs the exact SHA-256-verified Ultralytics wheel
without dependency resolution, resolves the separate AI compatibility ranges,
and proves that the selected OpenCV provider did not change. Its report records
installed versions plus metadata/RECORD and loaded-module fingerprints. These
reports are target-host provenance, not proof of a fully reproducible Python or
native environment. NCNN and pnnx are not installed by default.

## Register An Existing Model

Place the trusted file directly under `models/`, obtain the publisher's digest,
and compare it before approving checkpoint execution:

```bash
sha256sum models/target.pt
.venv/bin/python add_model.py \
  --model-name target.pt \
  --sha256 <publisher-sha256> \
  --trust-model
```

`--trust-model` is an explicit statement that the operator trusts the source and
approves loading a potentially executable PyTorch checkpoint. Omitting
`--sha256` is allowed only for an interactive local lab registration and is
recorded as an operator assertion, not publisher-digest verification.

The initializer and model manager normalize the runtime user's owned `models/`
directory to owner-only mode `0700`. The owner-only
`models/.model-provenance.json` registry is the trust authority;
`models/.models.json` is only a bounded rebuildable metadata cache and is
ignored unless it is an owner-only regular file. Unknown files, symlinks, hard
links, path escapes, unsafe permissions, and files changed after registration
are not loaded.

Registration keeps one no-follow descriptor pinned from the digest shown to the
operator through checkpoint inspection and provenance commit. Ultralytics sees
a private lease-owned alias retaining the canonical `.pt` or `_ncnn_model`
spelling, while that alias resolves only to the pinned `/proc/self/fd` descriptor.
The alias is removed with the descriptor, so a model-store path swap or an
operator-supplied symlink cannot redirect the transaction. Publisher-verified
provenance also records that the publisher digest was supplied separately;
PixEagle never promotes its own observed digest into publisher evidence.
Registrations created by an older implementation without the complete evidence
receipt must be re-registered. In `digest_required` mode, discovery, validation,
export, and runtime loading all reject ambiguous legacy publisher records.

Upgrade an incomplete legacy record by repeating the explicit local registration
with the publisher digest:

```bash
.venv/bin/python add_model.py --model-name target.pt \
  --sha256 <publisher-sha256> --trust-model
```

PixEagle replaces only an incomplete legacy record whose recorded digest and
size match the same pinned artifact and whose remaining fields do not
contradict it. The checkpoint is inspected once while the replacement receipt
is committed. A changed artifact, conflicting legacy field, or malformed
non-legacy record is refused; an exact retry of the completed receipt does not
execute the checkpoint again.

## Obtain Models Outside PixEagle

PixEagle does not fetch arbitrary model URLs. This keeps DNS rebinding,
environment-proxy, redirect, credential, and server-side request-forgery risks
outside the flight-adjacent process. Download from the publisher with a normal
operator tool, verify the digest supplied through a separate trusted channel,
then place the file in the owner-controlled model store:

```bash
curl --fail --location --output /tmp/target.pt \
  https://publisher.example/target.pt
printf '%s  %s\n' '<publisher-sha256>' /tmp/target.pt | sha256sum --check
install -m 600 /tmp/target.pt models/target.pt
.venv/bin/python add_model.py --model-name target.pt \
  --sha256 <publisher-sha256> --trust-model
```

The authenticated dashboard Models page accepts a local file upload through the
same trust transaction. Upload count, headers, body size, parsing time, disk
headroom, staging, process-local and cross-process concurrent ingestion are
bounded. Cancellation retains transaction ownership until the worker finishes
and removes staging. There is no hidden URL download route or CLI option.

An exact retry of a publisher-digest-bound upload or registration returns the
original deterministic registration receipt without loading the checkpoint a
second time. A same-name request with different bytes, digest, source, or trust
method is a collision and is refused; it never overwrites the existing model.
The authenticated model-file download pins the verified inode, releases the
shared store lease before network streaming, and hashes the bounded stream
again while sending it.

The loaded SmartTracker model holds a shared model-store lease so its files
cannot be replaced or deleted underneath the runtime. Upload, export, or delete
returns `MODEL_STORE_BUSY` immediately instead of blocking an API worker. Stop
or switch away from SmartTracker, complete the model-store operation, then
reactivate the intended model.

## Optional NCNN Export

NCNN adds dependencies and a second artifact that must be validated separately.
Install it only when the target needs it:

```bash
bash scripts/setup/install-ai-deps.sh --with-ncnn \
  --report-json "${XDG_STATE_HOME:-$HOME/.local/state}/pixeagle/setup-evidence/ai-dependencies-ncnn.json"
.venv/bin/python add_model.py \
  --model-name target.pt \
  --sha256 <publisher-sha256> \
  --trust-model \
  --export-ncnn
```

NCNN/pnnx artifacts are platform-dependent and resolver-managed. A successful
import and recorded installed fingerprint do not turn them into a hash-locked
environment. Export runs in a dedicated Linux cgroup-v2 subtree with POSIX
resource limits, a schema-bounded hard timeout, and workspace file/byte quotas.
The non-root worker stops before third-party code executes, enters the cgroup,
applies per-process CPU, address-space, file-size, file-descriptor, and process
count limits, and only then continues. Success is withheld until `cgroup.kill`
has removed every process remaining in that boundary and the cgroup reports
empty. Normal descendants inherit the boundary even when they create another
process group or session. A host without an owner-delegated, writable cgroup-v2
boundary fails closed and cannot export.

The system-level unit generated by `pixeagle-service enable` is the maintained
integration for this requirement. It sets systemd `Delegate=yes`, which permits
the non-root PixEagle service to manage only its own cgroup subtree; it does not
change `User=`, add Linux capabilities, or grant general host privilege. Manual
tmux runs and other non-systemd service managers are not automatically
delegated and are not claimed as NCNN-export-capable. They fail closed unless
the external launcher independently supplies an owner-delegated cgroup-v2
boundary.

This containment bounds exporter lifecycle and resource use; it is not a
security sandbox for hostile checkpoint code. Explicit source trust remains
mandatory. A timeout, quota breach, unexpected path, link, special file, or
incomplete descendant cleanup fails the export and discards staging. NCNN
provenance uses a versioned, domain-separated manifest that hashes entry type,
full relative path, size, file content, and empty directories. Exports recorded
with an older manifest schema must be deleted and re-exported.

## Configure The Runtime

The schema-backed defaults are:

```yaml
SmartTracker:
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"
  SMART_TRACKER_CPU_MODEL_PATH: "models/yolo26n_ncnn_model"
  SMART_TRACKER_MODEL_MAX_BYTES: 268435456
  SMART_TRACKER_MODEL_TRUST_POLICY: "operator_ack_or_digest"
  SMART_TRACKER_NCNN_EXPORT_TIMEOUT_SECONDS: 900
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_FALLBACK_TO_CPU: true
```

`operator_ack_or_digest` is the beginner lab/development default: explicit
operator approval is mandatory and a publisher digest is strongly recommended.
The `production_remote` setup profile sets `digest_required`, which refuses both
local registration and dashboard upload without the expected SHA-256. The size
limit is schema-bounded to 1-512 MiB. The NCNN export timeout is bounded to
30-3600 seconds. Both require a system restart after change.

Apply host-specific values through the Settings/config workflow. Do not create
another model-path setting outside the `SmartTracker` schema.

## Prove Readiness

```bash
bash scripts/setup/check-ai-runtime.sh
bash scripts/setup/check-ai-runtime.sh --require-smart-tracker
```

The second command exits nonzero unless required modules import and a local
candidate is loaded successfully within the bounded probe. It also rejects an
unsupported task and a CPU result when configuration requires GPU without CPU
fallback. Keep the command output with target-host evidence; file existence
alone is not readiness. The child sends its authoritative result through an
inherited private file descriptor; upstream stdout/stderr logs are retained only
as diagnostic tails and cannot corrupt the machine-readable result.

## Failure Recovery

Before commit, an AI installer failure restores the exact pre-run PixEagle
virtual environment and removes the failed replacement. If that rollback cannot
complete, setup fails explicitly and retains the recovery path it reports; do
not treat that state as ready. After a verified environment is committed, a
later evidence-publication or temporary-file cleanup failure retains the new
environment and reports `installed_evidence_failed` or
`installed_cleanup_failed`. Correct the reported issue and repeat the installer;
do not repair the environment with ad hoc global `pip` commands.
