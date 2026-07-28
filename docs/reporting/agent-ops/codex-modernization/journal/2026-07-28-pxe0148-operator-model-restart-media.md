# PXE-0148: Operator Model, Restart, And Media Feedback

Four tester reports shared one boundary problem: the dashboard was presenting
implementation states instead of actionable operator outcomes. Model collision
and store contention both looked busy, process Quit bypassed the maintained
restart lifecycle, routine video labels ignored OSD visibility, and WebRTC used
one deadline across several asynchronous negotiation stages.

This slice keeps the existing ownership boundaries. ModelManager remains the
only artifact naming and no-overwrite authority; the API now preserves its
structured outcome. The existing typed system-restart action is the only
dashboard process lifecycle command, and a rejection remains visible to the
operator. OSD status controls routine browser labels but not safety or
interaction feedback. WebRTC remains aiortc plus browser RTCPeerConnection,
with deadlines reset only after verified stage progress and failed transports
closed.

Recorded VPS evidence showed that signaling, offer handling, track creation,
answer generation, and candidate exchange succeeded. The server answer took
about five seconds while ICE candidates were gathered; the old eight-second
first-frame timer had already started and closed the peer shortly afterward.
The updated stage deadlines address that premature close. A public host still
needs a working UDP or TURN path; code cannot infer firewall/NAT reachability.

Focused model, action, route, security, auth, streaming, remote-browser, docs,
and dashboard tests pass. Schema and generated-contract checks plus the
production dashboard build also pass. Updated supervised-browser restart and
WebRTC acceptance remains the only closure gate; it is not inferred from the
local automated evidence.
