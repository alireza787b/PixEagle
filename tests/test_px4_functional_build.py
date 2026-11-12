"""Functional build orchestration only; native semantics have separate real XML evidence."""

import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile

import pytest

from tools import build_native_guidance as cli
from tools import px4_functional as tool


NAMES = {f"Case{number}" for number in range(10)}
NEGATIVE = {f"Case{number}" for number in range(6)}


def xml(path, failures=(), *, skipped=False):
    root = ET.Element("testsuites", tests="10", failures=str(len(failures)), disabled="0", errors="0")
    suite = ET.SubElement(root, "testsuite")
    for name in sorted(NAMES):
        case = ET.SubElement(suite, "testcase", name=name, status="run", result="completed")
        if name in failures:
            ET.SubElement(case, "failure", message="synthetic orchestration fixture")
        if skipped and name == "Case0":
            ET.SubElement(case, "skipped")
    ET.ElementTree(root).write(path)


@pytest.fixture
def build_inputs(tmp_path, monkeypatch):
    repository, source, cache = (tmp_path / name for name in ("repository", "source", "cache"))
    extension = repository / "native/px4"
    (extension / "patches").mkdir(parents=True)
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    original, patched = "float derivative = 0;\n", "float derivative = 1;\n"
    cpp = source / tool.TRANSITION
    cpp.parent.mkdir(parents=True)
    cpp.write_text(patched)
    (source / tool.TEST_SOURCE).write_text("\n".join(f"TEST_F(TransitionAccelerationTest, {name}) {{}}" for name in sorted(NAMES)))
    (source / "template.txt").write_text("synthetic generated fixture\n")
    (source / ".gitignore").write_text("generated.txt\n*.ignored\n")
    patch = extension / tool.FEEDFORWARD_PATCH
    patch.write_text("".join(difflib.unified_diff(original.splitlines(True), patched.splitlines(True),
                                               fromfile="a/" + tool.TRANSITION, tofile="b/" + tool.TRANSITION)))
    manifest = {"baseline_commit": "a" * 40, "patches": {tool.FEEDFORWARD_PATCH: tool.sih.digest(patch)},
                "files": {tool.TRANSITION: tool.sih.digest(cpp)},
                "original_files": {tool.TRANSITION: hashlib.sha256(original.encode()).hexdigest()}}
    (extension / "extension.json").write_text(json.dumps(manifest))
    dependencies = {}
    for name in ("googletest", "abseil-cpp", "re2", "antlr_cpp"):
        folder = cache / name
        folder.mkdir(parents=True)
        (folder / "source.txt").write_text("synthetic dependency source")
        entries = tool.dependency_entries(folder)
        dependencies[name] = {"relative_cache_directory": name, "source_file_count": len(entries),
                              "source_tree_sha256": hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()}
    lock = {"reference_px4_commit": manifest["baseline_commit"],
            "sih_build": {"platform": "linux/amd64", "target": "px4_sitl_sih", "submodules": [],
                          "toolchain_image": "compiler@sha256:" + "b" * 64,
                          "runtime_image": "runtime@sha256:" + "c" * 64},
            "px4_functional_tests": {"target": tool.TARGET, "expected_tests": 10,
                                     "expected_negative_failures": sorted(NEGATIVE), "dependencies": dependencies,
                                     "fuzztest_path": "test/fuzztest"}}
    (repository / "native/dependencies.lock.json").write_text(json.dumps(lock))
    policy = {"source_pins": {}, "expected_output_paths": 1,
              "outputs": {"generated.txt": {"template": "template.txt", "template_sha256": tool.sih.digest(source / "template.txt"),
                                            "mode": "COPYONLY"}}}
    (extension / "functional-generated-files.json").write_text(json.dumps(policy))
    (extension / "build-functional-tests.sh").write_text("# synthetic tool orchestration fixture\n")

    def verify(checkout, authority, spec, verify_extension):
        assert os.environ.get("GIT_OPTIONAL_LOCKS") == "0"
        declared = json.loads((authority / "native/px4/extension.json").read_text())
        assert tool.sih.digest(checkout / tool.TRANSITION) == declared["files"][tool.TRANSITION]
        return {"submodules": []}

    monkeypatch.setattr(tool, "verify_functional_source", verify)
    return SimpleNamespace(repository=repository, source=source, cache=cache, original=original,
                           patched=patched, lock=lock, policy=policy)


def build(inputs, output, *, prepare_only=False):
    return tool.build_functional(inputs.source, output, inputs.cache, prepare_only=prepare_only,
                                 verify_extension=lambda *args: None, repository=inputs.repository)


