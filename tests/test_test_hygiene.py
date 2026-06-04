"""Guard against weak tests being counted as real coverage."""

import ast
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
DISALLOWED_TEST_PATTERNS = (
    " or True",
    "Pending code audit",
    "TODO after code audit",
)


def test_no_placeholder_test_files_or_audit_stubs():
    offenders = []

    for path in TEST_ROOT.rglob("test_*.py"):
        if path == Path(__file__).resolve():
            continue

        relative_path = path.relative_to(TEST_ROOT)
        if "placeholder" in path.name.lower():
            offenders.append(f"{relative_path}: filename contains 'placeholder'")

        text = path.read_text(encoding="utf-8")
        for pattern in DISALLOWED_TEST_PATTERNS:
            if pattern in text:
                offenders.append(f"{relative_path}: contains {pattern!r}")

    assert offenders == []


def test_pytest_tests_do_not_return_boolean_status():
    offenders = []

    for path in TEST_ROOT.rglob("test_*.py"):
        if path == Path(__file__).resolve():
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Return):
                    continue
                if isinstance(child.value, ast.Constant) and isinstance(child.value.value, bool):
                    relative_path = path.relative_to(TEST_ROOT)
                    offenders.append(f"{relative_path}:{child.lineno} returns {child.value.value!r}")

    assert offenders == []
