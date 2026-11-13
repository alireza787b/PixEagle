"""Functional build orchestration only; native semantics have separate real XML evidence."""

import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile

import pytest

from tools import build_native_guidance as cli
from tools import px4_functional as tool


PRODUCTION = "src/Example.cpp"
TEST_SOURCE = "src/ExampleTest.cpp"
PATCH = "patches/0001-example.patch"
SUITE = "ExampleTest"
NAMES = {f"Case{number}" for number in range(10)}
NEGATIVE = {f"Case{number}" for number in range(6)}


def xml(path, failures=(), *, skipped=False, names=NAMES, suite=SUITE):
    root = ET.Element("testsuites", tests=str(len(names)), failures=str(len(failures)), disabled="0", errors="0")
    suite_node = ET.SubElement(root, "testsuite", name=suite)
    for name in sorted(names):
        case = ET.SubElement(suite_node, "testcase", name=name, classname=suite, status="run", result="completed")
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
    cpp = source / PRODUCTION
    cpp.parent.mkdir(parents=True)
    cpp.write_text(patched)
    (source / TEST_SOURCE).write_text("\n".join(f"TEST_F({SUITE}, {name}) {{}}" for name in sorted(NAMES)))
    (source / "template.txt").write_text("synthetic generated fixture\n")
    (source / ".gitignore").write_text("generated.txt\n*.ignored\n")
    patch = extension / PATCH
    patch.write_text("".join(difflib.unified_diff(original.splitlines(True), patched.splitlines(True),
                                               fromfile="a/" + PRODUCTION, tofile="b/" + PRODUCTION)))
    manifest = {"baseline_commit": "a" * 40, "patches": {PATCH: tool.sih.digest(patch)},
                "files": {PRODUCTION: tool.sih.digest(cpp), TEST_SOURCE: tool.sih.digest(source / TEST_SOURCE)},
                "original_files": {PRODUCTION: hashlib.sha256(original.encode()).hexdigest()}}
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
            "px4_functional_tests": {"dependencies": dependencies, "fuzztest_path": "test/fuzztest",
                "default_regression": "example", "regressions": {"example": {
                    "target": "functional-Example", "expected_tests": 10,
                    "expected_negative_failures": sorted(NEGATIVE), "test_source": TEST_SOURCE,
                    "test_suite": SUITE, "negative_patch": PATCH, "original_files": [PRODUCTION],
                    "characterization_env": "EXAMPLE_CHARACTERIZATION"}}}}

    (repository / "native/dependencies.lock.json").write_text(json.dumps(lock))
    (repository / "tools").mkdir()
    (repository / "tools/sih_baseline.py").write_bytes(Path(tool.sih.__file__).read_bytes())
    policy = {"source_pins": {}, "expected_output_paths": 1,
              "outputs": {"generated.txt": {"template": "template.txt", "template_sha256": tool.sih.digest(source / "template.txt"),
                                            "mode": "COPYONLY"}}}
    (extension / "functional-generated-files.json").write_text(json.dumps(policy))
    (extension / "build-functional-tests.sh").write_text("# synthetic tool orchestration fixture\n")

    def verify(checkout, authority, spec, verify_extension):
        assert os.environ.get("GIT_OPTIONAL_LOCKS") == "0"
        declared = json.loads((authority / "native/px4/extension.json").read_text())
        assert all(tool.sih.digest(checkout / path)==digest for path,digest in declared["files"].items())
        return {"submodules": []}

    monkeypatch.setattr(tool, "verify_functional_source", verify)
    return SimpleNamespace(repository=repository, source=source, cache=cache, original=original,
                           patched=patched, lock=lock, policy=policy)


def build(inputs, output, *, prepare_only=False, regression=None):
    return tool.build_functional(inputs.source, output, inputs.cache, prepare_only=prepare_only,
                                 verify_extension=lambda *args: None, repository=inputs.repository, regression=regression)


