"""Process-local choices for returning between local and camera tracking."""

from classes.schema_manager import get_schema_manager
from classes.trackers.tracker_factory import TRACKER_REGISTRY


def tracker_engine(tracker_type):
    """Resolve aliases through the catalog instead of matching vendor names."""
    _, info, _ = get_schema_manager().resolve_tracker_for_ui(tracker_type)
    factory = (info or {}).get("ui_metadata", {}).get("factory_key")
    implementation = TRACKER_REGISTRY.get(factory)
    if implementation is None:
        return None
    return "camera" if getattr(implementation, "is_external_tracker", False) else "local"


def remember_engine_selection(app):
    """Capture intent before cleanup; never retain the previous target itself."""
    tracker_type = getattr(app, "current_tracker_type", "")
    engine = tracker_engine(tracker_type)
    if engine is None:
        return
    choices = getattr(app, "_tracking_engine_selections", None)
    if choices is None:
        choices = app._tracking_engine_selections = {}
    choice = dict(tracker_type=tracker_type, smart_mode=bool(getattr(app, "smart_mode_active", False)))
    if engine == "camera":
        runtime = getattr(app, "camera_runtime", None)
        provider = getattr(runtime, "provider", None) or getattr(app.tracker, "gimbal_provider", None)
        control = getattr(provider, "manual_control", None)
        choice["selection_mode"] = getattr(control, "selection_mode", "classic")
    choices[engine] = choice


def recalled_engine_selection(app, requested_tracker):
    """Return a copy; the caller still validates current runtime availability."""
    engine = tracker_engine(requested_tracker)
    choices = getattr(app, "_tracking_engine_selections", {})
    choice = choices.get(engine)
    if choice and tracker_engine(choice["tracker_type"]) == engine:
        return dict(choice)
    return dict(tracker_type=requested_tracker, smart_mode=False)
