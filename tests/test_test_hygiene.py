"""Guard against weak tests being counted as real coverage."""

import ast
import re
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TEST_ROOT.parent
FRONTEND_SRC_ROOT = REPO_ROOT / "dashboard" / "src"
FRONTEND_CLIENT_ALLOWLIST = {
    Path("services/apiClient.js"),
}
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


def test_dashboard_api_calls_use_auth_client_boundary():
    """Keep browser-session cookies, CSRF, and auth-failure handling centralized."""
    offenders = []

    for path in FRONTEND_SRC_ROOT.rglob("*.js"):
        relative_path = path.relative_to(FRONTEND_SRC_ROOT)
        if relative_path in FRONTEND_CLIENT_ALLOWLIST or path.name.endswith(".test.js"):
            continue

        text = path.read_text(encoding="utf-8")
        checks = (
            (
                re.compile(r"(?<![A-Za-z0-9_$])fetch\s*\("),
                "uses raw fetch instead of apiFetch",
            ),
            (
                re.compile(r"import\s+axios\s+from\s+['\"]axios['\"]"),
                "imports axios directly instead of services/apiClient",
            ),
            (
                re.compile(r"new\s+WebSocket\s*\("),
                "constructs WebSocket directly instead of createDashboardWebSocket",
            ),
            (
                re.compile(r"href=\{endpoints\."),
                "uses a protected endpoint as a direct href",
            ),
        )
        for pattern, message in checks:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{relative_path}:{line}: {message}")

    assert offenders == []


def test_dashboard_does_not_reconstruct_direct_backend_urls_outside_endpoint_registry():
    """Reverse-proxy clients must not bypass `/pixeagle-api` with raw port URLs."""
    allowed = {
        Path("services/apiEndpoints.js"),
    }
    direct_api_pattern = re.compile(
        r"apiConfig\.(?:protocol|apiHost|apiPort)|"
        r"\$\{[^}]*apiHost[^}]*\}:\$\{[^}]*apiPort[^}]*\}"
    )
    offenders = []

    for path in FRONTEND_SRC_ROOT.rglob("*.js"):
        relative_path = path.relative_to(FRONTEND_SRC_ROOT)
        if relative_path in allowed or path.name.endswith(".test.js"):
            continue
        if direct_api_pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(relative_path))

    assert offenders == [], (
        "Dashboard modules must use the canonical endpoint registry so "
        f"`production_remote` stays behind `/pixeagle-api`: {offenders}"
    )
