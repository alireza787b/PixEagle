# src/classes/gstreamer_http_handler.py

import logging
import asyncio
import platform

# By default, we assume we cannot import PyGObject.
HAS_GI = False
GStreamerHTTPHandler = None

# Only attempt GI import on Linux (or wherever user has PyGObject installed).
if platform.system().lower().startswith("linux"):
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst, GLib

        HAS_GI = True

        class GStreamerHTTPHandler:
            """
            Optional pipeline for H.264 streaming over HTTP chunked response (MPEG-TS).
            Only functional if PyGObject is installed on a Linux-like environment.
            """

            def __init__(self, width, height, framerate, bitrate_kbps, speed_preset, tune, key_int_max):
                """
                Args:
                    width (int): The streaming width.
                    height (int): The streaming height.
                    framerate (int): The streaming framerate (FPS).
                    bitrate_kbps (int): The encoder bitrate in kbps.
                    speed_preset (str): e.g. "ultrafast"
                    tune (str): e.g. "zerolatency"
                    key_int_max (int): Keyframe interval.
                """
                Gst.init(None)
                self.width = width
                self.height = height
                self.framerate = framerate
                self.bitrate = bitrate_kbps
                self.speed_preset = speed_preset
                self.tune = tune
                self.key_int_max = key_int_max

                self.pipeline = None
                self.appsrc = None
                self.data_queue = asyncio.Queue()

                self._build_pipeline()

            def _build_pipeline(self):
                self.pipeline = Gst.Pipeline.new("gst-http-pipeline")

                self.appsrc = Gst.ElementFactory.make("appsrc", "appsrc")
                if not self.appsrc:
                    raise RuntimeError("Failed to create GStreamer 'appsrc' element.")

                # Create caps for BGR input frames
                caps = Gst.caps_from_string(
                    f"video/x-raw,format=BGR,width={self.width},height={self.height},framerate={self.framerate}/1"
                )
                self.appsrc.set_property("caps", caps)
                self.appsrc.set_property("is-live", True)
                self.appsrc.set_property("do-timestamp", True)

                convert = Gst.ElementFactory.make("videoconvert", "videoconvert")
                encoder = Gst.ElementFactory.make("x264enc", "encoder")
                if not encoder:
                    raise RuntimeError("Failed to create 'x264enc'. Check your GStreamer installation.")
                # Configure x264enc
                encoder.set_property("bitrate", self.bitrate)  # kbps
                encoder.set_property("speed-preset", self.speed_preset)
                encoder.set_property("tune", self.tune)
                encoder.set_property("key-int-max", self.key_int_max)

                h264parse = Gst.ElementFactory.make("h264parse", "h264parse")
                muxer = Gst.ElementFactory.make("mpegtsmux", "mpegtsmux")
                appsink = Gst.ElementFactory.make("appsink", "appsink")
                appsink.set_property("emit-signals", True)
                appsink.set_property("sync", False)
                appsink.set_property("drop", True)
                appsink.connect("new-sample", self._on_new_sample)

                for comp in [self.appsrc, convert, encoder, h264parse, muxer, appsink]:
                    self.pipeline.add(comp)

                # Link the elements
                self.appsrc.link(convert)
                convert.link(encoder)
                encoder.link(h264parse)
                h264parse.link(muxer)
                muxer.link(appsink)

                self.pipeline.set_state(Gst.State.PLAYING)
                logging.info("GStreamerHTTPHandler pipeline started (H.264 HTTP).")

            def _on_new_sample(self, sink):
                sample = sink.emit("pull-sample")
                if sample is None:
                    return Gst.FlowReturn.ERROR
                buf = sample.get_buffer()
                success, mapinfo = buf.map(Gst.MapFlags.READ)
                if success:
                    chunk = mapinfo.data
                    buf.unmap(mapinfo)
                    # Put chunk into the async queue
                    asyncio.run_coroutine_threadsafe(
                        self.data_queue.put(chunk), asyncio.get_event_loop()
                    )
                    return Gst.FlowReturn.OK
                return Gst.FlowReturn.ERROR

            def push_frame(self, frame):
                """
                Push a BGR frame into the pipeline via appsrc.
                """
                if frame is None:
                    return
                data = frame.tobytes()
                buf = Gst.Buffer.new_allocate(None, len(data), None)
                duration_ns = int(1e9 / self.framerate)
                now_ns = int(asyncio.get_event_loop().time() * 1e9)
                buf.pts = now_ns
                buf.dts = now_ns
                buf.set_duration(duration_ns)
                buf.fill(0, data)
                self.appsrc.emit("push-buffer", buf)

            async def get_chunks(self):
                """
                Async generator for retrieving H.264 TS chunks from the pipeline.
                """
                while True:
                    chunk = await self.data_queue.get()
                    if chunk == b'':
                        break
                    yield chunk

            def stop(self):
                """
                Gracefully stop the pipeline.
                """
                if self.pipeline:
                    self.appsrc.emit("end-of-stream")
                    self.pipeline.set_state(Gst.State.NULL)
                    logging.info("GStreamerHTTPHandler pipeline stopped.")

        # If we reach here, we have GStreamerHTTPHandler defined.
        GStreamerHTTPHandler = GStreamerHTTPHandler

    except ImportError as e:
        logging.warning(f"PyGObject or GStreamer not available: {e}")
        HAS_GI = False
else:
    logging.info("Non-Linux system detected; skipping PyGObject import.")


def get_http_handler_or_none():
    """
    Helper function to create a GStreamerHTTPHandler if possible.
    Otherwise returns None, with a warning log.
    """
    if not HAS_GI or not GStreamerHTTPHandler:
        logging.warning("GStreamerHTTPHandler not available on this system.")
        return None

    from classes.parameters import Parameters
    return GStreamerHTTPHandler(
        width=Parameters.GSTREAMER_WIDTH,
        height=Parameters.GSTREAMER_HEIGHT,
        framerate=Parameters.GSTREAMER_FRAMERATE,
        bitrate_kbps=Parameters.GSTREAMER_BITRATE,
        speed_preset=Parameters.GSTREAMER_SPEED_PRESET,
        tune=Parameters.GSTREAMER_TUNE,
        key_int_max=Parameters.GSTREAMER_KEY_INT_MAX,
    )
