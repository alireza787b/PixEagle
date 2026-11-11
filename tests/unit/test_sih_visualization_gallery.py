"""Offline current-evidence selection; no Docker, simulator or command publication."""

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest
import yaml

from tools import sih_visualization_gallery as gallery


pytestmark = pytest.mark.unit
IDENTITY = {
    "kind": "verified_source_build", "image_id": "sha256:" + "a" * 64,
    "manifest_sha256": "b" * 64, "recipe_sha256": "c" * 64,
    "firmware": {"commit": "d" * 40}, "binary_sha256": "e" * 64,
}
PROFILE = "mc_velocity_ground"
CATALOG = {"followers": [{
    "profile": PROFILE, "input": "image_position_2d", "command": "velocity_body_offboard",
    "purpose": "Ground target", "behavior": "Raw image axes",
}]}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def run_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(gallery, "baseline_identity", lambda path: deepcopy(IDENTITY))
    monkeypatch.setattr(gallery, "ROOT", tmp_path / "checkout")
    root, output = tmp_path / "runs", tmp_path / "gallery"
    output.mkdir()

    def make(name="run", *, capture=10., passed=True, fault=None, altitude=False):
        run = root / name
        run.mkdir(parents=True)
        scenario = {"follower": {"profile": PROFILE, "altitude_control": altitude},
                    "faults": [{"kind": fault}] if fault else []}
        (run / "scenario.yaml").write_text(yaml.safe_dump(scenario))
        (run / "configs").mkdir()
        (run / "configs/config.yaml").write_text("Follower:\n  USE_MAVLINK2REST: false\n")
        (run / "driver.py").write_text("# captured driver\n")
        source = f"src/classes/followers/{PROFILE}_follower.py"
        (run / "backend" / source).parent.mkdir(parents=True)
        (run / "backend" / source).write_text("# captured follower\n")
        for name in gallery.RAW_TRACES:
            path = run / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"timestamp": capture, "vehicle_ned": [0., 0., -20.]}) + "\n")
        result = {
            "follower": PROFILE, "passed": passed, "checks": {"observed_image_response": passed},
            "scope": "actual_mc_follower_component_only", "physical_camera": False,
            "hardware_qualified": False, "release_qualified": False, "application_startup_qualified": False,
            "altitude_guidance": altitude, "executed_scenario_sha256": gallery.sha256(run / "scenario.yaml"),
        }
        manifest = {
            "kind": "mc-fixed-camera-world-target-component", "follower": PROFILE,
            "network": "none", "host_ports": [], "simulator_model": "sihsim_quadx",
            "sih_baseline": deepcopy(IDENTITY), "px4_image": IDENTITY["image_id"],
            "config_sha256": gallery.sha256(run / "configs/config.yaml"),
            "driver_sha256": gallery.sha256(run / "driver.py"),
            "source_checksums": {source: gallery.sha256(run / "backend" / source)},
            "source_head": "f" * 40, "worktree_dirty": True,
        }
        write_json(run / "manifest.json", manifest)
        write_json(run / "result.json", result)
        summary = {"qualification_result": result, "evidence_kind": "px4_sih", "pose_observed_samples": 1}
        write_json(run / "visualization/summary.json", summary)
        (run / "visualization/index.html").write_text("<script>const PAYLOAD=" + json.dumps({"summary": summary}) + ";</script>")
        return run

    return make, root, output


def collect(root, output):
    return gallery.collect_evidence(CATALOG, root, root / "build.json", output)


def test_latest_raw_capture_selects_failure_and_retains_earlier_pass(run_factory):
    make, root, output = run_factory
    older = make("old-pass", capture=10.)
    make("new-fail", capture=20., passed=False)
    # File copy time does not determine which actual observation was later.
    os.utime(older / "result.json", (1000000, 1000000))
    evidence = collect(root, output)
    attempts = evidence["profiles"][PROFILE]["nominal"]
    assert [item["run"] for item in attempts] == ["old-pass", "new-fail"]
    assert not attempts[-1]["passed"]
    assert attempts[-1]["failed_checks"] == ["observed_image_response"]
    assert attempts[-1]["issues"] == []
    html = gallery.build_gallery(CATALOG, output, evidence)
    assert "Raw FAIL" in html and "Earlier attempts (1)" in html
    assert "control telemetry: mavsdk" in html
    assert "old-pass/result.json" in html and "new-fail/result.json" in html


def test_replay_disagreement_is_stale_and_does_not_override_raw_failure(run_factory):
    make, root, output = run_factory
    run = make(passed=False)
    summary = gallery.read_json(run / "visualization/summary.json")
    summary["qualification_result"]["passed"] = True
    write_json(run / "visualization/summary.json", summary)
    evidence = collect(root, output)
    current = evidence["profiles"][PROFILE]["nominal"][-1]
    assert not current["passed"]
    assert current["stale"] == ["Replay verdict differs from raw result.json", "Replay HTML differs from its saved summary"]
    html = gallery.build_gallery(CATALOG, output, evidence)
    assert "Stale replay" in html and "Raw FAIL" in html


def test_stale_html_is_detected_even_when_summary_matches_raw_result(run_factory):
    make, root, output = run_factory
    run = make()
    (run / "visualization/index.html").write_text('<script>const PAYLOAD={"summary":{"qualification_result":{"passed":false}}};</script>')
    evidence = collect(root, output)
    current = evidence["profiles"][PROFILE]["nominal"][-1]
    assert current["passed"] and not current["issues"]
    assert current["stale"] == ["Replay HTML differs from its saved summary"]


