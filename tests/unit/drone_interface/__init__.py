# tests/unit/drone_interface/__init__.py
"""
Unit tests for drone interface components.

Tests cover:
- PX4InterfaceManager: MAVSDK command dispatch, telemetry
- MavlinkDataManager: REST polling, data parsing
- SetpointHandler: Schema-driven field management
- SetpointSender: Threaded command publishing
- TelemetryHandler: Data formatting, UDP broadcast
- Control Types: Command format creation
"""
