"""Independent receiver half of the camera-free GStreamer qualification tool."""

import threading


def qualify_receiver_packets(codec: str, epoch: str, observations: list, packet_bytes: list) -> dict:
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstRtp", "1.0")
    from gi.repository import Gst, GstRtp

    decoders = {"h264": ("H264", "rtph264depay ! avdec_h264"), "vp8": ("VP8", "rtpvp8depay ! vp8dec")}
    encoding, decoder = decoders[codec]
    pipeline = Gst.parse_launch(
        "appsrc name=source format=time is-live=true do-timestamp=true "
        f"caps=application/x-rtp,media=video,encoding-name={encoding},clock-rate=90000,payload=96 ! "
        f"rtpjitterbuffer name=jitter latency=50 ! {decoder} ! "
        "videoconvert ! video/x-raw,format=I420 ! appsink name=sink sync=false max-buffers=8 drop=false"
    )
    # This finite fixture holds at most five contexts; production queues need
    # the same explicit age/capacity bounds as the sender association helper.
    contexts = {(epoch, row["ssrc"], row["rtp_timestamp"]): row for row in observations}
    missing = next(key for key, row in contexts.items() if row["metadata"]["frame_id"] == 1)
    late_context = contexts.pop(missing)
    exact_pts = {}
    probe_errors = []
    lock = threading.Lock()

    def observe_rtp(pad, info):
        buffer = info.get_buffer()
        mapped, rtp = GstRtp.RTPBuffer.map(buffer, Gst.MapFlags.READ)
        if not mapped:
            probe_errors.append("Invalid receiver RTP buffer")
            return Gst.PadProbeReturn.OK
        try:
            if rtp.get_marker():
                segment_event = pad.get_sticky_event(Gst.EventType.SEGMENT, 0)
                running_time = segment_event.parse_segment().to_running_time(Gst.Format.TIME, buffer.pts)
                identity = (epoch, rtp.get_ssrc(), rtp.get_timestamp())
                with lock:
                    if running_time in exact_pts or len(exact_pts) >= 8:
                        probe_errors.append("Ambiguous or unbounded receiver PTS map")
                    else:
                        exact_pts[running_time] = identity
        finally:
            rtp.unmap()
        return Gst.PadProbeReturn.OK

    pipeline.get_by_name("jitter").get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, observe_rtp)
    source, sink = pipeline.get_by_name("source"), pipeline.get_by_name("sink")
    results = []
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Receiver pipeline could not start")
        reordered = list(packet_bytes)
        reordered[1], reordered[2] = reordered[2], reordered[1]
        for payload in reordered:
            buffer = Gst.Buffer.new_allocate(None, len(payload), None)
            buffer.fill(0, payload)
            if source.emit("push-buffer", buffer) != Gst.FlowReturn.OK:
                raise RuntimeError("Receiver appsrc refused a packet")
        source.emit("end-of-stream")
        while True:
            sample = sink.emit("try-pull-sample", 3 * Gst.SECOND)
            if sample is None:
                if not sink.get_property("eos"):
                    raise RuntimeError("Receiver did not finish decoding")
                break
            buffer = sample.get_buffer()
            running_time = sample.get_segment().to_running_time(Gst.Format.TIME, buffer.pts)
            with lock:
                identity = exact_pts.pop(running_time, None)
            if identity is None:
                raise RuntimeError("Decoded PTS has no exact RTP association")
            context = contexts.pop(identity, None)
            frame_id = context["metadata"]["frame_id"] if context else None
            # Uniform source luminance independently identifies decoded content.
            luminance = buffer.extract_dup(0, 1)[0]
            if context and abs(luminance - (32 + frame_id * 16)) > 3:
                raise RuntimeError("Associated metadata does not match decoded pixels")
            results.append({"receiver_running_time_ns": running_time, "ssrc": identity[1],
                            "rtp_timestamp": identity[2], "frame_id": frame_id,
                            "decoded_luminance": luminance,
                            "interactive_mapping_available": context is not None})
            if identity == missing:
                # Late metadata must never label another decoded frame.
                contexts[missing] = late_context
        if probe_errors:
            raise RuntimeError("; ".join(probe_errors))
        if [row["frame_id"] for row in results] != [0, None, 3, 4, 5]:
            raise RuntimeError("Missing/delayed metadata or RTP reordering changed frame identity")
        if missing not in contexts:
            raise RuntimeError("Late metadata was incorrectly consumed by another frame")
        if any(key[0] != epoch for key in contexts):
            raise RuntimeError("Wrong source epoch admitted")
        return {"passed": True, "scope": "independent_jitterbuffer_to_decoded_pts",
                "presentation_verified": False, "frames": results}
    finally:
        pipeline.set_state(Gst.State.NULL)
