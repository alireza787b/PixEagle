"""Optional, single-peer GStreamer sender consuming the shared FramePublisher.

The signaling manager owns authentication, capacity and this peer's lifetime.
This module owns no socket or camera. Native-client capability remains gated
until receiver presentation, congestion control and packaging are qualified.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit

from pydantic import ValidationError

from classes.adaptive_quality_engine import AdaptiveQualityEngine
from classes.gstreamer_frame_association import GStreamerFrameAssociation
from classes.gstreamer_runtime import load_gstreamer as _gstreamer
from classes.streaming_presentation_feedback import VideoPresentationFeedback

TWCC_URI = "http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01"


class GStreamerWebRTCPeer:
    """Bounded media worker; all potentially blocking setup stays off asyncio."""

    def __init__(self, publisher, *, fps: int = 20, bitrate_bps: int = 1_000_000,
                 maximum_bitrate_bps: int = 4_000_000, prefer_osd: bool = True,
                 require_congestion_control: bool = True, ice_servers: list[dict] | None = None):
        if (any(type(value) is not int for value in (fps, bitrate_bps, maximum_bitrate_bps))
                or not 1 <= fps <= 60 or not 64_000 <= bitrate_bps <= maximum_bitrate_bps <= 8_000_000):
            raise ValueError("Invalid media rate limits")
        self.publisher = publisher
        self.fps = fps
        self.bitrate_bps = bitrate_bps
        self.maximum_bitrate_bps = maximum_bitrate_bps
        self.prefer_osd = prefer_osd
        # False is reserved for the explicit camera-free transport qualification.
        self.require_congestion_control = require_congestion_control
        self._ice_servers = [dict(server) for server in ice_servers or []]
        self.association = GStreamerFrameAssociation()
        self._selection_client = "webrtc:" + self.association.epoch
        self._quality = AdaptiveQualityEngine()
        self._quality.register_client(self._selection_client)
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="webrtc-media")
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._events: deque[dict] = deque()
        self._frames: deque[tuple[dict, float]] = deque(maxlen=32)
        self._pipeline = self._webrtc = self._source = self._encoder = None
        self._producer = None
        self._close_task = None
        self._negotiation_started = False
        self._source_identity = None
        self._codec = None
        self._twcc_id = None
        self._error = None
        self._submitted = self._associated = self._dropped_metadata = 0
        self._connected = False
        self._challenge = None
        self._congestion_controller_active = False
        self._bandwidth_estimates = 0
        self._congestion_feedback_events = 0
        self._effective_bitrate_bps = bitrate_bps
        self._delivery_size = None
        self._packet_recovery_negotiated = False

    def update_challenge(self, token: str) -> None:
        """Echo a prior client token to bound age without comparing host clocks."""
        if (not isinstance(token, str) or not 16 <= len(token) <= 64
                or any(character not in "0123456789abcdef" for character in token)):
            raise ValueError("Invalid frame age challenge")
        with self._lock:
            if not self._stop.is_set():
                self._challenge = token

    def update_presentation(self, payload) -> bool:
        """Optional peer-local QoS feedback; it never authorizes a selection."""
        if self._stop.is_set() or self.publisher is None:
            return False
        try:
            feedback = VideoPresentationFeedback.model_validate(payload)
        except ValidationError:
            return False
        self._quality.report_presentation_feedback(
            self._selection_client, feedback, max_age_ms=self.publisher.selection_max_age_ms)
        return True

    async def _run(self, function, *args):
        return await asyncio.get_running_loop().run_in_executor(self._worker, function, *args)

    def _event(self, event: dict) -> None:
        with self._lock:
            if self._stop.is_set():
                return
            if len(self._events) >= 64:
                self._error = "signaling_backlog"
                self._stop.set()
                return
            self._events.append(event)

    def _fail(self, reason: str) -> None:
        with self._lock:
            if self._error is None and not self._stop.is_set():
                self._error = reason
                self._events.append({"type": "error", "stage": reason})
        self._stop.set()

    def drain_events(self) -> list[dict]:
        """Called by the existing authenticated signaling owner, never a new socket."""
        now = time.monotonic()
        with self._lock:
            events = list(self._events)
            self._events.clear()
            while self._frames:
                event, observed_at = self._frames.popleft()
                context = event["payload"]["context"]
                for key in ("capture_age_ms", "publication_age_ms"):
                    if context.get(key) is not None:
                        context[key] += max(0.0, now - observed_at) * 1000
                events.append(event)
        return events

    def snapshot(self) -> dict:
        with self._lock:
            result = {"provider": "gstreamer", "codec": self._codec,
                    "connected": self._connected, "frames_submitted": self._submitted,
                    "access_units_associated": self._associated,
                    "metadata_dropped": self._dropped_metadata,
                    "pending_metadata": len(self._frames), "error": self._error,
                    "congestion_control_required": self.require_congestion_control,
                    "congestion_controller_active": self._congestion_controller_active,
                    "bandwidth_estimates": self._bandwidth_estimates,
                    "congestion_feedback_events": self._congestion_feedback_events,
                    "encoder_target_bitrate_bps": self._effective_bitrate_bps,
                    "packet_recovery_negotiated": self._packet_recovery_negotiated,
                    "delivery_dimensions": self._delivery_size,
                    "presentation_verified": False}
        policy = self._quality.get_client_state(self._selection_client)
        result["delivery_policy"] = {key: policy[key] for key in (
            "profile", "fps", "resolution_scale", "adjustment_reason", "encoded_feedback_age_ms", "encoded_pipeline_ms",
            "associated_encoded_fps",
            "receiver_feedback_age_ms", "receiver_verified_fps", "receiver_presented_fps", "receiver_pressure")}
        return result

    @staticmethod
    def _promise(action, *args):
        Gst, *_ = _gstreamer()
        completed = threading.Event()
        promise = Gst.Promise.new_with_change_func(lambda *_: completed.set(), None, None)
        action(*args, promise)
        if not completed.wait(5):
            promise.interrupt()
            raise TimeoutError("WebRTC description operation timed out")
        if promise.wait() != Gst.PromiseResult.REPLIED:
            raise RuntimeError("WebRTC description operation did not reply")
        reply = promise.get_reply()
        if reply and reply.has_field("error"):
            raise RuntimeError("WebRTC description operation refused")
        return reply

    @staticmethod
    def _select_offer(sdp: str):
        if not isinstance(sdp, str) or not 1 <= len(sdp.encode()) <= 65_536:
            raise ValueError("Invalid offer size")
        Gst, _, GstSdp, _, _ = _gstreamer()
        result, message = GstSdp.SDPMessage.new_from_text(sdp)
        if result != GstSdp.SDPResult.OK:
            raise ValueError("Invalid SDP offer")
        videos = [message.get_media(i) for i in range(message.medias_len())
                  if message.get_media(i).get_media() == "video"]
        if len(videos) != 1 or message.medias_len() != 1:
            raise ValueError("One receive-only video media section is required")
        media = videos[0]
        if (media.get_port() == 0 or media.get_attribute_val("inactive") is not None
                or media.get_attribute_val("sendonly") is not None):
            raise ValueError("Offer does not receive video")
        supported = []
        h264_ready = all(Gst.ElementFactory.find(name) is not None
                         for name in ("x264enc", "h264parse", "rtph264pay"))
        vp8_ready = all(Gst.ElementFactory.find(name) is not None for name in ("vp8enc", "rtpvp8pay"))
        for i in range(media.formats_len()):
            payload = media.get_format(i)
            if not payload.isdecimal() or not 0 <= int(payload) <= 127:
                continue
            caps = media.get_caps_from_media(int(payload))
            if caps is None or caps.is_empty():
                continue
            fields = caps.get_structure(0)
            encoding = fields.get_string("encoding-name")
            if encoding == "H264" and h264_ready:
                profile = fields.get_string("profile-level-id") or "42e01f"
                if (fields.get_string("packetization-mode") != "1" or len(profile) != 6
                        or not profile.lower().startswith("42")):
                    continue
                try:
                    if int(profile[-2:], 16) < 31:
                        continue
                except ValueError:
                    continue
                supported.append((0, "h264", int(payload)))
            elif encoding == "VP8" and vp8_ready:
                supported.append((1, "vp8", int(payload)))
        if not supported:
            raise ValueError("Offer has no supported H.264 baseline or VP8 codec")
        _, codec, payload = min(supported)
        twcc_id = None
        for i in range(media.attributes_len()):
            attribute = media.get_attribute(i)
            if attribute.key == "extmap":
                parts = attribute.value.split()
                if len(parts) >= 2 and parts[1] == TWCC_URI:
                    extension_id = parts[0].split("/")[0]
                    if extension_id.isdecimal() and 1 <= int(extension_id) <= 14:
                        twcc_id = int(extension_id)
        return message, codec, payload, twcc_id

    async def answer(self, offer_sdp: str) -> dict:
        if self._stop.is_set() or self._negotiation_started:
            raise RuntimeError("Peer is closed or already negotiated")
        self._negotiation_started = True
        try:
            return await self._run(self._answer, offer_sdp)
        except BaseException:
            self._stop.set()
            raise

    def _answer(self, offer_sdp: str) -> dict:
        Gst, GstRtp, _, GstWebRTC, _ = _gstreamer()
        message, codec, payload, self._twcc_id = self._select_offer(offer_sdp)
        if self.require_congestion_control and (
                not self._twcc_id or Gst.ElementFactory.find("rtpgccbwe") is None):
            raise RuntimeError("TWCC and rtpgccbwe are required for adaptive delivery")
        if self._stop.is_set():
            raise RuntimeError("Peer was cancelled")
        self._codec = codec
        # Match GStreamer's webrtcsink real-time rate-control buffers. VBR's
        # multi-second buffers/unbounded intra bursts defeat a narrow paced link.
        encoder = (
            f"x264enc name=encoder tune=zerolatency speed-preset=ultrafast bframes=0 "
            f"bitrate={self.bitrate_bps // 1000} key-int-max={self.fps} vbv-buf-capacity=120 ! "
            "video/x-h264,profile=constrained-baseline ! h264parse ! rtph264pay config-interval=-1"
            if codec == "h264" else
            f"vp8enc name=encoder deadline=1 cpu-used=8 lag-in-frames=0 "
            f"target-bitrate={self.bitrate_bps} keyframe-max-dist={self.fps} end-usage=cbr "
            "buffer-initial-size=100 buffer-optimal-size=120 buffer-size=150 "
            "max-intra-bitrate=250 error-resilient=default ! rtpvp8pay picture-id-mode=15-bit"
        )
        extension_caps = f",extmap-{self._twcc_id}=(string){TWCC_URI}" if self._twcc_id else ""
        self._pipeline = Gst.parse_launch(
            "webrtcbin name=peer bundle-policy=max-bundle "
            "appsrc name=source format=time is-live=true block=false max-buffers=1 leaky-type=downstream ! "
            "queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 leaky=downstream ! "
            f"videoconvert ! {encoder} name=pay pt={payload} mtu=1200 ! "
            f"application/x-rtp,media=video,encoding-name={'H264' if codec == 'h264' else 'VP8'},"
            f"clock-rate=90000,payload={payload},rtcp-fb-nack=(boolean)true,"
            f"rtcp-fb-nack-pli=(boolean)true{extension_caps} ! peer."
        )
        self._webrtc = self._pipeline.get_by_name("peer")
        transceiver = self._webrtc.emit("get-transceiver", 0)
        if transceiver is not None and transceiver.find_property("do-nack") is not None:
            transceiver.set_property("do-nack", True)
        self._configure_ice()
        self._source = self._pipeline.get_by_name("source")
        self._encoder = self._pipeline.get_by_name("encoder")
        payloader = self._pipeline.get_by_name("pay")
        if self._twcc_id:
            extension = GstRtp.RTPHeaderExtension.create_from_uri(TWCC_URI)
            if extension is None:
                raise RuntimeError("TWCC RTP extension is unavailable")
            extension.set_id(self._twcc_id)
            payloader.emit("add-extension", extension)
        self._webrtc.connect("on-ice-candidate", self._ice_candidate)
        self._webrtc.connect("notify::connection-state", self._connection_changed)
        if self.require_congestion_control:
            self._webrtc.connect("request-aux-sender", self._congestion_sender)
        epoch = self.association.epoch
        payloader.get_static_pad("src").add_probe(
            Gst.PadProbeType.BUFFER | Gst.PadProbeType.BUFFER_LIST, self._rtp_probe, epoch)
        self._pipeline.get_bus().set_sync_handler(self._bus_message, None)
        if self._pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("WebRTC pipeline failed to start")
        remote = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, message)
        self._promise(lambda *args: self._webrtc.emit("set-remote-description", *args), remote)
        answer = self._promise(lambda *args: self._webrtc.emit("create-answer", *args), None)
        description = answer.get_value("answer") if answer else None
        if description is None:
            raise RuntimeError("WebRTC answer is missing")
        # Keep the parent SDP wrapper alive while inspecting borrowed media/attributes.
        answer_sdp = description.sdp
        answer_media = answer_sdp.get_media(0)
        with self._lock:
            self._packet_recovery_negotiated = any(
                attribute.key == "rtcp-fb" and attribute.value.split()[1:] == ["nack"]
                for attribute in (answer_media.get_attribute(index) for index in range(answer_media.attributes_len())))
        if self.require_congestion_control:
            media = answer_media
            expected_extension = f"{self._twcc_id} {TWCC_URI}"
            extensions = []
            for index in range(media.attributes_len()):
                attribute = media.get_attribute(index)
                if attribute.key == "extmap":
                    extensions.append(attribute.value)
            if expected_extension not in extensions:
                raise RuntimeError("Transport-wide congestion feedback was not negotiated")
        self._promise(lambda *args: self._webrtc.emit("set-local-description", *args), description)
        if self._stop.is_set():
            raise RuntimeError("Peer was cancelled")
        self._producer = threading.Thread(target=self._produce, name="webrtc-frames", daemon=True)
        self._producer.start()
        return {"type": "answer", "sdp": answer_sdp.as_text(),
                "media_capabilities": {"provider": "gstreamer", "codec": codec,
                                       "native_frame_association": False,
                                       "presentation_verified": False}}

    def _configure_ice(self):
        for server in self._ice_servers:
            urls = server.get("urls", [])
            if isinstance(urls, str):
                urls = [urls]
            for url in urls:
                if not isinstance(url, str) or len(url) > 2048 or ":" not in url:
                    raise ValueError("Invalid ICE server")
                scheme, address = url.split(":", 1)
                parsed = urlsplit("//" + address.removeprefix("//"))
                if scheme not in ("stun", "turn", "turns") or not parsed.hostname or parsed.username:
                    raise ValueError("Unsupported ICE server")
                authority = parsed.netloc
                if scheme == "stun":
                    self._webrtc.set_property("stun-server", "stun://" + authority)
                else:
                    username, credential = server.get("username"), server.get("credential")
                    if not isinstance(username, str) or not isinstance(credential, str):
                        raise ValueError("TURN credentials are required")
                    userinfo = quote(username, safe="") + ":" + quote(credential, safe="")
                    uri = f"{scheme}://{userinfo}@{authority}"
                    if parsed.query:
                        uri += "?" + parsed.query
                    if not self._webrtc.emit("add-turn-server", uri):
                        raise ValueError("TURN configuration refused")

    def _ice_candidate(self, _peer, index, candidate):
        self._event({"type": "ice-candidate", "payload": {
            "candidate": candidate, "sdpMLineIndex": index}})

    def _connection_changed(self, peer, _property):
        state = peer.get_property("connection-state").value_nick
        with self._lock:
            self._connected = state == "connected"
        self._event({"type": "connection-state", "state": state})
        if state in ("failed", "closed"):
            self._fail("transport_failed")

    def _congestion_sender(self, _peer, _transport):
        Gst, *_ = _gstreamer()
        controller = Gst.ElementFactory.make("rtpgccbwe")
        controller.set_property("min-bitrate", 64_000)
        controller.set_property("max-bitrate", self.maximum_bitrate_bps)
        controller.set_property("estimated-bitrate", self.bitrate_bps)
        controller.connect("notify::estimated-bitrate", self._bitrate_changed)
        controller.get_static_pad("src").add_probe(Gst.PadProbeType.EVENT_UPSTREAM, self._congestion_feedback)
        with self._lock:
            self._congestion_controller_active = True
        return controller

    def _congestion_feedback(self, _pad, info):
        Gst, *_ = _gstreamer()
        event = info.get_event()
        structure = event.get_structure() if event is not None else None
        if structure is not None and structure.get_name() == "RTPTWCCPackets":
            with self._lock:
                self._congestion_feedback_events += 1
        return Gst.PadProbeReturn.OK

    def _bitrate_changed(self, controller, _property):
        if self._stop.is_set():
            return
        bitrate = min(self.maximum_bitrate_bps, max(64_000, controller.get_property("estimated-bitrate")))
        self._encoder.set_property("bitrate" if self._codec == "h264" else "target-bitrate",
                                   bitrate // 1000 if self._codec == "h264" else bitrate)
        with self._lock:
            self._bandwidth_estimates += 1
            self._effective_bitrate_bps = bitrate

    def _bus_message(self, _bus, message, _data):
        Gst, *_ = _gstreamer()
        if message.type == Gst.MessageType.ERROR:
            self._fail("pipeline_error")
        elif message.type == Gst.MessageType.EOS:
            self._fail("source_ended")
        # No GLib main loop or unbounded bus queue in the API process.
        return Gst.BusSyncReply.DROP

    def _rtp_probe(self, pad, info, epoch):
        Gst, GstRtp, *_ = _gstreamer()
        segment_event = pad.get_sticky_event(Gst.EventType.SEGMENT, 0)
        if segment_event is None or self._stop.is_set():
            return Gst.PadProbeReturn.OK
        buffers = []
        if info.type & Gst.PadProbeType.BUFFER:
            buffers.append(info.get_buffer())
        elif info.type & Gst.PadProbeType.BUFFER_LIST:
            buffer_list = info.get_buffer_list()
            buffers.extend(buffer_list.get(i) for i in range(buffer_list.length()))
        for buffer in buffers:
            running_time = segment_event.parse_segment().to_running_time(Gst.Format.TIME, buffer.pts)
            mapped, packet = GstRtp.RTPBuffer.map(buffer, Gst.MapFlags.READ)
            if not mapped:
                continue
            try:
                association = self.association.observe_packet(
                    epoch, running_time, packet.get_ssrc(), packet.get_timestamp(), marker=packet.get_marker())
            finally:
                packet.unmap()
            if association:
                context = association.metadata()
                observed_at = time.monotonic()
                submitted_at = context.pop("submitted_at_monotonic")
                requested_fps = context.pop("requested_fps")
                if self.require_congestion_control:
                    with self._lock:
                        bitrate = self._effective_bitrate_bps
                    self._quality.report_encoded_frame(
                        self._selection_client, bitrate_bps=bitrate,
                        width=context["encoded_width"], height=context["encoded_height"],
                        fps=requested_fps, pipeline_seconds=max(0.0, observed_at - submitted_at))
                for key in ("capture_age_ms", "publication_age_ms"):
                    if context.get(key) is not None:
                        context[key] += max(0.0, observed_at - submitted_at) * 1000
                event = {"type": "frame-context", "payload": {
                    "provider_epoch": association.epoch, "ssrc": association.ssrc,
                    "rtp_timestamp": association.rtp_timestamp, "context": context}}
                with self._lock:
                    if self._stop.is_set():
                        continue
                    if len(self._frames) == self._frames.maxlen:
                        self._dropped_metadata += 1
                    self._frames.append((event, observed_at))
                    self._associated += 1
        return Gst.PadProbeReturn.OK

    def _produce(self):
        Gst, _, _, _, GstVideo = _gstreamer()
        last_frame = None
        last_pts = -1
        last_caps = None
        next_frame_at = 0.0
        try:
            while not self._stop.wait(0.005):
                now = time.monotonic()
                if not self._connected or now < next_frame_at:
                    continue
                stamped = self.publisher.get_latest(prefer_osd=self.prefer_osd)
                if stamped is None or stamped.cache_identity == last_frame:
                    continue
                source_frame_identity = stamped.cache_identity
                identity = (stamped.stream_id, stamped.stream_epoch, stamped.capture.source_epoch)
                if self._source_identity is not None and identity != self._source_identity:
                    self._fail("source_changed")
                    return
                self._source_identity = identity
                source_height, source_width = stamped.frame.shape[:2]
                scale = min(1.0, 1280 / source_width, 720 / source_height)
                fps = float(self.fps)
                if scale < 0.25:
                    self._fail("unsupported_source_dimensions")
                    return
                stamped = self.publisher.delivery_variant(stamped, scale)
                if self.require_congestion_control:
                    policy = self._quality.get_client_policy(self._selection_client)
                    stamped = self.publisher.delivery_variant(stamped, policy["resolution_scale"])
                    fps = min(fps, policy["fps"])
                pixels = stamped.frame
                height, width = pixels.shape[:2]
                if (pixels.dtype.name != "uint8" or pixels.ndim != 3 or pixels.shape[2] != 3
                        or width % 2 or height % 2 or width > 1280 or height > 720):
                    self._fail("unsupported_source_format")
                    return
                if not self.publisher.is_current(stamped):
                    continue
                caps_identity = (width, height, round(fps * 10))
                if caps_identity != last_caps:
                    self._source.set_property("caps", Gst.Caps.from_string(
                        f"video/x-raw,format=BGR,width={width},height={height},framerate={caps_identity[2]}/10"))
                    last_caps = caps_identity
                pts = max(last_pts + 1, self._pipeline.get_clock().get_time() - self._pipeline.get_base_time())
                submitted_at = time.monotonic()
                context = stamped.provenance(submitted_at)
                if stamped.selection_geometry:
                    context["selection_geometry"] = dict(stamped.selection_geometry)
                context["submitted_at_monotonic"] = submitted_at
                context["requested_fps"] = fps
                with self._lock:
                    context["age_bound_token"] = self._challenge
                epoch = self.association.epoch
                # Unlike ACK-paced JPEG, RTP can have many frames in flight.
                # Retain its existing selection age window within shared byte limits.
                retention = min(self.publisher.selection_max_frames,
                                math.ceil(self.fps * self.publisher.selection_max_age_ms / 1000) + 2)
                self.publisher.pin_selection_delivery(stamped, self._selection_client, frame_limit=retention)
                if not self.association.submit(epoch, pts, context):
                    continue
                payload = pixels.tobytes()
                buffer = Gst.Buffer.new_allocate(None, len(payload), None)
                buffer.fill(0, payload)
                # NumPy BGR rows need not match GStreamer's four-byte padding.
                GstVideo.buffer_add_video_meta_full(
                    buffer, GstVideo.VideoFrameFlags.NONE, GstVideo.VideoFormat.BGR,
                    width, height, 1, [0, 0, 0, 0], [width * 3, 0, 0, 0])
                buffer.pts = pts
                buffer.duration = int(Gst.SECOND / fps)
                if self._stop.is_set() or not self.publisher.is_current(stamped):
                    self.association.discard(epoch, pts)
                    continue
                if self._source.emit("push-buffer", buffer) != Gst.FlowReturn.OK:
                    self.association.discard(epoch, pts)
                    self._fail("encoder_input_refused")
                    return
                with self._lock:
                    self._submitted += 1
                    self._delivery_size = (width, height)
                last_frame, last_pts = source_frame_identity, pts
                next_frame_at = now + 1 / fps
        except Exception:
            self._fail("frame_worker_failed")

    async def add_ice_candidate(self, candidate: str, index: int) -> None:
        if (not isinstance(candidate, str) or len(candidate) > 4096 or "\n" in candidate
                or isinstance(index, bool) or index != 0):
            raise ValueError("Invalid ICE candidate")
        if self._stop.is_set():
            return
        await self._run(self._add_ice_candidate, candidate, index)

    def _add_ice_candidate(self, candidate, index):
        if self._stop.is_set() or self._webrtc is None:
            return
        self._webrtc.emit("add-ice-candidate", index, candidate)

    async def close(self) -> None:
        """Concurrent shutdown callers join one teardown; no retired frame can emit."""
        if self._close_task is None:
            self._stop.set()
            self.association.reset()
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self):
        try:
            await self._run(self._release)
        finally:
            self._worker.shutdown(wait=False, cancel_futures=True)

    def _release(self):
        if self._pipeline is not None:
            Gst, *_ = _gstreamer()
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline.get_bus().set_sync_handler(None, None)
        if self._producer is not None:
            self._producer.join(timeout=1)
            if self._producer.is_alive():
                raise RuntimeError("Frame worker did not stop")
        self._pipeline = self._webrtc = self._source = self._encoder = None
        if self.publisher is not None:
            self.publisher.unpin_selection_client(self._selection_client)
        with self._lock:
            self._connected = False
            self._frames.clear()
            self._events.clear()