def mock_compiler(monkeypatch, *, baseline_exit=8, candidate_exit=0, missing_xml=False, wrong_failure=False):
    real_run, calls = subprocess.run, []

    def run(argv, **kwargs):
        if argv[0] == "git":
            return real_run(argv, **kwargs)
        assert argv[:3] == ["docker", "run", "--rm"]
        calls.append(argv)
        mounts = {part.split(",dst=", 1)[1].split(",", 1)[0]: Path(part.split("src=", 1)[1].split(",", 1)[0])
                  for part in argv if part.startswith("type=bind,src=")}
        source, output = mounts["/source"], mounts["/build"]
        baseline = source.name == "source-baseline"
        failures = NEGATIVE if baseline else set()
        if wrong_failure and baseline:
            failures = {"Case9"}
        (source / "generated.txt").write_bytes((source / "template.txt").read_bytes())
        if not missing_xml:
            xml(output / "native-tests.xml", failures)
        (output / "build.ninja").write_text("synthetic identical build graph")
        (output / "compile_commands.json").write_text("[]")
        kwargs["stdout"].write("synthetic compiler boundary; no actual build\n")
        return SimpleNamespace(returncode=baseline_exit if baseline else candidate_exit)

    monkeypatch.setattr(tool.subprocess, "run", run)
    return calls


def test_cli_dispatches_before_ros_preparation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli.sys, "argv", ["build_native_guidance.py", "--target", "px4-functional", "--prepare-only",
                                         "--px4-source", str(tmp_path), "--output-dir", str(tmp_path / "out")])
    monkeypatch.setattr(cli, "prepare_sources", lambda *args: pytest.fail("ROS preparation"))
    monkeypatch.setattr(tool, "build_functional", lambda *args, **kwargs: calls.append((args, kwargs)))
    cli.main()
    assert calls[0][1]["prepare_only"] is True


def test_preparation_isolated_negative_control_never_mutates_operator_or_uses_docker(build_inputs, tmp_path, monkeypatch):
    real_run = subprocess.run
    def git_only(argv, **kwargs):
        assert argv[0] == "git"
        return real_run(argv, **kwargs)
    monkeypatch.setattr(tool.subprocess, "run", git_only)
    output = tmp_path / "prepared"
    result = json.loads(build(build_inputs, output, prepare_only=True).read_text())
    assert result["prepared_only"] and result["completed"]
    assert (build_inputs.source / tool.TRANSITION).read_text() == build_inputs.patched
    assert (output / "source-baseline" / tool.TRANSITION).read_text() == build_inputs.original
    assert (output / "source-candidate" / tool.TRANSITION).read_text() == build_inputs.patched
    assert not list(output.glob("**/native-tests.xml"))
    assert not list(output.glob("**/native/px4/extension.json"))


def test_expected_pair_retains_raw_negative_exit_xml_logs_and_same_build_recipe(build_inputs, tmp_path, monkeypatch):
    calls = mock_compiler(monkeypatch)
    result = json.loads(build(build_inputs, tmp_path / "built").read_text())
    assert result["completed"] and len(calls) == 2
    baseline, candidate = (result["variants"][name] for name in ("baseline", "candidate"))
    assert baseline["raw_exit_code"] == 8 and baseline["tests"]["failed_names"] == sorted(NEGATIVE)
    assert candidate["raw_exit_code"] == 0 and candidate["tests"]["failed_names"] == []
    assert (build_inputs.source / tool.TRANSITION).read_text() == build_inputs.patched
    for argv in calls:
        assert argv[argv.index("--network") + 1] == "none"
        assert argv[argv.index("--cpus") + 1] == "2" and argv[argv.index("--memory") + 1] == "4g"
        assert "PYTHONDONTWRITEBYTECODE=1" in argv
        assert any(part.endswith("dst=/deps,readonly") for part in argv)
        assert any(part.endswith("dst=/plan,readonly") for part in argv)


@pytest.mark.parametrize("change", [{"baseline_exit": 0}, {"baseline_exit": 1}, {"missing_xml": True}, {"wrong_failure": True}])
def test_unexpected_negative_control_stops_before_candidate(build_inputs, tmp_path, monkeypatch, change):
    calls = mock_compiler(monkeypatch, **change)
    output = tmp_path / "failed"
    with pytest.raises(ValueError):
        build(build_inputs, output)
    result = json.loads((output / "functional-results.json").read_text())
    assert "error" in result and len(calls) == 1
    state = result["variants"]["baseline"]
    assert "after" in state and "authority_after" in state and "dependencies_after" in state
    assert state["outcome"] == "build_or_validation_failed"
    assert "operator_source_after" in result
    assert not (output / "source-candidate").exists()


def test_candidate_failure_is_retained(build_inputs, tmp_path, monkeypatch):
    mock_compiler(monkeypatch, candidate_exit=8)
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="Unexpected"):
        build(build_inputs, output)
    result = json.loads((output / "functional-results.json").read_text())
    assert result["variants"]["candidate"]["raw_exit_code"] == 8 and "error" in result


