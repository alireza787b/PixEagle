"""
Tests for schema generation option extraction behavior.
"""

import os
import sys

# Add project root to import scripts module
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, PROJECT_ROOT)

from scripts.generate_schema import extract_options  # noqa: E402


def test_extract_options_with_parenthetical_descriptions_and_prefix_text():
    description = (
        "Fixed-camera lateral guidance strategy. "
        "Options: coordinated_turn (recommended fixed camera), "
        "sideslip (advanced, may lose target)"
    )

    options, cleaned = extract_options(description)

    assert cleaned == "Fixed-camera lateral guidance strategy."
    assert options == [
        {
            "value": "coordinated_turn",
            "label": "coordinated_turn",
            "description": "recommended fixed camera",
        },
        {
            "value": "sideslip",
            "label": "sideslip",
            "description": "advanced, may lose target",
        },
    ]
