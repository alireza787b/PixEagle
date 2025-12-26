# tests/integration/drone_interface/__init__.py
"""
Integration tests for drone interface layer.

Tests the data flow between components:
- Command flow: Follower → SetpointHandler → PX4InterfaceManager
- Telemetry flow: MAVLink2REST → PX4InterfaceManager → TelemetryHandler
- Safety integration: Circuit breaker and limits enforcement
"""