def test_existing_output_is_never_overwritten(build_inputs, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(ValueError, match="new functional output"):
        build(build_inputs, output)
    assert list(output.iterdir()) == []


def test_read_only_operator_git_environment_restored_even_after_refusal(build_inputs, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "1")
    output = tmp_path / "exists"
    output.mkdir()
    with pytest.raises(ValueError):
        build(build_inputs, output)
    assert os.environ["GIT_OPTIONAL_LOCKS"] == "1"


def test_corrupt_cached_dependency_refused_without_fetch_or_repair(build_inputs, tmp_path, monkeypatch):
    path = build_inputs.cache / "re2/source.txt"
    path.write_text("corrupt")
    real_run = subprocess.run
    def read_only_git(argv, **kwargs):
        assert argv[0] == "git" and "clone" not in argv and "checkout" not in argv
        return real_run(argv, **kwargs)
    monkeypatch.setattr(tool.subprocess, "run", read_only_git)
    with pytest.raises(ValueError, match="dependency source changed"):
        build(build_inputs, tmp_path / "failed")
    assert path.read_text() == "corrupt"


def test_unknown_ignored_source_and_tampered_generation_template_refused(build_inputs):
    source = build_inputs.source
    (source / "unreviewed.ignored").write_text("hidden input")
    snapshot = tool.source_snapshot(source, build_inputs.policy["outputs"])
    with pytest.raises(ValueError, match="ignored"):
        tool.source_integrity(source, snapshot, build_inputs.policy, {"submodules": []})
    (source / "unreviewed.ignored").unlink()
    (source / "template.txt").write_text("tampered template")
    snapshot = tool.source_snapshot(source, build_inputs.policy["outputs"])
    with pytest.raises(ValueError, match="template changed"):
        tool.source_integrity(source, snapshot, build_inputs.policy, {"submodules": []})


def test_complete_xml_cannot_hide_skipped_or_missing_cases(tmp_path):
    path = tmp_path / "tests.xml"
    xml(path, NEGATIVE, skipped=True)
    with pytest.raises(ValueError, match="complete executed"):
        tool.validate_result(path, 8, "baseline", NAMES, NEGATIVE)
    path.unlink()
    with pytest.raises(ValueError, match="no native XML"):
        tool.validate_result(path, 8, "baseline", NAMES, NEGATIVE)


def test_archive_path_escape_is_rejected_before_extraction(tmp_path, monkeypatch):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("../escape.txt", "untrusted archive")
    payload = data.getvalue()
    pin = {"relative_cache_directory": "antlr_cpp", "archive_name": "source.zip", "url": "https://example.invalid/source.zip",
           "archive_sha256": hashlib.sha256(payload).hexdigest()}
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(payload))
    with pytest.raises(ValueError, match="Unsafe"):
        tool.prepare_dependencies(tmp_path / "cache", {"dependencies": {"antlr_cpp": pin}})
    assert not (tmp_path / "escape.txt").exists()


def test_git_dependency_metadata_cannot_change_the_locked_revision(build_inputs):
    source = build_inputs.cache / "googletest"
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "source.txt"], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "synthetic dependency fixture"], check=True)
    spec = build_inputs.lock["px4_functional_tests"]
    spec["dependencies"]["googletest"]["git_commit"] = "0" * 40
    with pytest.raises(ValueError, match="Git revision/worktree"):
        tool.verify_dependencies(build_inputs.cache, spec)
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    spec["dependencies"]["googletest"]["git_commit"] = head
    assert tool.verify_dependencies(build_inputs.cache, spec)["googletest"]["git_commit"] == head


def test_all_postchecks_run_after_a_partial_configure_failure(build_inputs, tmp_path, monkeypatch):
    real_run, calls = subprocess.run, []
    def failed_compile(argv, **kwargs):
        if argv[0] == "git":
            return real_run(argv, **kwargs)
        calls.append(argv)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(tool.subprocess, "run", failed_compile)
    output = tmp_path / "partial"
    with pytest.raises(ValueError, match="validation failed"):
        build(build_inputs, output)
    result = json.loads((output / "functional-results.json").read_text())
    state = result["variants"]["baseline"]
    assert state["raw_exit_code"] == 1 and len(calls) == 1
    assert {"after", "authority_after", "dependencies_after"} <= state.keys()
    assert set(state["postcheck_errors"]) == {"tests", "generated_files"}
    assert "operator_source_after" in result and not result["completed"]


def test_canonical_functional_inputs_are_pinned_without_report_paths():
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "native/dependencies.lock.json").read_text())
    manifest = json.loads((root / "native/px4/extension.json").read_text())
    for name, digest in manifest["patches"].items():
        assert tool.sih.digest(root / "native/px4" / name) == digest
    assert set(lock["px4_functional_tests"]["dependencies"]) == {"googletest", "abseil-cpp", "re2", "antlr_cpp"}
    assert tool.TRANSITION in manifest["original_files"]
    assert "reports/" not in json.dumps(lock["px4_functional_tests"])
