#!/usr/bin/env python3
"""Camera-free ICE/DTLS/SRTP and exact decoded-frame qualification.

Uses numbered uniform pixels from FramePublisher, not a camera or flight link.
This intentionally disables congestion control on an unconstrained loopback;
it does not qualify adaptation, QGC presentation or production availability.
"""

import argparse
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from classes.frame_publisher import CaptureStamp, FramePublisher
from classes.gstreamer_webrtc_peer import GStreamerWebRTCPeer, _gstreamer


async def qualify_peer(codec: str, *, congestion_control: bool = False,
                       source_width: int = 160, source_height: int = 120, minimum_media_seconds: float = 0,
                       bitrate_bps: int = 1_000_000, maximum_bitrate_bps: int = 4_000_000) -> dict:
    if not 0 <= minimum_media_seconds <= 60:
        raise ValueError("Media observation duration must be between zero and sixty seconds")
    Gst, GstRtp, _, GstWebRTC, _ = _gstreamer()
    publisher = FramePublisher()
    sender = GStreamerWebRTCPeer(publisher, fps=10, require_congestion_control=congestion_control,
                                bitrate_bps=bitrate_bps, maximum_bitrate_bps=maximum_bitrate_bps)
    receiver = Gst.Pipeline.new("qualification-receiver")
    peer = Gst.ElementFactory.make("webrtcbin", "receiver")
    peer.set_property("bundle-policy", "max-bundle")
    peer.set_property("latency", 50)
    receiver.add(peer)
    encoding = "H264" if codec == "h264" else "VP8"
    codec_caps = (",packetization-mode=(string)1,profile-level-id=(string)42e01f"
                  if codec == "h264" else "")
    caps = Gst.Caps.from_string(
        f"application/x-rtp,media=video,encoding-name={encoding},clock-rate=90000,payload=96,"
        f"rtcp-fb-nack=(boolean)true,rtcp-fb-nack-pli=(boolean)true{codec_caps}")
    if congestion_control:
        caps.set_value("extmap-1", "http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01")
    transceiver = peer.emit("add-transceiver", GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY, caps)
    transceiver.set_property("do-nack", True)
    lock = threading.Lock()
    ice, errors, raw_frames = [], [], []
    exact_pts, metadata = {}, {}
    sinks = []

    def on_ice(_peer, index, candidate):
        with lock:
            ice.append((candidate, index))

    def on_rtp(pad, info):
        buffer = info.get_buffer()
        mapped, packet = GstRtp.RTPBuffer.map(buffer, Gst.MapFlags.READ)
        if mapped:
            try:
                if packet.get_marker():
                    segment = pad.get_sticky_event(Gst.EventType.SEGMENT, 0).parse_segment()
                    running = segment.to_running_time(Gst.Format.TIME, buffer.pts)
                    with lock:
                        if running in exact_pts:
                            errors.append("Ambiguous RTP running time")
                        exact_pts[running] = (packet.get_ssrc(), packet.get_timestamp())
                        if len(exact_pts) > 64:
                            errors.append("Unbounded receiver context map")
            finally:
                packet.unmap()
        return Gst.PadProbeReturn.OK

    def on_sample(sink):
        sample = sink.emit("pull-sample")
        buffer = sample.get_buffer()
        running = sample.get_segment().to_running_time(Gst.Format.TIME, buffer.pts)
        format = sample.get_caps().get_structure(0)
        with lock:
            raw_frames.append((running, buffer.extract_dup(0, 1)[0],
                               format.get_value("width"), format.get_value("height")))
        return Gst.FlowReturn.OK

    def on_pad(_peer, pad):
        if pad.direction != Gst.PadDirection.SRC:
            return
        try:
            decoder = "rtph264depay ! avdec_h264" if codec == "h264" else "rtpvp8depay ! vp8dec"
            decode = Gst.parse_bin_from_description(
                f"{decoder} ! videoconvert ! video/x-raw,format=BGR ! "
                "appsink name=decoded sync=false emit-signals=true max-buffers=1 drop=true", True)
            sink = decode.get_by_name("decoded")
            sink.connect("new-sample", on_sample)
            sinks.append(sink)
            receiver.add(decode)
            pad.add_probe(Gst.PadProbeType.BUFFER, on_rtp)
            if pad.link(decode.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
                raise RuntimeError("Receiver decode link refused")
            decode.sync_state_with_parent()
        except Exception as exc:
            with lock:
                errors.append(str(exc))

    def on_bus(_bus, message, _data):
        if message.type == Gst.MessageType.ERROR:
            error, _debug = message.parse_error()
            with lock:
                errors.append(str(error))
        return Gst.BusSyncReply.DROP

    peer.connect("on-ice-candidate", on_ice)
    peer.connect("pad-added", on_pad)
    receiver.get_bus().set_sync_handler(on_bus, None)
    results = []
    observed_captures = set()
    try:
        receiver.set_state(Gst.State.PLAYING)
        offer_reply = await asyncio.to_thread(sender._promise, lambda *args: peer.emit("create-offer", *args), None)
        offer = offer_reply.get_value("offer")
        await asyncio.to_thread(sender._promise, lambda *args: peer.emit("set-local-description", *args), offer)
        answer = await sender.answer(offer.sdp.as_text())
        _, _, GstSdp, _, _ = _gstreamer()
        _, answer_sdp = GstSdp.SDPMessage.new_from_text(answer["sdp"])
        answer_description = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, answer_sdp)
        await asyncio.to_thread(sender._promise,
                                lambda *args: peer.emit("set-remote-description", *args), answer_description)
        deadline = time.monotonic() + 12 + minimum_media_seconds
        media_started_at = None
        next_publish = 0.0
        published = 0
        missing_identity = None
        late_context = None
        checked_late = False
        while time.monotonic() < deadline and (
                len(results) < 12 or media_started_at is None
                or time.monotonic() - media_started_at < minimum_media_seconds):
            now = time.monotonic()
            if now >= next_publish:
                # Uniform, independently identifiable content survives lossy coding.
                value = 40 + published % 8 * 20
                frame = np.full((source_height, source_width, 3), value, dtype=np.uint8)
                publisher.publish(frame, frame, analysis_frame=frame, target_revision="fixture",
                                  capture=CaptureStamp("fixture-source", str(published), now, "fresh"))
                published += 1
                next_publish = now + 0.12
            with lock:
                candidates = list(ice)
                ice.clear()
            for candidate, index in candidates:
                await sender.add_ice_candidate(candidate, index)
            for event in sender.drain_events():
                if event["type"] == "ice-candidate":
                    payload = event["payload"]
                    peer.emit("add-ice-candidate", payload["sdpMLineIndex"], payload["candidate"])
                elif event["type"] == "frame-context":
                    context = event["payload"]
                    identity = (context["ssrc"], context["rtp_timestamp"])
                    if missing_identity is None:
                        missing_identity, late_context = identity, context
                    else:
                        metadata[identity] = context
                elif event["type"] == "error":
                    raise RuntimeError(event["stage"])
            with lock:
                frames = list(raw_frames)
                raw_frames.clear()
                if errors:
                    raise RuntimeError("; ".join(errors))
            if frames and media_started_at is None:
                media_started_at = time.monotonic()
            for running, luminance, width, height in frames:
                with lock:
                    identity = exact_pts.pop(running, None)
                if identity is None:
                    raise RuntimeError("Decoded frame lacks an exact RTP timestamp mapping")
                context = metadata.pop(identity, None)
                if identity == missing_identity:
                    if context is not None:
                        raise RuntimeError("Intentionally absent metadata was admitted")
                    # Late metadata cannot retroactively attach to a newer image.
                    metadata[identity] = late_context
                    checked_late = True
                    continue
                if context is None:
                    # Reliable signaling can arrive after decoding. Never guess.
                    results.append({"exact_rtp_mapping": True, "interactive": False})
                    continue
                capture_id = int(context["context"]["capture_id"])
                expected_size = (context["context"]["encoded_width"], context["context"]["encoded_height"])
                if (width, height) != expected_size:
                    raise RuntimeError(f"Decoded dimensions {(width, height)} differ from metadata {expected_size}")
                if capture_id in observed_captures:
                    raise RuntimeError("A publisher frame was duplicated while waiting for fresh input")
                observed_captures.add(capture_id)
                expected = 40 + capture_id % 8 * 20
                if abs(luminance - expected) > 6:
                    raise RuntimeError(f"Frame identity mismatch: pixels={luminance}, expected={expected}")
                results.append({"exact_rtp_mapping": True, "interactive": True,
                                "capture_id": capture_id, "decoded_value": luminance,
                                "decoded_dimensions": [width, height],
                                "ssrc": identity[0], "rtp_timestamp": identity[1]})
            await asyncio.sleep(0.01)
        if (len([row for row in results if row["interactive"]]) < 8 or not checked_late
                or peer.get_property("connection-state").value_nick != "connected"):
            raise RuntimeError("Insufficient connected, independently verified decoded frames")
        if congestion_control and not sender.snapshot()["congestion_controller_active"]:
            raise RuntimeError("Negotiation did not install the required congestion controller")
        if congestion_control and minimum_media_seconds >= 5 and not sender.snapshot()["congestion_feedback_events"]:
            raise RuntimeError("No negotiated transport-wide feedback reached the congestion controller")
        return {"passed": True, "codec": codec, "receiver_state": "connected",
                "scope": "loopback_ice_dtls_srtp_rtp_decoded_pixels", "frames": results,
                "source_dimensions": [source_width, source_height],
                "late_metadata_rejected": checked_late, "sender": sender.snapshot(),
                "estimator_feedback_observed": sender.snapshot()["bandwidth_estimates"] > 0,
                "media_observation_seconds": (time.monotonic() - media_started_at) if media_started_at else 0,
                "adaptation_qualified": False, "qgc_presentation_verified": False}
    finally:
        await asyncio.gather(sender.close(), sender.close())
        receiver.set_state(Gst.State.NULL)
        receiver.get_bus().set_sync_handler(None, None)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codecs", choices=("h264", "vp8"), nargs="+", default=["h264", "vp8"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--congestion-control", action="store_true", help="Require the installed TWCC/GCC path")
    parser.add_argument("--minimum-media-seconds", type=float, default=0,
                        help="Observe feedback longer; does not simulate a constrained link")
    parser.add_argument("--source-width", type=int, default=160)
    parser.add_argument("--source-height", type=int, default=120)
    args = parser.parse_args()
    report = {"results": []}
    try:
        for codec in args.codecs:
            report["results"].append(await qualify_peer(
                codec, congestion_control=args.congestion_control,
                source_width=args.source_width, source_height=args.source_height,
                minimum_media_seconds=args.minimum_media_seconds))
    except Exception as exc:
        report["error"] = str(exc)
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 2 if "error" in report else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
