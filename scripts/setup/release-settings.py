"""Prepare and validate the saved YAML using the target release in an isolated checkout."""

import hashlib
import json
import sys
from pathlib import Path

from ruamel.yaml import YAML

from classes.config_service import ConfigService


def leaves(value, keys=()):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from leaves(child, (*keys, key))
    else:
        yield keys, value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def prepare_settings(source, backup_dir):
    yaml = YAML()
    yaml.preserve_quotes = True
    service = ConfigService(Path.cwd())
    current = Path("configs/config.yaml")
    review = []
    saved = yaml.load(source.read_text()) if source.is_file() else service.get_default()
    edited = backup_dir / "edited-defaults.yaml"
    changed = False
    if edited.is_file() and source.is_file():
        original = dict(leaves(yaml.load((backup_dir / "original-defaults.yaml").read_text())))
        sentinel = object()
        for path, value in leaves(yaml.load(edited.read_text())):
            if value != original.get(path, sentinel) and not service._mapping_path_exists(
                saved, path
            ):
                service._set_mapping_path(saved, path, value)
                changed = True
    # Validate against the candidate definitions before exposing a migration.
    normalized, _ = service.normalize_declared_legacy_values(saved)
    result = service.validate_config_mapping(normalized, require_safety=True)
    if not result.valid:
        defaults = dict(leaves(service.get_default()))
        for path, value in list(leaves(normalized)):
            key = list(path)
            if path not in defaults or value == defaults[path] or service.is_sensitive_path(key):
                continue
            if service.get_path_schema(key) and not service.validate_path(key, value).valid:
                replacement = defaults[path]
                review.append(
                    {
                        "path": ".".join(path),
                        "before": service.redact_value(value, key),
                        "after": service.redact_value(replacement, key),
                    }
                )
                service._set_mapping_path(saved, path, replacement)
                changed = True
        normalized, _ = service.normalize_declared_legacy_values(saved)
        result = service.validate_config_mapping(normalized, require_safety=True)
        if not result.valid:
            raise ValueError(
                "These saved settings require manual review: " + "; ".join(result.errors)
            )
    if changed:
        with current.open("w") as stream:
            yaml.dump(saved, stream)
    elif source.exists():
        current.write_bytes(source.read_bytes())
    # The candidate's strict runtime loader also checks cross-field invariants.
    from classes.parameters import Parameters

    Parameters.load_config(strict_dependents=True)
    loaded = ConfigService.get_instance().get_startup_effective_config()
    if current.is_file():
        (backup_dir / "prepared-config.yaml").write_bytes(current.read_bytes())
    return {
        "changes": review,
        "digest": digest(review) if review else None,
        "effective": digest(loaded),
    }


if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    result = prepare_settings(source, destination)
    (destination / "settings-preview.json").write_text(json.dumps(result))