def add_second_regression(inputs):
    production, test_source, patch_name = "src/Second.cpp", "src/SecondTest.cpp", "patches/0002-second.patch"
    original, patched = "float heading = 0;\n", "float heading = 1;\n"
    names, failures = {f"Other{number}" for number in range(5)}, {"Other1", "Other3"}
    (inputs.source / production).write_text(patched)
    (inputs.source / test_source).write_text("\n".join(f"TEST_F(SecondTest, {name}) {{}}" for name in sorted(names)))
    extension = inputs.repository / "native/px4"
    patch = extension / patch_name
    patch.write_text("".join(difflib.unified_diff(original.splitlines(True), patched.splitlines(True),
                                               fromfile="a/" + production, tofile="b/" + production)))
    path = extension / "extension.json"
    manifest = json.loads(path.read_text())
    manifest["patches"][patch_name] = tool.sih.digest(patch)
    manifest["files"].update({name: tool.sih.digest(inputs.source/name) for name in [production, test_source]})
    manifest["original_files"][production] = hashlib.sha256(original.encode()).hexdigest()
    path.write_text(json.dumps(manifest))
    record = dict(target="functional-Second", test_source=test_source, test_suite="SecondTest",
                  negative_patch=patch_name, original_files=[production], expected_tests=len(names),
                  expected_negative_failures=sorted(failures), characterization_env=None)
    inputs.lock["px4_functional_tests"]["regressions"]["second"] = record
    (inputs.repository / "native/dependencies.lock.json").write_text(json.dumps(inputs.lock))
    return record, names, failures


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
            environment = dict(argv[i+1].split("=",1) for i,value in enumerate(argv) if value=="--env")
            repository = mounts["/plan"].parents[1]
            records = json.loads((repository/"native/dependencies.lock.json").read_text())["px4_functional_tests"]["regressions"]
            record = next(row for row in records.values() if row["target"]==environment["PX4_FUNCTIONAL_TARGET"])
            import re
            names=set(re.findall(r"^TEST_F\("+re.escape(record["test_suite"])+r", (\w+)\)",(source/record["test_source"]).read_text(),re.M))
            failures=set(record["expected_negative_failures"]) if baseline and not wrong_failure else failures
            xml(output / "native-tests.xml", failures, names=names, suite=record["test_suite"])
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
    assert calls[0][1]["regression"] is None


def test_cli_selects_regression_without_a_display_or_gui(monkeypatch, tmp_path):
    monkeypatch.delenv("DISPLAY", raising=False)
    calls = []
    monkeypatch.setattr(cli.sys, "argv", ["build_native_guidance.py", "--target", "px4-functional",
        "--regression", "second", "--prepare-only", "--px4-source", str(tmp_path), "--output-dir", str(tmp_path/"out")])
    monkeypatch.setattr(tool, "build_functional", lambda *args, **kwargs: calls.append(kwargs))
    cli.main()
    assert calls[0]["regression"] == "second"
    monkeypatch.setattr(cli.sys, "argv", ["build_native_guidance.py", "--regression", "second", "--output-dir", str(tmp_path/"out")])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2 and len(calls) == 1


def test_preparation_isolated_negative_control_never_mutates_operator_or_uses_docker(build_inputs, tmp_path, monkeypatch):
    real_run = subprocess.run
    def git_only(argv, **kwargs):
        assert argv[0] == "git"
        return real_run(argv, **kwargs)
    monkeypatch.setattr(tool.subprocess, "run", git_only)
    output = tmp_path / "prepared"
    result = json.loads(build(build_inputs, output, prepare_only=True).read_text())
    assert result["prepared_only"] and result["completed"]
    assert (build_inputs.source / PRODUCTION).read_text() == build_inputs.patched
    assert (output / "source-baseline" / PRODUCTION).read_text() == build_inputs.original
    assert (output / "source-candidate" / PRODUCTION).read_text() == build_inputs.patched
    assert not list(output.glob("**/native-tests.xml"))
    assert not list(output.glob("**/native/px4/extension.json"))


def test_expected_pair_retains_raw_negative_exit_xml_logs_and_same_build_recipe(build_inputs, tmp_path, monkeypatch):
    calls = mock_compiler(monkeypatch)
    result = json.loads(build(build_inputs, tmp_path / "built").read_text())
    assert result["completed"] and len(calls) == 2
    baseline, candidate = (result["variants"][name] for name in ("baseline", "candidate"))
    assert baseline["raw_exit_code"] == 8 and baseline["tests"]["failed_names"] == sorted(NEGATIVE)
    assert candidate["raw_exit_code"] == 0 and candidate["tests"]["failed_names"] == []
    assert (build_inputs.source / PRODUCTION).read_text() == build_inputs.patched
    for argv in calls:
        assert argv[argv.index("--network") + 1] == "none"
        assert argv[argv.index("--cpus") + 1] == "2" and argv[argv.index("--memory") + 1] == "4g"
        assert "PYTHONDONTWRITEBYTECODE=1" in argv
        assert any(part.endswith("dst=/deps,readonly") for part in argv)
        assert any(part.endswith("dst=/plan,readonly") for part in argv)


