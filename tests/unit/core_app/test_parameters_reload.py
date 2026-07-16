"""
Tests for Parameters.reload_config() functionality (v5.3.0+)
=============================================================

Tests the hot-reload capability of the Parameters class,
including thread safety and SafetyManager integration.

Run with: pytest tests/unit/core_app/test_parameters_reload.py -v
"""

import copy
import os
import sys
import pytest
import threading
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from classes.parameters import Parameters
from classes.follower_config_manager import FollowerConfigManager
from classes.runtime_config_generation import runtime_config_barrier
from classes.safety_manager import SafetyManager


@pytest.fixture
def isolated_parameters_state():
    """Restore Parameters class state after tests that load synthetic configs."""
    previous_names = set(Parameters._dynamic_config_attributes)
    previous_values = {
        name: Parameters.__dict__[name]
        for name in previous_names
        if name in Parameters.__dict__
    }
    previous_raw_config = Parameters._raw_config
    previous_loaded_config_file = Parameters._loaded_config_file

    with patch('classes.parameters._get_safety_manager'), patch(
        'classes.parameters._get_follower_config_manager'
    ):
        try:
            yield
        finally:
            for name in set(Parameters._dynamic_config_attributes):
                if name in Parameters.__dict__:
                    delattr(Parameters, name)
            for name, value in previous_values.items():
                setattr(Parameters, name, value)

            Parameters._dynamic_config_attributes = previous_names
            Parameters._raw_config = previous_raw_config
            Parameters._loaded_config_file = previous_loaded_config_file


def write_config(path: Path, content: str) -> str:
    """Write a synthetic YAML config and return its path."""
    path.write_text(content, encoding='utf-8')
    return str(path)


