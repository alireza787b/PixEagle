"""Static boundaries for read-only setup reuse and explicit rebuilds."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_python_and_ai_reuse_is_verified_before_venv_transaction():
    initializer = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")

    assert "reuse_verified_python_environment" in initializer
    assert initializer.index("if reuse_verified_python_environment; then") < (
        initializer.index(
            'pixeagle_begin_venv_transaction "$VENV_DIR" "PixEagle initialization"'
        )
    )
    assert "verify-installed-requirements.py" in initializer
    assert "--verify-only" in initializer


def test_verify_only_paths_precede_package_mutation():
    pytorch = (
        PROJECT_ROOT / "scripts" / "setup" / "setup-pytorch.sh"
    ).read_text(encoding="utf-8")
    ai = (
        PROJECT_ROOT / "scripts" / "setup" / "install-ai-deps.sh"
    ).read_text(encoding="utf-8")
    pytorch_main = pytorch[pytorch.index("main() {") :]
    ai_main = ai[ai.index("main() {") :]

    assert pytorch_main.index('if [[ "$VERIFY_ONLY" == "true" ]]') < pytorch_main.index(
        "install_python_stack"
    )
    assert ai_main.index('if [[ "$VERIFY_ONLY" == "true" ]]') < ai_main.index(
        "install_ai_packages"
    )
    assert "--verify-only" in pytorch
    assert "--verify-only" in ai


def test_dlib_reuse_precedes_system_packages_and_venv_transaction():
    source = (
        PROJECT_ROOT / "scripts" / "setup" / "install-dlib.sh"
    ).read_text(encoding="utf-8")
    main_source = source[source.index("main() {") :]

    assert main_source.index("verify_existing_dlib") < main_source.index(
        "check_build_environment"
    )
    assert main_source.index("verify_existing_dlib") < main_source.index(
        "pixeagle_begin_venv_transaction"
    )


def test_opencv_reuse_uses_builder_owned_version_and_capability_contract():
    initializer = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")
    builder = (
        PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    ).read_text(encoding="utf-8")

    assert "--verify-current" in initializer
    assert "verify_current_contract" in builder
    assert 'payload.get("provider_kind") == "source_gstreamer"' in builder
    assert 'payload.get("version") == expected_version' in builder
