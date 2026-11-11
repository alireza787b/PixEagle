# Frame lifecycle and provenance

The capture owner, tracker and media consumers share frame identity, not mutable
pixel buffers. Source code: `video_handler.py`, `app_controller.py`,
`guidance_observation.py` and `frame_publisher.py` under `src/classes/`.

## Pixel branches

```text
decoder output -> configured rotation/flip -> capture pixels
                                             |          |
                           analysis resize/preprocess    original display copy
                                      |                  + annotations/OSD
                                tracker/segmentor                |
                                      |                   delivery resize/encode
                           immutable measured sample             |
                                                        Dashboard / QGC
```

`NATIVE_CAPTURE_RESOLUTION` preserves decoder detail while analysis retains the
configured capture dimensions. With compatibility behavior, the decoder may
already output the analysis dimensions. Delivery dimensions do not redefine
tracker coordinates. Blur/enhancement belongs to analysis; display starts from
the captured pixels. `resize_pixels` filters scaling; native delivery fits the
source aspect ratio inside the requested bounds. Saved compatibility values
remain until an accepted configuration migration changes them.

The legacy `current_raw_frame`, `current_osd_frame` and resized attributes are
producer state. Consumers use `FramePublisher` snapshots rather than assuming
separate reads of those attributes describe the same frame.

## Identity and freshness

`VideoHandler.get_capture_context(frame)` atomically returns:

- `CaptureStamp`: source epoch, capture ID, monotonic backend receipt and state;
- the actual oriented decoder dimensions, rotation and flip for those pixels;
- an opaque signature of the actual capture opening path, or `None` if unknown.

Receipt time is **not camera exposure time**. Reprocessing, inference completion,
status polling and cached playback cannot refresh it. History and recovery
buffers are bounded copies. Cached images may support operator continuity, but
their state cannot authorize a new measured observation. Replayed video also
remains subject to the separate command-preview/SIH authorization policy.

Before inference, `AppController` freezes an `ImageFrameContext` with source,
target generation, geometry, receipt and optional calibration. Classic and Smart
trackers commit a measured pixel against that context. Retarget/source changes
invalidate obsolete results. A detection box, estimate or repeated output read
does not create a new camera measurement.

## Optional fixed-camera calibration

`VideoSource.FIXED_CAMERA_CALIBRATION` defaults to `null`; ordinary image-based
MC guidance needs no calibration. Measured intrinsics refer to the **actual
decoder output before PixEagle rotation/flip**, with an explicit fixed optical
right/down/forward to physical-body FRD quaternion.

The binding requires the selected-source signature and exact decoder grid. It
freezes the inverse resize/rotation/flip affine, including resize pixel-centre
offsets, before inference. Changed source, epoch, dimensions, orientation or
calibration content invalidates that binding. Failed calibration leaves ordinary
image measurements usable but supplies no calibrated bearing. Manual gimbal
control cannot be treated as fixed extrinsics.

This signature identifies a capture specification, **not physical camera
identity**. A replacement camera at the same address, upstream crop/zoom or an
unobserved moving mount needs its own validation. Exposure/attitude alignment
and native FW readiness are separate gates; calibration alone enables neither.

## Publication and selection

`FramePublisher.publish` copies pixels into read-only arrays and swaps the paired
raw/OSD snapshots under its lock. A source reset clears current frames, selection
tokens and encoded-delivery associations. A late publication from a retired
source is rejected. Format changes advance the stream epoch.

Interactive selection uses the displayed frame's bounded, expiring token and
its retained analysis pixels/geometry. Never substitute the latest telemetry or
use an overlay's integer coordinate helper as a calibration transform. The
calibration affine and display-selection mapping serve different contracts.

## Concurrency and memory

One capture owner serializes reads. Source lifecycle changes may retire a handle
without waiting for a blocked native read; late results are discarded. Async
UDP uses its existing background reader rather than a second `grab`/`retrieve`
loop. Capture mode mutation revokes calibration identity before property writes,
including partial or failed changes. Reopening establishes the new identity.
Direct size mutation of async UDP/GStreamer is refused; change its source
configuration and reopen through the normal lifecycle instead.

NumPy operations are not a synchronization contract. Capture/context locks,
tracker generation checks and immutable publisher snapshots provide that
contract. Do not mutate a published array or infer freshness from a non-null
buffer.

Memory depends on actual decoder, analysis and delivery dimensions plus bounded
history, selection and encoding caches. One 1920×1080 BGR copy is about 5.9 MiB;
count all retained branches rather than assuming a fixed 640×480 footprint.
See [streaming architecture](../04-streaming/README.md) for delivery budgets and
[VideoHandler](video-handler.md) for source/recovery behavior.
