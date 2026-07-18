"""Dashboard tracking defaults that must stay aligned with the built client."""

from pathlib import Path
import re

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_click_roi_fallback_matches_dashboard_default():
    """Fresh installs and builds without a generated .env must behave identically."""
    dashboard_defaults = yaml.safe_load(
        (PROJECT_ROOT / "dashboard" / "env_default.yaml").read_text(encoding="utf-8")
    )
    hook_source = (
        PROJECT_ROOT / "dashboard" / "src" / "hooks" / "useBoundingBoxHandlers.js"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"const FALLBACK_BOUNDING_BOX_SIZE = (?P<value>\d+(?:\.\d+)?);",
        hook_source,
    )

    assert match is not None
    assert float(match.group("value")) == float(
        dashboard_defaults["REACT_APP_DEFAULT_BOUNDING_BOX_SIZE"]
    )

