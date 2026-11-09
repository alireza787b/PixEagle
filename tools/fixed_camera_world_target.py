"""Pure simulated fixed-camera measurements from independent NED target truth.

This is a qualification fixture, not a camera/provider adapter or flight model.
Aircraft pose is always an observed input; commands never advance it.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import yaml

from classes.aircraft_state import Quaternion, Vector3, finite_number
from classes.sih_visualization import VisualizationScenario, VisualizationValidationError


MC_IMAGE_PROFILES = frozenset({
    "mc_velocity_position", "mc_velocity_chase", "mc_velocity_ground",
    "mc_velocity_distance", "mc_attitude_rate",
})


def _vector(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} requires three finite components")
    return Vector3(*(finite_number(component, name) for component in value))


@dataclass(frozen=True)
class FixedCamera:
    forward_body: Vector3
    right_body: Vector3
    down_body: Vector3
    offset_body: Vector3
    horizontal_fov_deg: float
    vertical_fov_deg: float

    @classmethod
    def from_mapping(cls, raw):
        if not isinstance(raw, dict) or set(raw) != {
            "forward_body", "right_body", "down_body", "offset_body_m",
            "horizontal_fov_deg", "vertical_fov_deg",
        }:
            raise ValueError("fixed_camera requires explicit extrinsic axes, offset and FOV")
        axes = [_vector(raw[name], name) for name in ("forward_body", "right_body", "down_body")]
        dot = lambda a, b: a.x * b.x + a.y * b.y + a.z * b.z
        if any(not math.isclose(axis.magnitude, 1., abs_tol=1e-8) for axis in axes):
            raise ValueError("fixed_camera axes must be unit vectors")
        f, r, d = axes
        cross = Vector3(f.y * r.z - f.z * r.y, f.z * r.x - f.x * r.z, f.x * r.y - f.y * r.x)
        if (any(abs(dot(a, b)) > 1e-8 for a, b in ((f, r), (f, d), (r, d)))
                or not math.isclose(dot(cross, d), 1., abs_tol=1e-8)):
            raise ValueError("fixed_camera axes must form a right-handed orthogonal frame")
        hfov = finite_number(raw["horizontal_fov_deg"], "horizontal_fov")
        vfov = finite_number(raw["vertical_fov_deg"], "vertical_fov")
        if not 1. <= hfov < 179. or not 1. <= vfov < 179.:
            raise ValueError("fixed_camera FOV must be in [1, 179) degrees")
        return cls(f, r, d, _vector(raw["offset_body_m"], "camera_offset"), hfov, vfov)

    def project(self, vehicle_ned, quaternion_wxyz, target_ned):
        """Return normalized image right/down, or no visible measurement."""
        position, target = _vector(vehicle_ned, "vehicle"), _vector(target_ned, "target")
        q = Quaternion(*quaternion_wxyz)
        inverse = Quaternion(q.w, -q.x, -q.y, -q.z)
        delta = inverse.rotate(Vector3(target.x - position.x, target.y - position.y, target.z - position.z))
        ray = Vector3(delta.x - self.offset_body.x, delta.y - self.offset_body.y, delta.z - self.offset_body.z)
        dot = lambda axis: axis.x * ray.x + axis.y * ray.y + axis.z * ray.z
        depth = dot(self.forward_body)
        if depth <= 1e-6:
            return None
        x = dot(self.right_body) / depth / math.tan(math.radians(self.horizontal_fov_deg) / 2.)
        y = dot(self.down_body) / depth / math.tan(math.radians(self.vertical_fov_deg) / 2.)
        return (x, y) if abs(x) <= 1. and abs(y) <= 1. else None


@dataclass(frozen=True)
class MCScenario:
    visual: VisualizationScenario
    camera: FixedCamera
    duration_s: float
    loss_windows: tuple[tuple[float, float], ...]
    expected_handoff: bool
    altitude_tolerance_m: float
    position_tolerance_m: float
    minimum_vertical_response_m: float | None = None

    def __post_init__(self):
        if self.minimum_vertical_response_m is not None:
            minimum = finite_number(self.minimum_vertical_response_m, "minimum_vertical_response_m")
            if minimum <= 0.:
                raise VisualizationValidationError("Minimum vertical response must be positive")
        if self.visual.altitude_control and self.visual.follower_profile != "mc_attitude_rate":
            if self.minimum_vertical_response_m is None:
                raise VisualizationValidationError("Altitude-enabled velocity scenarios require minimum_vertical_response_m")
            stimulus = max(abs(point.position_ned[2] - self.visual.initial_vehicle_ned[2])
                           for point in self.visual.target_waypoints)
            if stimulus < self.minimum_vertical_response_m:
                raise VisualizationValidationError("Altitude-enabled velocity scenarios require nonzero vertical target stimulus")

    @classmethod
    def from_yaml(cls, path: Path):
        visual = VisualizationScenario.from_yaml(path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if visual.follower_profile not in MC_IMAGE_PROFILES or visual.airframe != "multicopter":
            raise VisualizationValidationError("MC runner requires a multicopter image profile")
        if visual.requested_speed is not None:
            raise VisualizationValidationError("MC image profiles have no requested-speed session control")
        camera = FixedCamera.from_mapping(raw.get("fixed_camera"))
        if len(visual.target_waypoints) < 2 or visual.target_waypoints[0].time_s != 0.:
            raise VisualizationValidationError("World target requires at least two waypoints beginning at zero")
        duration = visual.target_waypoints[-1].time_s
        if not 1. <= duration <= 60.:
            raise VisualizationValidationError("MC scenario duration must be 1–60 seconds")
        if visual.stable_flight != {"required": True, "settle_samples": 7}:
            raise VisualizationValidationError("MC runner requires seven fresh stable Hold samples")
        if visual.continuity_policy and visual.continuity_policy != {"mode": "immediate_handoff"}:
            raise VisualizationValidationError("Scenario cannot override saved continuity policy")
        windows = []
        for fault in visual.faults:
            if set(fault) != {"kind", "at_s", "duration_s"} or fault["kind"] != "target_loss":
                raise VisualizationValidationError("MC runner supports only explicit target_loss windows")
            start = finite_number(fault["at_s"], "loss_start")
            length = finite_number(fault["duration_s"], "loss_duration")
            if not 1. <= start < duration or length <= 0. or start + length > duration:
                raise VisualizationValidationError("Loss window must fit after the initial response interval")
            windows.append((start, start + length))
        if any(right[0] < left[1] for left, right in zip(sorted(windows), sorted(windows)[1:])):
            raise VisualizationValidationError("Loss windows cannot overlap")
        qualification = raw.get("qualification", {})
        required = {"expected_handoff", "altitude_tolerance_m", "position_tolerance_m"}
        if not required <= set(qualification) or set(qualification) - required - {"minimum_vertical_response_m"}:
            raise VisualizationValidationError("Explicit qualification tolerances and expected handoff are required")
        expected = qualification["expected_handoff"]
        if type(expected) is not bool or expected != bool(windows):
            raise VisualizationValidationError("Loss scenarios must explicitly expect terminal handoff")
        altitude = finite_number(qualification["altitude_tolerance_m"], "altitude_tolerance")
        position = finite_number(qualification["position_tolerance_m"], "position_tolerance")
        if not 0. < altitude <= 2. or not 0. < position <= 2.:
            raise VisualizationValidationError("MC response tolerances must be positive and no greater than 2 m")
        minimum_vertical = (finite_number(qualification["minimum_vertical_response_m"], "minimum_vertical_response_m")
                            if "minimum_vertical_response_m" in qualification else None)
        if visual.follower_profile == "mc_velocity_ground":
            if camera.forward_body != Vector3(0., 0., 1.) or camera.right_body != Vector3(0., 1., 0.):
                raise VisualizationValidationError("Ground scenario requires explicit downlooking camera axes")
            if any(point.position_ned[2] <= visual.initial_vehicle_ned[2] for point in visual.target_waypoints):
                raise VisualizationValidationError("Ground targets must be below the initial aircraft")
        initial_quaternion = raw.get("initial_conditions", {}).get("quaternion_wxyz", (1., 0., 0., 0.))
        if camera.project(visual.initial_vehicle_ned, initial_quaternion, visual.target_at(0.)) is None:
            raise VisualizationValidationError("Initial world target must be in the declared camera FOV")
        return cls(visual, camera, duration, tuple(windows), expected, altitude, position, minimum_vertical)

    def target_at(self, elapsed_s, anchor_ned):
        """Use one frozen pre-engagement world anchor, never the latest aircraft pose."""
        target = self.visual.target_at(elapsed_s)
        if target is None:
            return None
        return tuple(target[index] + anchor_ned[index] for index in range(3))


def stable_hold_window(samples, *, expected_altitude_m):
    """Seven distinct progressing PX4 observations, not seven repeated polls."""
    if len(samples) != 7 or samples[-1]["monotonic_s"] - samples[0]["monotonic_s"] < 2.9:
        return False
    if any(not sample["hold"] or not sample["airborne"] for sample in samples):
        return False
    for previous, current in zip(samples, samples[1:]):
        if any(now <= before for now, before in zip(current["source_boot_ms"], previous["source_boot_ms"])):
            return False
    initial = samples[0]
    for sample in samples:
        if (math.hypot(*sample["velocity_ned"][:2]) > .5 or abs(sample["velocity_ned"][2]) > .2
                or abs(sample["altitude_m"] - expected_altitude_m) > 1.
                or abs(sample["roll_deg"]) > 3. or abs(sample["pitch_deg"]) > 3.):
            return False
    yaw_offsets = [math.remainder(sample["yaw_rad"] - initial["yaw_rad"], 2 * math.pi) for sample in samples]
    return (max(s["altitude_m"] for s in samples) - min(s["altitude_m"] for s in samples) <= .1
            and max(yaw_offsets) - min(yaw_offsets) <= math.radians(.6))


def evaluate_response(scenario, records, publications, *, velocity_limits, rate_limits_deg_s,
                      attitude_limits_deg, publication_gap_limit_s=.25):
    """Assess independent observed motion and actual publications, never integrate commands."""
    mode = scenario.visual.follower_profile
    fields = [row["fields"] for row in publications if row.get("fields") is not None]
    expected = ({"rollspeed_deg_s", "pitchspeed_deg_s", "yawspeed_deg_s", "thrust"}
                if mode == "mc_attitude_rate" else
                {"vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"})
    checks = {
        "independent_pose_present": len(records) >= 2,
        "complete_publications": bool(fields) and len(fields) == len(publications) and all(set(row) == expected for row in fields),
        "publication_success": bool(publications) and all(row["success"] for row in publications),
        "finite_commands": all(math.isfinite(value) for row in fields for value in row.values()),
    }
    checks["saved_velocity_bounds"] = all(
        all(abs(row.get(key, 0.)) <= velocity_limits[axis] + 1e-6
            for key, axis in (("vel_body_fwd", "forward"), ("vel_body_right", "lateral"), ("vel_body_down", "vertical")))
        and math.sqrt(sum(row.get(key, 0.) ** 2 for key in ("vel_body_fwd", "vel_body_right", "vel_body_down"))) <= velocity_limits["max_magnitude"] + 1e-6
        for row in fields
    )
    checks["saved_rate_bounds"] = all(
        all(abs(row.get(key, 0.)) <= limit + 1e-6 for key, limit in rate_limits_deg_s.items())
        for row in fields
    )
    if mode in {"mc_velocity_position", "mc_velocity_distance"}:
        checks["zero_forward_intent"] = all(abs(row.get("vel_body_fwd", 0.)) <= 1e-9 for row in fields)
    if mode == "mc_velocity_position":
        checks["zero_lateral_intent"] = all(abs(row.get("vel_body_right", 0.)) <= 1e-9 for row in fields)
    if mode == "mc_velocity_ground":
        checks["zero_yaw_intent"] = all(abs(row.get("yawspeed_deg_s", 0.)) <= 1e-9 for row in fields)
    if mode != "mc_attitude_rate" and not scenario.visual.altitude_control:
        checks["altitude_off_zero_intent"] = all(abs(row.get("vel_body_down", 0.)) <= 1e-9 for row in fields)
    metrics = {}
    gaps = [current["monotonic_s"] - previous["monotonic_s"]
            for previous, current in zip(publications, publications[1:])]
    checks["bounded_publication_gaps"] = bool(gaps) and all(0. < gap <= publication_gap_limit_s for gap in gaps)
    metrics["maximum_publication_gap_s"] = max(gaps, default=None)
    if len(records) < 2:
        return {"passed": False, "checks": checks, "metrics": metrics}
    first = records[0]
    altitude_error = max(abs(row["altitude_m"] - first["altitude_m"]) for row in records)
    horizontal_drift = max(math.dist(row["position_ned"][:2], first["position_ned"][:2]) for row in records)
    range_start = math.dist(first["position_ned"], first["target_ned"])
    range_end = math.dist(records[-1]["position_ned"], records[-1]["target_ned"])
    work = 0.
    vertical_work_m = 0.
    for previous, current in zip(records, records[1:]):
        if current.get("loss_active") or previous.get("loss_active"):
            continue
        target = current["target_ned"]
        before = scenario.camera.project(previous["position_ned"], previous["quaternion_wxyz"], target)
        after = scenario.camera.project(current["position_ned"], current["quaternion_wxyz"], target)
        if before is None or after is None:
            continue
        axes = (0,) if mode in {"mc_velocity_position", "mc_velocity_chase", "mc_velocity_distance"} else (0, 1)
        work += sum(before[axis] ** 2 - after[axis] ** 2 for axis in axes)
        # Freeze independent target height so only observed aircraft z earns closure.
        vertical_work_m += (abs(target[2] - previous["position_ned"][2])
                            - abs(target[2] - current["position_ned"][2]))
    metrics.update(maximum_altitude_error_m=altitude_error, maximum_horizontal_drift_m=horizontal_drift,
                   range_start_m=range_start, range_end_m=range_end, camera_response_work=work)
    checks["observed_image_response"] = work > 1e-4
    checks["altitude_envelope"] = all(
        scenario.visual.limits["altitude_min"] <= row["altitude_m"] <= scenario.visual.limits["altitude_max"]
        for row in records
    )
    if not scenario.visual.altitude_control:
        checks["observed_altitude_hold"] = altitude_error <= scenario.altitude_tolerance_m
    elif mode != "mc_attitude_rate":
        metrics["vertical_response_work_m"] = vertical_work_m
        metrics["minimum_vertical_response_m"] = scenario.minimum_vertical_response_m
        checks["observed_vertical_response"] = vertical_work_m >= scenario.minimum_vertical_response_m
    if mode == "mc_velocity_position":
        checks["observed_stationary_drift"] = horizontal_drift <= scenario.position_tolerance_m
    if mode == "mc_velocity_chase":
        checks["observed_range_closure"] = range_start - range_end > .05
        checks["nonnegative_forward"] = all(row.get("vel_body_fwd", 0.) >= -1e-9 for row in fields)
    if mode == "mc_attitude_rate":
        checks["thrust_normalized"] = all(0. <= row.get("thrust", -1.) <= 1. for row in fields)
        checks["observed_attitude_envelope"] = all(
            abs(row["roll_deg"]) <= attitude_limits_deg["roll"]
            and abs(row["pitch_deg"]) <= attitude_limits_deg["pitch"] for row in records
        )
    return {"passed": all(checks.values()), "checks": checks, "metrics": metrics}
