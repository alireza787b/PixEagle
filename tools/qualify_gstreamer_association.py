#!/usr/bin/env python3
"""Prove sender association against locally encoded RTP; no camera or sockets."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from classes.gstreamer_frame_association import GStreamerFrameAssociation, gstreamer_capabilities


def qualify_codec(codec: str) -> dict:
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstRtp", "1.0")
    from gi.repository import Gst, GstRtp

    encoders = {
        "h264": "x264enc tune=zerolatency speed-preset=ultrafast bframes=0 ! h264parse ! rtph264pay",
        "vp8": "vp8enc deadline=1 cpu-used=8 lag-in-frames=0 ! rtpvp8pay",
    }
    association = GStreamerFrameAssociation()
    epochs = []
    for generation in range(2):
        previous_epoch = association.epoch
        epoch = association.reset()
        pipeline = Gst.parse_launch(
            "appsrc name=source format=time is-live=false block=true "
            "caps=video/x-raw,format=I420,width=160,height=120,framerate=20/1 ! "
            f"{encoders[codec]} name=pay pt=96 ssrc=12345 timestamp-offset=4294964000 mtu=300 ! "
            "appsink name=sink sync=false max-buffers=64 drop=false"
        )
        source, sink = pipeline.get_by_name("source"), pipeline.get_by_name("sink")
        observed, packets = [], 0
        try:
            if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError(f"{codec} pipeline could not start")
            for frame_id in range(6):
                running_time = frame_id * 50_000_000
                context = {"frame_id": frame_id, "source_generation": generation,
                           "selection_geometry": {"encoded_width": 160, "encoded_height": 120}}
                if not association.submit(epoch, running_time, context):
                    raise RuntimeError("Input context rejected")
                if frame_id == 2:
                    # Intentionally omit an encoder input, while retaining its context.
                    continue
                buffer = Gst.Buffer.new_allocate(None, 160 * 120 * 3 // 2, None)
                buffer.fill(0, bytes([32 + frame_id * 16]) * buffer.get_size())
                buffer.pts = running_time
                buffer.duration = 50_000_000
                if source.emit("push-buffer", buffer) != Gst.FlowReturn.OK:
                    association.discard(epoch, running_time)
                    raise RuntimeError("appsrc refused input")
            source.emit("end-of-stream")
            while True:
                sample = sink.emit("try-pull-sample", 3 * Gst.SECOND)
                if sample is None:
                    if not sink.get_property("eos"):
                        message = pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
                        raise RuntimeError(str(message.parse_error()) if message else "RTP output timed out")
                    break
                buffer = sample.get_buffer()
                # x264 may offset PTS by 1000 hours; the public segment removes it.
                running_time = sample.get_segment().to_running_time(Gst.Format.TIME, buffer.pts)
                mapped, rtp = GstRtp.RTPBuffer.map(buffer, Gst.MapFlags.READ)
                if not mapped:
                    raise RuntimeError("Invalid RTP output")
                try:
                    packets += 1
                    result = association.observe_packet(
                        epoch, running_time, rtp.get_ssrc(), rtp.get_timestamp(), marker=rtp.get_marker())
                    if result:
                        observed.append({"running_time_ns": result.running_time_ns,
                                         "ssrc": result.ssrc, "rtp_timestamp": result.rtp_timestamp,
                                         "metadata": result.metadata()})
                finally:
                    rtp.unmap()
            expected_frames = [0, 1, 3, 4, 5]
            if [row["metadata"]["frame_id"] for row in observed] != expected_frames:
                raise RuntimeError("Encoded frame context does not match the submitted inputs")
            for row, frame_id in zip(observed, expected_frames):
                if (row["running_time_ns"] != frame_id * 50_000_000
                        or row["rtp_timestamp"] != (4294964000 + frame_id * 4500) % (1 << 32)
                        or row["metadata"]["source_generation"] != generation):
                    raise RuntimeError("RTP wrap, running-time or source generation mismatch")
            if association.observe_packet(previous_epoch, 0, 12345, 4294964000, marker=True) is not None:
                raise RuntimeError("Retired epoch admitted")
            epochs.append({"generation": generation, "packets": packets, "frames": observed})
        finally:
            pipeline.set_state(Gst.State.NULL)
    return {"codec": codec, "passed": True, "epochs": epochs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codecs", choices=("h264", "vp8"), nargs="+", default=["h264", "vp8"])
    parser.add_argument("--output", type=Path, help="Optional JSON evidence file")
    args = parser.parse_args()
    report = {"capabilities": gstreamer_capabilities(), "scope": "sender_payloader_association",
              "network_delivery_verified": False, "presentation_verified": False, "results": []}
    code = 0
    try:
        if not report["capabilities"]["available"]:
            raise RuntimeError(report["capabilities"]["reason"])
        for codec in args.codecs:
            missing = report["capabilities"]["missing_elements"][f"{codec}_association"]
            if missing:
                raise RuntimeError(f"Missing {codec} elements: {', '.join(missing)}")
            report["results"].append(qualify_codec(codec))
    except (ImportError, ValueError, RuntimeError) as error:
        report["error"] = str(error)
        code = 2
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