def write_generation_config(path: Path, marker: int) -> str:
    """Write one coherent Parameters/safety/follower generation fixture."""
    defaults = yaml.safe_load(
        Path('configs/config_default.yaml').read_text(encoding='utf-8')
    )
    general = copy.deepcopy(defaults['Follower']['General'])
    general['TARGET_LOSS_TIMEOUT'] = float(marker)
    config = {
        'Example': {'generation_marker': marker},
        'Safety': {'GlobalLimits': {'MIN_ALTITUDE': marker}},
        'Follower': {
            'General': general,
            'FollowerOverrides': {},
        },
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return str(path)


class TestParametersReloadConfig:
    """Test Parameters.reload_config() method."""

    def test_reload_config_returns_bool(self):
        """reload_config should return a boolean."""
        result = Parameters.reload_config()
        assert isinstance(result, bool)

    def test_reload_config_success_returns_true(self):
        """Successful reload should return True."""
        # Default config file should exist and be valid
        result = Parameters.reload_config()
        assert result is True

    def test_reload_config_invalid_file_returns_false(self):
        """Invalid config file should return False."""
        result = Parameters.reload_config('nonexistent_config_file.yaml')
        assert result is False

    def test_reload_config_updates_class_attributes(self):
        """reload_config should update class attributes."""
        # First ensure config is loaded
        Parameters.reload_config()

        # Get current value of a stable attribute that must always exist
        # (DEFAULT_FPS is a core VideoSource parameter — always present)
        assert hasattr(Parameters, 'DEFAULT_FPS')
        original_value = Parameters.DEFAULT_FPS

        # Reload should work
        result = Parameters.reload_config()
        assert result is True

        # Value should still be accessible (and same since we didn't change file)
        assert hasattr(Parameters, 'DEFAULT_FPS')
        assert Parameters.DEFAULT_FPS == original_value

    def test_reload_config_is_thread_safe(self):
        """Multiple concurrent reload calls should not cause race conditions."""
        results = []
        errors = []

        def reload_task():
            try:
                result = Parameters.reload_config()
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [threading.Thread(target=reload_task) for _ in range(10)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0, f"Errors occurred during concurrent reload: {errors}"

        # All reloads should have succeeded
        assert all(r is True for r in results), "Some reloads failed"
        assert len(results) == 10


class TestParametersReloadSafetyManager:
    """Test SafetyManager integration with reload."""

    @patch('classes.parameters._get_safety_manager')
    def test_reload_notifies_safety_manager(self, mock_get_safety_manager):
        """reload_config should prepare and publish SafetyManager state."""
        mock_safety_manager = MagicMock()
        prepared_state = object()
        mock_safety_manager._prepare_runtime_state.return_value = prepared_state
        mock_get_safety_manager.return_value = mock_safety_manager

        result = Parameters.reload_config()

        assert result is True
        mock_safety_manager._prepare_runtime_state.assert_called_once()
        mock_safety_manager._publish_runtime_state.assert_called_once_with(
            prepared_state
        )
        mock_safety_manager.load_from_config.assert_not_called()

    @patch('classes.parameters._get_safety_manager')
    def test_runtime_reload_fails_closed_if_safety_manager_fails(
        self,
        mock_get_safety_manager,
    ):
        """Runtime reload must not accept a missing safety consumer."""
        mock_get_safety_manager.side_effect = Exception("SafetyManager error")

        result = Parameters.reload_config()
        assert result is False


class TestParametersReloadEdgeCases:
    """Test edge cases for reload functionality."""

    def test_reload_with_custom_config_path(self):
        """reload_config should work with custom config path."""
        # Use the checked-in default config explicitly. configs/config.yaml is
        # gitignored and may not exist in a clean clone.
        result = Parameters.reload_config('configs/config_default.yaml')
        assert result is True

    def test_reload_preserves_raw_config(self):
        """reload_config should preserve _raw_config for SafetyManager."""
        Parameters.reload_config()
        assert hasattr(Parameters, '_raw_config')
        assert Parameters._raw_config is not None

    def test_reload_multiple_times(self):
        """Multiple sequential reloads should all succeed."""
        for i in range(5):
            result = Parameters.reload_config()
            assert result is True, f"Reload {i+1} failed"


class TestParametersDynamicAttributeOwnership:
    """Test transactional ownership of config-derived class attributes."""

    def test_loads_flattened_grouped_hybrid_and_scalar_attributes(
        self, tmp_path, isolated_parameters_state
    ):
        config_file = write_config(
            tmp_path / 'attribute_shapes.yaml',
            """
FlatSection:
  flat_value: 7
Safety:
  GlobalLimits:
    MIN_ALTITUDE: 3
Follower:
  FOLLOWER_MODE: test
  enabled: false
  General:
    MAX_VELOCITY: 4
ScalarValue: ready
ScalarDisabled: false
""",
        )

        Parameters.load_config(config_file)

        assert Parameters.FLAT_VALUE == 7
        assert Parameters.Safety == {'GlobalLimits': {'MIN_ALTITUDE': 3}}
        assert Parameters.Follower['General'] == {'MAX_VELOCITY': 4}
        assert Parameters.FOLLOWER_MODE == 'test'
        assert Parameters.ENABLED is False
        assert Parameters.ScalarValue == 'ready'
        assert Parameters.ScalarDisabled is False
        assert Parameters._dynamic_config_attributes == {
            'FLAT_VALUE',
            'Safety',
            'Follower',
            'FOLLOWER_MODE',
            'ENABLED',
            'ScalarValue',
            'ScalarDisabled',
        }
        assert Parameters._raw_config['FlatSection']['flat_value'] == 7
        assert Parameters._loaded_config_file == config_file

    def test_reload_removes_only_stale_dynamic_attributes(
        self, tmp_path, isolated_parameters_state
    ):
        first_config = write_config(
            tmp_path / 'first.yaml',
            """
FlatSection:
  stale_flat: 1
Safety:
  GlobalLimits:
    MIN_ALTITUDE: 3
Follower:
  STALE_HYBRID: old
  General:
    MAX_VELOCITY: 4
stale_scalar: old
""",
        )
        second_config = write_config(
            tmp_path / 'second.yaml',
            """
Replacement:
  replacement_value: 2
""",
        )
        grouped_sections = Parameters._GROUPED_SECTIONS

        Parameters.load_config(first_config)
        assert Parameters.reload_config(
            second_config,
            strict_dependents=False,
        ) is True

        assert not hasattr(Parameters, 'STALE_FLAT')
        assert not hasattr(Parameters, 'Safety')
        assert not hasattr(Parameters, 'Follower')
        assert not hasattr(Parameters, 'STALE_HYBRID')
        assert not hasattr(Parameters, 'stale_scalar')
        assert Parameters.REPLACEMENT_VALUE == 2
        assert Parameters._dynamic_config_attributes == {'REPLACEMENT_VALUE'}
        assert Parameters._GROUPED_SECTIONS is grouped_sections
        assert callable(Parameters.reload_config)

    def test_publish_config_mapping_does_not_reread_persisted_file(
        self,
        tmp_path,
        isolated_parameters_state,
    ):
        config_file = write_config(
            tmp_path / "runtime.yaml",
            "Example:\n  value: 1\n",
        )
        Parameters.load_config(config_file)
        loaded_source = Parameters._loaded_config_file
        Path(config_file).unlink()

        Parameters.publish_config_mapping(
            {"Example": {"value": 2}},
            source="unit_selective_publish",
            strict_dependents=False,
        )

        assert Parameters.VALUE == 2
        assert Parameters.get_runtime_config_snapshot() == {
            "Example": {"value": 2}
        }
        assert Parameters._loaded_config_file == loaded_source

    def test_reserved_attribute_collision_preserves_previous_state(
        self, tmp_path, isolated_parameters_state
    ):
        valid_config = write_config(
            tmp_path / 'valid.yaml',
            """
Prior:
  prior_value: 1
""",
        )
        colliding_config = write_config(
            tmp_path / 'collision.yaml',
            """
reload_config: blocked
""",
        )
        Parameters.load_config(valid_config)
        previous_names = set(Parameters._dynamic_config_attributes)
        previous_values = {
            name: Parameters.__dict__[name]
            for name in previous_names
        }
        previous_raw_config = Parameters._raw_config
        previous_loaded_config_file = Parameters._loaded_config_file

        with pytest.raises(ValueError, match='reload_config'):
            Parameters.load_config(colliding_config)

        assert Parameters._dynamic_config_attributes == previous_names
        assert {
            name: Parameters.__dict__[name]
            for name in previous_names
        } == previous_values
        assert Parameters._raw_config is previous_raw_config
        assert Parameters._loaded_config_file == previous_loaded_config_file
        assert callable(Parameters.reload_config)

    def test_failed_reload_preserves_previous_state(
        self, tmp_path, isolated_parameters_state
    ):
        valid_config = write_config(
            tmp_path / 'valid.yaml',
            """
Prior:
  prior_value: 1
stale_scalar: retained
""",
        )
        malformed_config = write_config(
            tmp_path / 'malformed.yaml',
            'Broken: [unterminated\n',
        )
        Parameters.load_config(valid_config)
        previous_names = set(Parameters._dynamic_config_attributes)
        previous_values = {
            name: Parameters.__dict__[name]
            for name in previous_names
        }
        previous_raw_config = Parameters._raw_config
        previous_loaded_config_file = Parameters._loaded_config_file

        assert Parameters.reload_config(malformed_config) is False

        assert Parameters._dynamic_config_attributes == previous_names
        assert {
            name: Parameters.__dict__[name]
            for name in previous_names
        } == previous_values
        assert Parameters._raw_config is previous_raw_config
        assert Parameters._loaded_config_file == previous_loaded_config_file

    def test_duplicate_flattened_names_are_rejected_with_both_paths(
        self, tmp_path, isolated_parameters_state
    ):
        config_file = write_config(
            tmp_path / 'duplicate.yaml',
            """
First:
  shared_name: 1
Second:
  shared_name: 2
""",
        )

        with pytest.raises(ValueError, match=r'First\.shared_name.*Second\.shared_name'):
            Parameters.load_config(config_file)

    def test_registered_retirements_do_not_shadow_canonical_runtime_values(
        self, tmp_path, isolated_parameters_state
    ):
        config_file = write_config(
            tmp_path / 'retired-collisions.yaml',
            """
Tracking:
  APPEARANCE_CONFIDENCE_THRESHOLD: 0.5
Detector:
  APPEARANCE_CONFIDENCE_THRESHOLD: 0.7
TrackerSafety:
  BOUNDARY_MARGIN_PIXELS: 22
BOUNDARY_MARGIN_PIXELS: 99
""",
        )

        Parameters.load_config(config_file)

        assert Parameters.APPEARANCE_CONFIDENCE_THRESHOLD == 0.7
        assert Parameters.TrackerSafety['BOUNDARY_MARGIN_PIXELS'] == 22
        assert not hasattr(Parameters, 'BOUNDARY_MARGIN_PIXELS')
        assert 'Tracking' not in Parameters._raw_config

    @pytest.mark.parametrize('failing_consumer', ['safety', 'follower'])
    def test_strict_dependent_failure_restores_parameters_and_consumers(
        self,
        tmp_path,
        isolated_parameters_state,
        failing_consumer,
    ):
        first_config = write_generation_config(tmp_path / 'strict-first.yaml', 1)
        second_config = write_generation_config(tmp_path / 'strict-second.yaml', 2)
        safety_manager = SafetyManager()
        follower_manager = FollowerConfigManager()
        failing_manager = (
            safety_manager if failing_consumer == 'safety' else follower_manager
        )

        with patch(
            'classes.parameters._get_safety_manager',
            return_value=safety_manager,
        ), patch(
            'classes.parameters._get_follower_config_manager',
            return_value=follower_manager,
        ), patch.object(Parameters, '_validate_dependent_config'):
            Parameters.load_config(first_config, strict_dependents=True)
            generation_before = Parameters.get_runtime_config_generation()
            with patch.object(
                failing_manager,
                '_publish_runtime_state',
                side_effect=RuntimeError('blocked'),
            ):
                assert Parameters.reload_config(
                    second_config,
                    strict_dependents=True,
                ) is False

        assert Parameters.GENERATION_MARKER == 1
        assert Parameters._loaded_config_file == first_config
        assert safety_manager.get_limit('MIN_ALTITUDE') == 1
        assert follower_manager.get_param('TARGET_LOSS_TIMEOUT') == 1
        assert Parameters.get_runtime_config_generation() == generation_before

    def test_reload_updates_each_dependent_manager_once(
        self, tmp_path, isolated_parameters_state
    ):
        config_file = write_config(
            tmp_path / 'single-consumer-update.yaml',
            """
Example:
  owned_value: 3
""",
        )
        safety_manager = MagicMock()
        follower_manager = MagicMock()
        safety_state = object()
        follower_state = object()
        safety_manager._prepare_runtime_state.return_value = safety_state
        follower_manager._prepare_runtime_state.return_value = follower_state

        with patch(
            'classes.parameters._get_safety_manager',
            return_value=safety_manager,
        ), patch(
            'classes.parameters._get_follower_config_manager',
            return_value=follower_manager,
        ), patch.object(Parameters, '_validate_dependent_config'):
            generation_before = Parameters.get_runtime_config_generation()
            assert Parameters.reload_config(config_file) is True

        safety_manager._prepare_runtime_state.assert_called_once()
        follower_manager._prepare_runtime_state.assert_called_once()
        safety_manager._publish_runtime_state.assert_called_once_with(safety_state)
        follower_manager._publish_runtime_state.assert_called_once_with(follower_state)
        safety_manager.load_from_config.assert_not_called()
        follower_manager.load_from_config.assert_not_called()
        assert Parameters.get_runtime_config_generation() == generation_before + 1

    def test_strict_validation_failure_never_publishes_to_dependents(
        self, tmp_path, isolated_parameters_state
    ):
        first_config = write_config(
            tmp_path / 'valid-first.yaml',
            """
Example:
  owned_value: 1
""",
        )
        invalid_config = write_config(
            tmp_path / 'invalid-second.yaml',
            """
Example:
  owned_value: 2
""",
        )
        Parameters.load_config(first_config)
        generation_before = Parameters.get_runtime_config_generation()
        config_service = MagicMock()
        config_service.get_retirement_registry.return_value = {'retirements': []}
        config_service.normalize_declared_legacy_values.return_value = (
            {'Example': {'owned_value': 2}},
            [],
        )
        config_service.validate_config_mapping.return_value = MagicMock(
            valid=False,
            errors=['Safety.GlobalLimits is required'],
            warnings=[],
        )
        safety_manager = MagicMock()
        follower_manager = MagicMock()

        with patch(
            'classes.config_service.ConfigService.get_instance',
            return_value=config_service,
        ), patch(
            'classes.parameters._get_safety_manager',
            return_value=safety_manager,
        ), patch(
            'classes.parameters._get_follower_config_manager',
            return_value=follower_manager,
        ), patch(
            'classes.config_validator.normalize_safety_config',
            side_effect=lambda config, **_kwargs: config,
        ):
            assert Parameters.reload_config(
                invalid_config,
                strict_dependents=True,
            ) is False

        assert Parameters.OWNED_VALUE == 1
        assert Parameters._loaded_config_file == first_config
        config_service.validate_config_mapping.assert_called_once_with(
            {'Example': {'owned_value': 2}},
            require_safety=True,
        )
        safety_manager._prepare_runtime_state.assert_not_called()
        follower_manager._prepare_runtime_state.assert_not_called()
        assert Parameters.get_runtime_config_generation() == generation_before

    def test_strict_safety_validator_remains_an_additional_gate(
        self,
        tmp_path,
        isolated_parameters_state,
    ):
        first_config = write_config(
            tmp_path / 'safety-valid-first.yaml',
            """
Example:
  owned_value: 1
""",
        )
        second_config = write_config(
            tmp_path / 'safety-invalid-second.yaml',
            """
Example:
  owned_value: 2
""",
        )
        Parameters.load_config(first_config)
        generation_before = Parameters.get_runtime_config_generation()
        config_service = MagicMock()
        config_service.get_retirement_registry.return_value = {'retirements': []}
        config_service.normalize_declared_legacy_values.return_value = (
            {'Example': {'owned_value': 2}},
            [],
        )
        config_service.validate_config_mapping.return_value = MagicMock(
            valid=True,
            errors=[],
            warnings=[],
        )
        safety_manager = MagicMock()
        follower_manager = MagicMock()

        with patch(
            'classes.config_service.ConfigService.get_instance',
            return_value=config_service,
        ), patch(
            'classes.parameters._get_safety_manager',
            return_value=safety_manager,
        ), patch(
            'classes.parameters._get_follower_config_manager',
            return_value=follower_manager,
        ), patch(
            'classes.config_validator.normalize_safety_config',
            side_effect=ValueError('invalid safety limit'),
        ):
            assert Parameters.reload_config(second_config) is False

        config_service.validate_config_mapping.assert_called_once_with(
            {'Example': {'owned_value': 2}},
            require_safety=True,
        )
        safety_manager._prepare_runtime_state.assert_not_called()
        follower_manager._prepare_runtime_state.assert_not_called()
        assert Parameters.OWNED_VALUE == 1
        assert Parameters.get_runtime_config_generation() == generation_before

    def test_strict_null_safety_limit_never_publishes(
        self,
        tmp_path,
        isolated_parameters_state,
    ):
        default_path = Path('configs/config_default.yaml')
        config = yaml.safe_load(default_path.read_text(encoding='utf-8'))
        config['Safety']['GlobalLimits']['MAX_VELOCITY_FORWARD'] = None
        invalid_path = tmp_path / 'null-safety-limit.yaml'
        invalid_path.write_text(
            yaml.safe_dump(config, sort_keys=False),
            encoding='utf-8',
        )
        generation_before = Parameters.get_runtime_config_generation()
        raw_before = Parameters._raw_config

        assert Parameters.reload_config(
            str(invalid_path),
            strict_dependents=True,
        ) is False

        assert Parameters.get_runtime_config_generation() == generation_before
        assert Parameters._raw_config is raw_before


class TestRuntimeConfigPublicationConsistency:
    """Prove readers cannot observe an in-progress mixed generation."""

    @pytest.mark.parametrize('publication_fails', [False, True])
    def test_compound_reader_sees_only_complete_success_or_rollback(
        self,
        tmp_path,
        isolated_parameters_state,
        publication_fails,
    ):
        first_config = write_generation_config(tmp_path / 'generation-1.yaml', 1)
        second_config = write_generation_config(tmp_path / 'generation-2.yaml', 2)
        safety_manager = SafetyManager()
        follower_manager = FollowerConfigManager()
        publication_reached = threading.Event()
        release_publication = threading.Event()
        reader_done = threading.Event()
        reload_results = []
        observations = []
        thread_errors = []

        with patch(
            'classes.parameters._get_safety_manager',
            return_value=safety_manager,
        ), patch(
            'classes.parameters._get_follower_config_manager',
            return_value=follower_manager,
        ), patch.object(Parameters, '_validate_dependent_config'):
            Parameters.load_config(first_config, strict_dependents=True)
            generation_before = Parameters.get_runtime_config_generation()
            original_publish = follower_manager._publish_runtime_state

            def gated_follower_publish(state):
                publication_reached.set()
                if not release_publication.wait(timeout=3):
                    raise TimeoutError('test did not release config publication')
                if publication_fails:
                    raise RuntimeError('injected follower publication failure')
                original_publish(state)

            def reload_task():
                try:
                    reload_results.append(
                        Parameters.reload_config(
                            second_config,
                            strict_dependents=True,
                        )
                    )
                except Exception as exc:  # pragma: no cover - assertion aid
                    thread_errors.append(exc)

            def read_task():
                try:
                    with Parameters.read_generation() as generation:
                        observations.append(
                            (
                                generation,
                                Parameters.GENERATION_MARKER,
                                safety_manager.get_limit('MIN_ALTITUDE'),
                                follower_manager.get_param('TARGET_LOSS_TIMEOUT'),
                            )
                        )
                except Exception as exc:  # pragma: no cover - assertion aid
                    thread_errors.append(exc)
                finally:
                    reader_done.set()

            with patch.object(
                follower_manager,
                '_publish_runtime_state',
                side_effect=gated_follower_publish,
            ):
                writer = threading.Thread(target=reload_task)
                writer.start()
                assert publication_reached.wait(timeout=3)

                reader = threading.Thread(target=read_task)
                reader.start()
                assert not reader_done.wait(timeout=0.15)

                release_publication.set()
                writer.join(timeout=3)
                reader.join(timeout=3)

        assert not writer.is_alive()
        assert not reader.is_alive()
        assert thread_errors == []
        if publication_fails:
            assert reload_results == [False]
            assert observations == [(generation_before, 1, 1, 1)]
            assert Parameters.get_runtime_config_generation() == generation_before
        else:
            assert reload_results == [True]
            assert observations == [(generation_before + 1, 2, 2, 2)]
            assert Parameters.get_runtime_config_generation() == generation_before + 1

    def test_direct_parameter_and_manager_readers_block_during_publication(
        self,
        tmp_path,
        isolated_parameters_state,
    ):
        first_config = write_generation_config(tmp_path / 'direct-1.yaml', 1)
        second_config = write_generation_config(tmp_path / 'direct-2.yaml', 2)
        safety_manager = SafetyManager()
        follower_manager = FollowerConfigManager()
        publication_reached = threading.Event()
        release_publication = threading.Event()
        reload_results = []
        thread_errors = []
        observations = {}
        reader_done = {
            name: threading.Event()
            for name in ('parameter', 'safety', 'follower')
        }

        with patch(
            'classes.parameters._get_safety_manager',
            return_value=safety_manager,
        ), patch(
            'classes.parameters._get_follower_config_manager',
            return_value=follower_manager,
        ), patch.object(Parameters, '_validate_dependent_config'):
            Parameters.load_config(first_config, strict_dependents=True)
            original_publish = follower_manager._publish_runtime_state

            def gated_follower_publish(state):
                publication_reached.set()
                if not release_publication.wait(timeout=3):
                    raise TimeoutError('test did not release config publication')
                original_publish(state)

            def reload_task():
                try:
                    reload_results.append(Parameters.reload_config(second_config))
                except Exception as exc:  # pragma: no cover - assertion aid
                    thread_errors.append(exc)

            readers = {
                'parameter': lambda: Parameters.GENERATION_MARKER,
                'safety': lambda: safety_manager.get_limit('MIN_ALTITUDE'),
                'follower': lambda: follower_manager.get_param(
                    'TARGET_LOSS_TIMEOUT'
                ),
            }

            def read_task(name, reader):
                try:
                    observations[name] = reader()
                except Exception as exc:  # pragma: no cover - assertion aid
                    thread_errors.append(exc)
                finally:
                    reader_done[name].set()

            with patch.object(
                follower_manager,
                '_publish_runtime_state',
                side_effect=gated_follower_publish,
            ):
                writer = threading.Thread(target=reload_task)
                writer.start()
                assert publication_reached.wait(timeout=3)

                reader_threads = [
                    threading.Thread(target=read_task, args=(name, reader))
                    for name, reader in readers.items()
                ]
                for reader_thread in reader_threads:
                    reader_thread.start()
                assert all(
                    not done.wait(timeout=0.1)
                    for done in reader_done.values()
                )

                release_publication.set()
                writer.join(timeout=3)
                for reader_thread in reader_threads:
                    reader_thread.join(timeout=3)

        assert not writer.is_alive()
        assert all(not reader_thread.is_alive() for reader_thread in reader_threads)
        assert thread_errors == []
        assert reload_results == [True]
        assert observations == {
            'parameter': 2,
            'safety': 2,
            'follower': 2,
        }

    def test_direct_parameter_write_blocks_during_publication(self):
        """Live compatibility writes cannot interleave with config publication."""
        publication_reached = threading.Event()
        release_publication = threading.Event()
        write_done = threading.Event()
        errors = []

        def publication_task():
            try:
                with runtime_config_barrier.publish():
                    publication_reached.set()
                    if not release_publication.wait(timeout=3):
                        raise TimeoutError('test did not release config publication')
            except Exception as exc:  # pragma: no cover - assertion aid
                errors.append(exc)

        def write_task():
            try:
                Parameters.RUNTIME_WRITE_BARRIER_TEST = 'complete'
            except Exception as exc:  # pragma: no cover - assertion aid
                errors.append(exc)
            finally:
                write_done.set()

        publisher = threading.Thread(target=publication_task)
        writer = threading.Thread(target=write_task)
        writer_started = False
        try:
            publisher.start()
            assert publication_reached.wait(timeout=3)
            writer.start()
            writer_started = True
            assert not write_done.wait(timeout=0.15)

            release_publication.set()
            publisher.join(timeout=3)
            writer.join(timeout=3)

            assert not publisher.is_alive()
            assert not writer.is_alive()
            assert errors == []
            assert Parameters.RUNTIME_WRITE_BARRIER_TEST == 'complete'
        finally:
            release_publication.set()
            publisher.join(timeout=3)
            if writer_started:
                writer.join(timeout=3)
            if hasattr(Parameters, 'RUNTIME_WRITE_BARRIER_TEST'):
                delattr(Parameters, 'RUNTIME_WRITE_BARRIER_TEST')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
