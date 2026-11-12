"""Build the canonical PX4 functional regression and its isolated negative control."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from tools import sih_baseline as sih


ROOT = Path(__file__).resolve().parents[1]


def select_regression(repository: Path, selector: str | None) -> tuple[str, dict]:
    spec = json.loads((repository / "native/dependencies.lock.json").read_text())["px4_functional_tests"]
    name = spec["default_regression"] if selector is None else selector
    if not isinstance(name, str) or name not in spec["regressions"]:
        raise ValueError("Unknown native functional regression: " + str(name))
    record = spec["regressions"][name]
    fields = {"target", "test_source", "test_suite", "negative_patch", "original_files",
              "expected_tests", "expected_negative_failures", "characterization_env"}
    if not isinstance(record, dict) or set(record) != fields:
        raise ValueError("Incomplete native functional regression: " + name)
    if (any(not isinstance(record[key], str) for key in ["target", "test_source", "test_suite", "negative_patch"])
            or not isinstance(record["original_files"], list)
            or any(not isinstance(path, str) for path in record["original_files"])
            or not isinstance(record["expected_negative_failures"], list)
            or any(not isinstance(case, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", case)
                   for case in record["expected_negative_failures"])
            or record["characterization_env"] is not None and not isinstance(record["characterization_env"], str)):
        raise ValueError("Invalid native functional regression field types: " + name)
    paths = [record["test_source"], record["negative_patch"], *record["original_files"]]
    if (not record["original_files"] or len(set(record["original_files"])) != len(record["original_files"])
            or any(not isinstance(path, str) or Path(path).is_absolute() or ".." in Path(path).parts for path in paths)
            or not record["test_source"].startswith("src/") or not record["test_source"].endswith("Test.cpp")
            or not record["negative_patch"].startswith("patches/") or not record["negative_patch"].endswith(".patch")
            or any(not path.startswith("src/") for path in record["original_files"])
            or not re.fullmatch(r"functional-[A-Za-z_][A-Za-z0-9_]*", record["target"])
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", record["test_suite"])
            or type(record["expected_tests"]) is not int or record["expected_tests"] <= 1
            or not record["expected_negative_failures"]
            or len(set(record["expected_negative_failures"])) != len(record["expected_negative_failures"])
            or len(record["expected_negative_failures"]) >= record["expected_tests"]
            or record["characterization_env"] is not None
            and not re.fullmatch(r"[A-Z][A-Z0-9_]*", record["characterization_env"])):
        raise ValueError("Invalid native functional regression: " + name)
    manifest = json.loads((repository / "native/px4/extension.json").read_text())
    if (record["negative_patch"] not in manifest["patches"] or record["test_source"] not in manifest["files"]
            or any(path not in manifest.get("original_files", {}) or path not in manifest["files"]
                   for path in record["original_files"])):
        raise ValueError("Selected regression is not present in the canonical extension: " + name)
    return name, record


def write_json(path: Path, value: object) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def dependency_entries(source: Path) -> list:
    entries = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            if not path.resolve().is_relative_to(source.resolve()):
                raise ValueError("Dependency link leaves its pinned source tree")
            value = {"symlink": str(path.readlink())}
        elif path.is_file():
            value = sih.digest(path)
        elif path.is_dir():
            continue
        else:
            raise ValueError("Unsupported dependency source entry")
        entries.append([str(relative), value])
    return entries


def verify_dependencies(cache: Path, spec: dict) -> dict:
    verified = {}
    for name, pin in spec["dependencies"].items():
        source = cache / pin["relative_cache_directory"]
        if source.is_symlink() or not source.is_dir():
            raise ValueError("Missing regular functional dependency: " + name)
        entries = dependency_entries(source)
        digest = hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()
        if digest != pin["source_tree_sha256"] or len(entries) != pin["source_file_count"]:
            raise ValueError("Functional dependency source changed: " + name)
        verified[name] = {"sha256": digest, "files": len(entries)}
        if (source / ".git").exists():
            head = sih.command("git", "-C", str(source), "rev-parse", "HEAD")
            if (Path(sih.command("git", "-C", str(source), "rev-parse", "--show-toplevel")).resolve() != source.resolve()
                    or head != pin.get("git_commit") or sih.command("git", "-C", str(source), "status", "--porcelain")):
                raise ValueError("Functional dependency Git revision/worktree changed: " + name)
            verified[name]["git_commit"] = head
    return verified


def prepare_dependencies(cache: Path, spec: dict) -> dict:
    """Network access is limited to preparation; existing sources are never repaired."""
    cache.mkdir(parents=True, exist_ok=True)
    for name, pin in spec["dependencies"].items():
        destination = cache / pin["relative_cache_directory"]
        if destination.exists() or destination.is_symlink():
            continue
        with tempfile.TemporaryDirectory(prefix="functional-dependency-", dir=cache) as directory:
            temporary = Path(directory)
            source = temporary / "source"
            if "git_commit" in pin:
                subprocess.run(["git", "clone", "--no-checkout", pin["repository"], str(source)], check=True)
                subprocess.run(["git", "-C", str(source), "checkout", "--detach", pin["git_commit"]], check=True)
            else:
                archive = temporary / pin["archive_name"]
                with urllib.request.urlopen(pin["url"], timeout=60) as response, archive.open("wb") as stream:
                    shutil.copyfileobj(response, stream)
                if sih.digest(archive) != pin["archive_sha256"]:
                    raise ValueError("Functional dependency archive checksum mismatch: " + name)
                source.mkdir()
                with zipfile.ZipFile(archive) as bundle:
                    for member in bundle.infolist():
                        target = source / member.filename
                        if (not target.resolve().is_relative_to(source.resolve())
                                or (member.external_attr >> 16) & 0o170000 == 0o120000):
                            raise ValueError("Unsafe functional dependency archive entry")
                    bundle.extractall(source)
            verify_dependencies(temporary, {"dependencies": {name: pin | {"relative_cache_directory": "source"}}})
            source.rename(destination)
    return verify_dependencies(cache, spec)


@contextmanager
def source_authority(repository: Path, variant: str, regression: dict | None = None):
    """Only the negative control has a temporary, derived verification authority."""
    if variant == "candidate":
        yield repository
        return
    if regression is None:
        _, regression = select_regression(repository, None)
    with tempfile.TemporaryDirectory(prefix="px4-negative-authority-") as directory:
        temporary = Path(directory)
        shutil.copytree(repository / "native/px4", temporary / "native/px4")
        shutil.copyfile(repository / "native/dependencies.lock.json", temporary / "native/dependencies.lock.json")
        path = temporary / "native/px4/extension.json"
        manifest = json.loads(path.read_text())
        del manifest["patches"][regression["negative_patch"]]
        for name in regression["original_files"]:
            manifest["files"][name] = manifest["original_files"][name]
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        yield temporary


def verify_functional_source(source: Path, repository: Path, spec: dict, verify_extension) -> dict:
    provenance = sih.verify_source(source, repository, verify_extension)
    fuzz = next((row for row in provenance["submodules"] if row.split()[1] == spec["fuzztest_path"]), None)
    if fuzz is None or fuzz.split()[0] != spec["fuzztest_gitlink"]:
        raise ValueError("Functional tests need the initialized pinned fuzztest submodule")
    for relative in ["", *(row.split()[1] for row in provenance["submodules"])]:
        module = source / relative
        if Path(sih.command("git", "-C", str(module), "rev-parse", "--show-toplevel")).resolve() != module:
            raise ValueError("Functional source Git worktree leaves the isolated checkout")
        alternate = Path(sih.command("git", "-C", str(module), "rev-parse", "--git-path", "objects/info/alternates"))
        if (module / alternate).exists():
            raise ValueError("Functional source Git objects must be self-contained")
    return provenance


def ignored_files(source: Path, provenance: dict) -> set[str]:
    result = set()
    for relative in ["", *(row.split()[1] for row in provenance["submodules"])]:
        output = sih.command("git", "-C", str(source / relative), "ls-files", "--others",
                             "--ignored", "--exclude-standard", "-z")
        result.update(str(Path(relative) / name) for name in output.split("\0") if name)
    return result


def source_snapshot(source: Path, generated: dict) -> dict:
    result = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if ".git" in relative.parts or relative.parts[0] == "build" or str(relative) in generated:
            continue
        if path.is_symlink():
            if not path.resolve().is_relative_to(source):
                raise ValueError("Functional source link leaves the checkout")
            result[str(relative)] = {"symlink": str(path.readlink())}
        elif path.is_file():
            result[str(relative)] = {"sha256": sih.digest(path), "executable": bool(path.stat().st_mode & 0o111)}
        elif not path.is_dir():
            raise ValueError("Unsupported functional source entry")
    return result


def source_integrity(source: Path, expected: dict, policy: dict, provenance: dict, *, operator=False) -> dict:
    if source_snapshot(source, policy["outputs"]) != expected:
        raise ValueError("Functional source inputs changed")
    ignored = ignored_files(source, provenance)
    unexpected = ignored - policy["outputs"].keys()
    if operator:
        unexpected = {name for name in unexpected if not name.startswith("build/")}
    if unexpected:
        raise ValueError("Unreviewed ignored functional source files: " + ", ".join(sorted(unexpected)))
    for name, digest in policy["source_pins"].items():
        if sih.digest(source / name) != digest:
            raise ValueError("Functional configure source changed: " + name)
    generated = {}
    for name, item in policy["outputs"].items():
        if sih.digest(source / item["template"]) != item["template_sha256"]:
            raise ValueError("Functional configure template changed: " + name)
        path = source / name
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file():
                raise ValueError("Invalid functional generated file: " + name)
            if item["mode"] == "COPYONLY" and sih.digest(path) != item["template_sha256"]:
                raise ValueError("Functional configure copy differs: " + name)
            generated[name] = sih.digest(path)
    return {"source_entries": len(expected), "generated_files": generated, "ignored_files": sorted(ignored)}


def validate_result(path: Path, returncode: int, variant: str, expected: set[str], negative: set[str],
                    *, suite: str | None = None) -> dict:
    if not path.is_file():
        raise ValueError("Functional build produced no native XML")
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    names = [case.get("name") for case in cases]
    failures = {case.get("name") for case in cases if case.find("failure") is not None}
    if (len(names) != len(expected) or set(names) != expected or root.findall(".//skipped")
            or root.findall(".//error") or root.get("disabled") != "0" or root.get("errors") != "0"
            or any(case.get("status") != "run" or case.get("result") != "completed" for case in cases)
            or suite is not None and (len(root.findall("testsuite")) != 1
                or root.find("testsuite").get("name") != suite
                or any(case.get("classname") != suite for case in cases))
            or int(root.get("tests", -1)) != len(expected) or int(root.get("failures", -1)) != len(failures)):
        raise ValueError("Functional XML does not contain the complete executed regression")
    if returncode != (8 if variant == "baseline" else 0) or failures != (negative if variant == "baseline" else set()):
        raise ValueError("Unexpected native functional result")
    return {"raw_exit_code": returncode, "tests": len(names), "failed_names": sorted(failures),
            "passed_names": sorted(expected - failures), "xml_sha256": sih.digest(path)}


def build_functional(source: Path, output: Path, cache: Path, *, prepare_only: bool,
                     verify_extension, repository: Path = ROOT, regression: str | None = None) -> Path:
    previous = os.environ.get("GIT_OPTIONAL_LOCKS")
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return _build_functional(source, output, cache, prepare_only=prepare_only,
                                 verify_extension=verify_extension, repository=repository, regression=regression)
    finally:
        if previous is None:
            os.environ.pop("GIT_OPTIONAL_LOCKS", None)
        else:
            os.environ["GIT_OPTIONAL_LOCKS"] = previous


def _build_functional(source: Path, output: Path, cache: Path, *, prepare_only: bool,
                      verify_extension, repository: Path, regression: str | None) -> Path:
    source, output, cache = (path.expanduser().resolve() for path in (source, output, cache))
    if source.is_relative_to(output) or output.is_relative_to(source) or cache.is_relative_to(source):
        raise ValueError("Keep functional build evidence/cache separate from operator source")
    if output.exists():
        raise ValueError("Use a new functional output directory; evidence is never overwritten")
    regression_name, record = select_regression(repository, regression)
    firmware, compiler = sih.authority(repository)
    spec = json.loads((repository / "native/dependencies.lock.json").read_text())["px4_functional_tests"]
    if set(spec["dependencies"]) != {"googletest", "re2", "abseil-cpp", "antlr_cpp"}:
        raise ValueError("Unsupported native functional dependency set")
    submodules = [*compiler["submodules"], spec["fuzztest_path"]]
    if (len(set(submodules)) != len(submodules) or any(not isinstance(path, str) or Path(path).is_absolute()
            or ".." in Path(path).parts or not re.fullmatch(r"[A-Za-z0-9_./-]+", path) for path in submodules)):
        raise ValueError("Invalid locked functional submodule paths")
    policy = json.loads((repository / "native/px4/functional-generated-files.json").read_text())
    if len(policy["outputs"]) != policy["expected_output_paths"]:
        raise ValueError("Functional generated-file policy is incomplete")
    provenance = verify_functional_source(source, repository, spec, verify_extension)
    original = source_snapshot(source, policy["outputs"])
    source_integrity(source, original, policy, provenance, operator=True)
    expected = set(re.findall(r"^TEST_F\(" + re.escape(record["test_suite"]) + r", (\w+)\)",
                              (source / record["test_source"]).read_text(), re.M))
    negative = set(record["expected_negative_failures"])
    if len(expected) != record["expected_tests"] or not negative < expected:
        raise ValueError("Canonical functional test names differ from the locked regression")
    output.mkdir(parents=True)
    result = {"scope": "Native functional reference/controller component only; no flight/adoption qualification",
              "firmware": firmware, "compiler": compiler["toolchain_image"], "source": provenance,
              "lock_sha256": sih.digest(repository / "native/dependencies.lock.json"),
              "policy_sha256": sih.digest(repository / "native/px4/functional-generated-files.json"),
              "script_sha256": sih.digest(repository / "native/px4/build-functional-tests.sh"),
              "builder_sha256": sih.digest(Path(__file__)),
              "compiler_entrypoint_override": None,
              "operator_Git_optional_locks": "0",
              "regression": regression_name, "regression_record": record,
              "prepared_only": prepare_only, "completed": False, "variants": {}}
    try:
        result["dependencies"] = prepare_dependencies(cache, spec)
        for variant in ("baseline", "candidate"):
            copied = output / ("source-" + variant)
            def exclude(directory, names):
                return {name for name in names if (Path(directory) == source and name == "build")
                        or str((Path(directory) / name).relative_to(source)) in policy["outputs"]}
            shutil.copytree(source, copied, symlinks=True, ignore=exclude)
            if source_snapshot(copied, policy["outputs"]) != original:
                raise ValueError("Operator source changed during functional preparation")
            if variant == "baseline":
                patch = repository / "native/px4" / record["negative_patch"]
                subprocess.run(["git", "-C", str(copied), "apply", "--reverse", "--check", str(patch)], check=True)
                subprocess.run(["git", "-C", str(copied), "apply", "--reverse", str(patch)], check=True)
            with source_authority(repository, variant, record) as effective:
                snapshot = source_snapshot(copied, policy["outputs"])
                changed = sorted(key for key in original.keys() | snapshot.keys() if original.get(key) != snapshot.get(key))
                if changed != (sorted(record["original_files"]) if variant == "baseline" else []):
                    raise ValueError("Negative control must omit only the selected production patch")
                checked = verify_functional_source(copied, effective, spec, verify_extension)
                write_json(output / (variant + "-source-inputs.json"), snapshot)
                state = {"effective_authority_sha256": sih.digest(effective / "native/px4/extension.json"),
                         "source_inputs_sha256": sih.digest(output / (variant + "-source-inputs.json")),
                         "changed_from_canonical": changed,
                         "omitted_patch": record["negative_patch"] if variant == "baseline" else None,
                         "source": checked, "before": source_integrity(copied, snapshot, policy, checked)}
                result["variants"][variant] = state
                build = output / (variant + "-debug")
                argv = ["docker", "run", "--rm", "--pull=never", "--network", "none", "--platform", compiler["platform"],
                        "--cpus", "2", "--memory", "4g", "--env", "PYTHONDONTWRITEBYTECODE=1",
                        "--env", "PX4_GIT_SUBMODULES=" + ";".join(submodules),
                        "--env", "PX4_FUNCTIONAL_TARGET=" + record["target"],
                        "--env", "PX4_FUZZTEST_PATH=" + spec["fuzztest_path"],
                        "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                        "--mount", f"type=bind,src={copied},dst=/source",
                        "--mount", f"type=bind,src={cache},dst=/deps,readonly",
                        "--mount", f"type=bind,src={build},dst=/build",
                        "--mount", f"type=bind,src={repository / 'native/px4'},dst=/plan,readonly",
                        compiler["toolchain_image"], "bash", "/plan/build-functional-tests.sh"]
                if record["characterization_env"] is not None:
                    at = argv.index("--user")
                    argv[at:at] = ["--env", record["characterization_env"] + "=/build/native-characterization.csv"]
                state["argv"] = argv
                if prepare_only:
                    continue
                build.mkdir()
                state["raw_exit_code"] = None
                with (output / (variant + "-build.log")).open("x") as log:
                    try:
                        process = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=False)
                        state["raw_exit_code"] = process.returncode
                    except OSError as error:
                        state["build_error"] = type(error).__name__ + ": " + str(error)
                state["log_sha256"] = sih.digest(output / (variant + "-build.log"))
                state["build_artifacts"] = {name: sih.digest(build / name) for name in
                    ("native-tests.xml", "native-characterization.csv", record["target"], "build.ninja", "compile_commands.json")
                    if (build / name).is_file()}
                errors = {}
                postchecks = {
                    "after": lambda: source_integrity(copied, snapshot, policy, checked),
                    "authority_after": lambda: verify_functional_source(copied, effective, spec, verify_extension),
                    "dependencies_after": lambda: verify_dependencies(cache, spec),
                    "tests": lambda: validate_result(build / "native-tests.xml", state["raw_exit_code"], variant,
                                                     expected, negative, suite=record["test_suite"]),
                }
                for name, check in postchecks.items():
                    try:
                        state[name] = check()
                    except Exception as error:
                        errors[name] = type(error).__name__ + ": " + str(error)
                if len(state.get("after", {}).get("generated_files", {})) != policy["expected_output_paths"]:
                    errors["generated_files"] = "Incomplete known configure output set"
                if errors:
                    state["postcheck_errors"] = errors
                    state["outcome"] = "build_or_validation_failed"
                    raise ValueError("Native functional validation failed: " + json.dumps(errors))
                state["outcome"] = "expected_negative_control" if variant == "baseline" else "candidate_passed"
                if variant == "candidate":
                    for name in ("build.ninja", "compile_commands.json"):
                        if sih.digest(output / "baseline-debug" / name) != sih.digest(build / name):
                            raise ValueError("Functional control and candidate build options differ")
        result["completed"] = True
    except BaseException as error:
        result["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        operator_error = None
        try:
            result["operator_source_after"] = source_integrity(source, original, policy, provenance, operator=True)
            verify_functional_source(source, repository, spec, verify_extension)
        except Exception as error:
            operator_error = error
            result["completed"] = False
            result["operator_source_error"] = type(error).__name__ + ": " + str(error)
        write_json(output / "functional-results.json", result)
        if operator_error is not None:
            raise ValueError("Operator source changed during functional build") from operator_error
    print("Native functional evidence: " + str(output))
    return output / "functional-results.json"