@pytest.mark.parametrize("name", ["scenario.yaml", "configs/config.yaml", "driver.py",
                                   f"backend/src/classes/followers/{PROFILE}_follower.py"])
def test_recorded_input_tampering_is_invalid_evidence(run_factory, name):
    make, root, output = run_factory
    run = make()
    with (run / name).open("a") as stream:
        stream.write("\n# changed after capture\n")
    evidence = collect(root, output)
    current = evidence["profiles"][PROFILE]["nominal"][-1]
    assert any("checksum mismatch" in issue for issue in current["issues"])
    assert "Invalid evidence" in gallery.build_gallery(CATALOG, output, evidence)


def test_different_baseline_does_not_replace_canonical_capture(run_factory):
    make, root, output = run_factory
    make("canonical", capture=10.)
    other = make("diagnostic", capture=20.)
    manifest = gallery.read_json(other / "manifest.json")
    manifest["sih_baseline"]["manifest_sha256"] = "0" * 64
    write_json(other / "manifest.json", manifest)
    evidence = collect(root, output)
    assert evidence["profiles"][PROFILE]["nominal"][-1]["run"] == "canonical"
    assert evidence["excluded_runs"] == [{"run": "diagnostic", "reason": "Different or unverified SIH baseline"}]


def test_missing_replay_cannot_hide_raw_failure_or_fault_class(run_factory):
    make, root, output = run_factory
    run = make(passed=False, fault="stale_telemetry")
    (run / "visualization/index.html").unlink()
    evidence = collect(root, output)
    assert evidence["profiles"][PROFILE]["stale_telemetry"][-1]["replay"] is None
    html = gallery.build_gallery(CATALOG, output, evidence)
    assert "Raw FAIL" in html and "Replay unavailable" in html
    assert "Not run / unqualified" in html


def test_missing_pose_on_new_failed_attempt_is_visible_with_invalid_order_fallback(run_factory):
    make, root, output = run_factory
    make("old-pass", capture=10.)
    run = make("new-incomplete", capture=20., passed=False)
    (run / gallery.RAW_TRACES[0]).unlink()
    os.utime(run / "result.json", (30., 30.))
    evidence = collect(root, output)
    current = evidence["profiles"][PROFILE]["nominal"][-1]
    assert current["run"] == "new-incomplete" and not current["passed"]
    assert "fallback" in current["capture_time_basis"]
    assert "Missing raw trace: px4/pose_trace.jsonl" in current["issues"]


def test_current_follower_byte_difference_is_distinct_from_invalid_or_stale(run_factory, monkeypatch):
    make, root, output = run_factory
    make()
    checkout = root.parent / "checkout"
    path = checkout / f"src/classes/followers/{PROFILE}_follower.py"
    path.parent.mkdir(parents=True)
    path.write_text("# later comment\n")
    monkeypatch.setattr(gallery, "ROOT", checkout)
    evidence = collect(root, output)
    current = evidence["profiles"][PROFILE]["nominal"][-1]
    assert current["follower_source_differs"] and not current["issues"] and not current["stale"]
    html = gallery.build_gallery(CATALOG, output, evidence)
    assert "Follower source differs" in html and "do not assert a behavior change" in html


def test_catalog_remains_only_profile_authority_and_scope_is_explicit(run_factory):
    make, root, output = run_factory
    make(altitude=True)
    evidence = collect(root, output)
    catalog_path = Path(__file__).resolve().parents[2] / "tools/sih_visualization_scenarios/follower-contracts.yaml"
    catalog = yaml.safe_load(catalog_path.read_text())
    html = gallery.build_gallery(catalog, output, evidence)
    declarations = yaml.safe_load((catalog_path.parents[2] / "configs/follower_commands.yaml").read_text())
    assert {item["profile"] for item in catalog["followers"]} == set(declarations["follower_profiles"])
    assert html.count('<article class="card">') == len(catalog["followers"])
    assert "Outside this MC evidence snapshot" in html
    assert "camera measurements are simulated" in html
    assert "physical camera/tracker" in html
    assert "experimental MC rates: direct-rate cases only, PNG and field tuning unqualified" in html
    assert "Unsupported live retarget · Stop required" in html
    assert "Engagement-height hold plus optional offset; no altitude-chase qualification." in html
    assert "one-run-each comparison does not identify a specific upstream cause" in html
    assert "Selection, hashes and capture revisions" in html


def test_selected_build_manifest_uses_existing_authority(monkeypatch, tmp_path):
    from tools import sih_baseline
    firmware, spec = {"commit": "f" * 40}, {"target": "px4_sitl_sih"}
    monkeypatch.setattr(sih_baseline, "authority", lambda: (firmware, spec))
    monkeypatch.setattr(sih_baseline, "recipe_fingerprint", lambda *args: "recipe")
    path = tmp_path / "build.json"
    manifest = {"schema_version": 1, "kind": "pixeagle_sih_build", "firmware": firmware,
                "build": spec, "recipe_sha256": "recipe", "image_id": IDENTITY["image_id"],
                "artifacts": {"binary_sha256": IDENTITY["binary_sha256"]}}
    write_json(path, manifest)
    assert gallery.baseline_identity(path)["manifest_sha256"] == gallery.sha256(path)
    manifest["firmware"] = {"commit": "unreviewed"}
    write_json(path, manifest)
    with pytest.raises(ValueError, match="reviewed build authority"):
        gallery.baseline_identity(path)
