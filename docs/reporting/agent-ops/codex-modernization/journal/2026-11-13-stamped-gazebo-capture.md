# Stamped Gazebo capture

Added an optional launcher-managed image source using actual Gazebo RGB pixels
and their original simulator timestamps. The existing asynchronous capture owner
feeds normal analysis, tracking and FramePublisher delivery. There is no second
tracker, synthesized target or parallel QGC picture.

The private socket envelope is bounded and source-bound. Host receipt and source
sample time remain separate through capture, cached frames and image-measurement
serialization. Ordinary camera/replay paths and public defaults are preserved;
`VideoSource.GAZEBO_CAMERA` defaults to null.

Software checks: 362 video/provenance/profile regressions passed before three
additional capture/profile checks; the final focused group passed 67 cases.
The asynchronous capture/provenance regressions passed 189 cases after updating
private helper references; a shared-backoff/explicit-release regression was added.
Schema generation is updated with the same source contract. These results do
not establish actual Gazebo camera timing or native fixed-wing flight readiness.
Provider integration, source-time attitude alignment and full application
qualification remain the next gates.