def test_second_record_reuses_same_builder_with_its_own_source_suite_counts_and_patch(build_inputs, tmp_path, monkeypatch):
    record, names, failures = add_second_regression(build_inputs)
    calls = mock_compiler(monkeypatch)
    output = tmp_path / "second"
    result = json.loads(build(build_inputs, output, regression="second").read_text())
    assert result["regression"] == "second" and result["regression_record"] == record
    baseline, candidate = (result["variants"][name] for name in ["baseline", "candidate"])
    assert baseline["tests"]["failed_names"] == sorted(failures) and baseline["tests"]["tests"] == len(names)
    assert candidate["tests"]["passed_names"] == sorted(names)
    assert baseline["changed_from_canonical"] == record["original_files"]
    assert baseline["omitted_patch"] == record["negative_patch"]
    for variant in ["baseline", "candidate"]:
        assert (output/("source-"+variant)/PRODUCTION).read_text() == build_inputs.patched
    assert (build_inputs.source/record["original_files"][0]).read_text() == "float heading = 1;\n"
    for argv in calls:
        assert "PX4_FUNCTIONAL_TARGET=functional-Second" in argv
        assert "PX4_FUZZTEST_PATH=test/fuzztest" in argv
        assert not any("CHARACTERIZATION=" in value for value in argv)


def test_unknown_selector_refuses_before_source_cache_output_or_gui(build_inputs, tmp_path, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(tool, "verify_functional_source", lambda *args: pytest.fail("source access"))
    monkeypatch.setattr(tool, "prepare_dependencies", lambda *args: pytest.fail("cache access"))
    output = tmp_path / "unknown"
    with pytest.raises(ValueError, match="Unknown native functional regression"):
        build(build_inputs, output, regression="unknown")
    assert not output.exists()


@pytest.mark.parametrize("field,value", [("negative_patch", "patches/missing.patch"),
    ("test_source", "src/MissingTest.cpp"), ("original_files", ["src/Missing.cpp"]),
    ("target", "functional-Second;other"), ("test_source", "../OutsideTest.cpp")])
def test_wrong_record_patch_source_or_target_is_refused_early(build_inputs, tmp_path, monkeypatch, field, value):
    record, _, _ = add_second_regression(build_inputs)
    record[field] = value
    (build_inputs.repository/"native/dependencies.lock.json").write_text(json.dumps(build_inputs.lock))
    monkeypatch.setattr(tool, "verify_functional_source", lambda *args: pytest.fail("source access"))
    output = tmp_path / "wrong"
    with pytest.raises(ValueError):
        build(build_inputs, output, regression="second")
    assert not output.exists()


def test_wrong_existing_production_patch_cannot_reverse_a_different_file(build_inputs, tmp_path, monkeypatch):
    second, _, _ = add_second_regression(build_inputs)
    build_inputs.lock["px4_functional_tests"]["regressions"]["example"]["negative_patch"] = second["negative_patch"]
    (build_inputs.repository/"native/dependencies.lock.json").write_text(json.dumps(build_inputs.lock))
    calls = mock_compiler(monkeypatch)
    output = tmp_path / "wrong-patch"
    with pytest.raises(ValueError, match="only the selected production patch"):
        build(build_inputs, output)
    assert not calls and not (output/"source-candidate").exists()
    assert (build_inputs.source/PRODUCTION).read_text() == build_inputs.patched


def test_record_cannot_parse_test_names_from_another_suite(build_inputs, tmp_path, monkeypatch):
    record, _, _ = add_second_regression(build_inputs)
    record["test_suite"] = "UnrelatedSuite"
    (build_inputs.repository/"native/dependencies.lock.json").write_text(json.dumps(build_inputs.lock))
    calls = mock_compiler(monkeypatch)
    with pytest.raises(ValueError, match="test names differ"):
        build(build_inputs, tmp_path/"wrong-suite", regression="second")
    assert not calls


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


def test_identical_xml_case_names_from_wrong_suite_are_rejected(tmp_path):
    path = tmp_path/"wrong-suite.xml"
    xml(path, NEGATIVE, suite="OtherFixture")
    with pytest.raises(ValueError, match="complete executed"):
        tool.validate_result(path, 8, "baseline", NAMES, NEGATIVE, suite=SUITE)


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
    _, record = tool.select_regression(root, None)
    assert record["target"] == "functional-FlightTaskTransition"
    assert record["characterization_env"] == "TRANSITION_CHARACTERIZATION"
    assert record["original_files"][0] in manifest["original_files"]
    assert "reports/" not in json.dumps(lock["px4_functional_tests"])
    assert not {"target", "expected_tests", "expected_negative_failures"} & lock["px4_functional_tests"].keys()
    prospective = lock["px4_functional_tests"]["regressions"]["fw-mode-transition-heading"]
    assert prospective["expected_tests"] == 10 and len(prospective["expected_negative_failures"]) == 5
    assert tool.select_regression(root, "fw-mode-transition-heading")[1] == prospective
    assert prospective["characterization_env"] is None


def test_sparse_axes_authority_omits_only_production_fix_and_retains_test_hook():
    root = Path(__file__).resolve().parents[1]
    _, record = tool.select_regression(root, "control-allocation-sparse-axes")
    canonical = json.loads((root / "native/px4/extension.json").read_text())
    assert record["target"] == "functional-ControlAllocationSparseAxes"
    assert record["expected_tests"] == 11 and len(record["expected_negative_failures"]) == 2
    assert record["characterization_env"] is None
    with tool.source_authority(root, "baseline", record) as authority:
        assert (authority / "tools/sih_baseline.py").read_bytes() == (root / "tools/sih_baseline.py").read_bytes()
        baseline = json.loads((authority / "native/px4/extension.json").read_text())
        assert set(canonical["patches"]) - set(baseline["patches"]) == {record["negative_patch"]}
        assert {name for name in canonical["files"] if canonical["files"][name] != baseline["files"][name]} == set(record["original_files"])
        assert baseline["files"][record["original_files"][0]] == canonical["original_files"][record["original_files"][0]]
        assert baseline["files"][record["test_source"]] == canonical["files"][record["test_source"]]
        assert baseline["patches"]["patches/0009-control-allocation-sparse-axes-functional-tests.patch"] == canonical["patches"]["patches/0009-control-allocation-sparse-axes-functional-tests.patch"]
    assert tool.select_regression(root, None)[0] == "transition-acceleration"


def test_sparse_axes_record_uses_shared_orchestrator_with_mocked_compiler(build_inputs, tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    selector, record = tool.select_regression(root, "control-allocation-sparse-axes")
    patch_text = (root / "native/px4/patches/0009-control-allocation-sparse-axes-functional-tests.patch").read_text()
    names = set(re.findall(r"^\+TEST_F\(" + re.escape(record["test_suite"]) + r", (\w+)\)", patch_text, re.M))
    assert len(names) == record["expected_tests"]
    assert set(record["expected_negative_failures"]) < names
    assert {"SignedSaturationAndDesaturationStayFiniteAndBounded", "NoRenormalizationPreservesCapturedScale",
            "ActuatorFailureFreezesNormalizationScale", "MetricAllocationKeepsAnalyticInverseCoefficient"} <= names
    extension = build_inputs.repository / "native/px4"
    production = record["original_files"][0]
    original, patched = "float synthetic_scale = 1;\n", "float synthetic_scale = 0;\n"
    for name, contents in [(production, patched), (record["test_source"], "\n".join(
            f"TEST_F({record['test_suite']}, {name}) {{}}" for name in sorted(names)))]:
        path = build_inputs.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    production_patch = extension / record["negative_patch"]
    production_patch.write_text("".join(difflib.unified_diff(original.splitlines(True), patched.splitlines(True),
        fromfile="a/" + production, tofile="b/" + production)))
    hook = extension / "patches/0009-control-allocation-sparse-axes-functional-tests.patch"
    hook.write_text(patch_text)
    path = extension / "extension.json"
    manifest = json.loads(path.read_text())
    manifest["patches"].update({record["negative_patch"]: tool.sih.digest(production_patch),
                              "patches/0009-control-allocation-sparse-axes-functional-tests.patch": tool.sih.digest(hook)})
    manifest["files"].update({name: tool.sih.digest(build_inputs.source / name)
                             for name in [production, record["test_source"]]})
    manifest["original_files"][production] = hashlib.sha256(original.encode()).hexdigest()
    path.write_text(json.dumps(manifest))
    build_inputs.lock["px4_functional_tests"]["regressions"][selector] = record
    (build_inputs.repository / "native/dependencies.lock.json").write_text(json.dumps(build_inputs.lock))
    calls = mock_compiler(monkeypatch)
    output = tmp_path / "sparse"
    result = json.loads(build(build_inputs, output, regression=selector).read_text())
    assert result["variants"]["baseline"]["tests"]["failed_names"] == sorted(record["expected_negative_failures"])
    assert result["variants"]["candidate"]["tests"]["passed_names"] == sorted(names)
    assert result["variants"]["baseline"]["tests"]["tests"] == 11
    assert len(result["variants"]["baseline"]["tests"]["passed_names"]) == 9
    assert result["variants"]["baseline"]["changed_from_canonical"] == [production]
    assert len(calls) == 2 and all("PX4_FUNCTIONAL_TARGET=" + record["target"] in call for call in calls)
    assert all(not any("CHARACTERIZATION=" in argument for argument in call) for call in calls)
    assert (output / "source-baseline" / record["test_source"]).read_bytes() == (output / "source-candidate" / record["test_source"]).read_bytes()
    assert (build_inputs.source / production).read_text() == patched
