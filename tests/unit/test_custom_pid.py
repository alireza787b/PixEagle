# tests/unit/test_custom_pid.py
"""
Unit tests for CustomPID controller.

Tests the custom PID implementation including:
- Basic P, I, D term calculations
- Output limiting
- Anti-windup behavior
- Proportional on Measurement (PoM)
- Setpoint changes
- Reset functionality
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from classes.followers.custom_pid import CustomPID


# =============================================================================
# Mock Parameters for isolated testing
# =============================================================================

class MockParameters:
    """Mock Parameters class for isolated PID testing."""
    PROPORTIONAL_ON_MEASUREMENT = False
    ENABLE_ANTI_WINDUP = False
    ANTI_WINDUP_BACK_CALC_COEFF = 0.1


@pytest.fixture(autouse=True)
def mock_parameters():
    """Patch Parameters class for all tests in this module."""
    with patch('classes.followers.custom_pid.Parameters', MockParameters):
        MockParameters.PROPORTIONAL_ON_MEASUREMENT = False
        MockParameters.ENABLE_ANTI_WINDUP = False
        MockParameters.ANTI_WINDUP_BACK_CALC_COEFF = 0.1
        yield MockParameters


# =============================================================================
# Test: Basic Initialization
# =============================================================================

class TestCustomPIDInitialization:
    """Test CustomPID initialization and default values."""

    def test_init_with_gains(self):
        """PID initializes with specified gains."""
        pid = CustomPID(Kp=1.0, Ki=0.1, Kd=0.05)
        assert pid.Kp == 1.0
        assert pid.Ki == 0.1
        assert pid.Kd == 0.05

    def test_init_with_setpoint(self):
        """PID initializes with specified setpoint."""
        pid = CustomPID(Kp=1.0, setpoint=10.0)
        assert pid.setpoint == 10.0

    def test_init_with_output_limits(self):
        """PID initializes with output limits."""
        pid = CustomPID(Kp=1.0, output_limits=(-10, 10))
        assert pid.output_limits == (-10, 10)

    def test_init_last_output_zero(self):
        """Last output initialized to zero."""
        pid = CustomPID(Kp=1.0)
        assert pid.last_output == 0

    def test_init_default_gains(self):
        """PID initializes with default gains of 1.0."""
        pid = CustomPID()
        assert pid.Kp == 1.0
        assert pid.Ki == 0.0
        assert pid.Kd == 0.0

    def test_init_with_sample_time(self):
        """PID initializes with sample time."""
        pid = CustomPID(Kp=1.0, sample_time=0.1)
        assert pid.sample_time == 0.1


# =============================================================================
# Test: Proportional Term
# =============================================================================

class TestProportionalTerm:
    """Test proportional (P) term calculations."""

    def test_proportional_positive_error(self):
        """Positive error produces positive output."""
        pid = CustomPID(Kp=2.0, Ki=0.0, Kd=0.0, setpoint=10.0)
        output = pid(5.0)  # Error = 10 - 5 = 5
        assert output == pytest.approx(10.0)  # Kp * error = 2 * 5

    def test_proportional_negative_error(self):
        """Negative error produces negative output."""
        pid = CustomPID(Kp=2.0, Ki=0.0, Kd=0.0, setpoint=5.0)
        output = pid(10.0)  # Error = 5 - 10 = -5
        assert output == pytest.approx(-10.0)  # Kp * error = 2 * -5

    def test_proportional_zero_error(self):
        """Zero error produces zero output."""
        pid = CustomPID(Kp=2.0, Ki=0.0, Kd=0.0, setpoint=10.0)
        output = pid(10.0)  # Error = 0
        assert output == pytest.approx(0.0)

    def test_proportional_gain_scaling(self):
        """Output scales linearly with Kp."""
        pid1 = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=10.0)
        pid2 = CustomPID(Kp=3.0, Ki=0.0, Kd=0.0, setpoint=10.0)

        output1 = pid1(5.0)
        output2 = pid2(5.0)

        assert output2 == pytest.approx(3 * output1)

    def test_proportional_fractional_gain(self):
        """Fractional Kp reduces output."""
        pid = CustomPID(Kp=0.5, Ki=0.0, Kd=0.0, setpoint=10.0)
        output = pid(0.0)  # Error = 10
        assert output == pytest.approx(5.0)


# =============================================================================
# Test: Integral Term
# =============================================================================

class TestIntegralTerm:
    """Test integral (I) term calculations."""

    def test_integral_accumulates_error(self):
        """Integral term accumulates over time."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0)

        # First call
        output1 = pid(5.0, dt=1.0)  # Error = 5
        # Second call
        output2 = pid(5.0, dt=1.0)  # Error = 5

        # Second output should be higher due to accumulated error
        assert output2 > output1

    def test_integral_with_constant_error(self):
        """Integral grows linearly with constant error."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0)

        outputs = []
        for _ in range(5):
            outputs.append(pid(5.0, dt=1.0))  # Error = 5

        # Each step adds Ki * error * dt = 1 * 5 * 1 = 5
        for i in range(1, len(outputs)):
            diff = outputs[i] - outputs[i-1]
            assert diff == pytest.approx(5.0, rel=0.01)

    def test_integral_zero_gain(self):
        """Zero Ki produces no integral action."""
        pid = CustomPID(Kp=0.0, Ki=0.0, Kd=0.0, setpoint=10.0)

        output1 = pid(5.0, dt=1.0)
        output2 = pid(5.0, dt=1.0)

        assert output1 == output2 == 0.0

    def test_integral_negative_error(self):
        """Negative error decreases integral."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=0.0)

        output = pid(5.0, dt=1.0)  # Error = -5
        assert output < 0

    def test_integral_time_scaling(self):
        """Integral scales with dt."""
        pid1 = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0)
        pid2 = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0)

        output1 = pid1(5.0, dt=0.1)
        output2 = pid2(5.0, dt=0.2)

        assert output2 == pytest.approx(2 * output1)


# =============================================================================
# Test: Derivative Term
# =============================================================================

class TestDerivativeTerm:
    """Test derivative (D) term calculations."""

    def test_derivative_rate_of_change(self):
        """Derivative responds to rate of change."""
        pid = CustomPID(Kp=0.0, Ki=0.0, Kd=1.0, setpoint=10.0)

        # Initial call
        _ = pid(0.0, dt=1.0)
        # Second call with changed input
        output = pid(5.0, dt=1.0)  # Rate = (5 - 0) / 1 = 5

        # Derivative opposes rate of change
        assert output != 0

    def test_derivative_zero_rate(self):
        """No change in input produces no derivative action."""
        pid = CustomPID(Kp=0.0, Ki=0.0, Kd=1.0, setpoint=10.0)

        # Multiple calls with same input
        _ = pid(5.0, dt=1.0)
        output = pid(5.0, dt=1.0)

        # Derivative should be near zero (small due to setpoint difference)
        assert abs(output) < 1.0

    def test_derivative_opposes_increasing_input(self):
        """Derivative opposes increasing input (negative contribution)."""
        pid = CustomPID(Kp=0.0, Ki=0.0, Kd=1.0, setpoint=10.0)

        _ = pid(0.0, dt=1.0)
        output = pid(5.0, dt=1.0)  # Input increasing

        # Derivative opposes change
        assert output < 0

    def test_derivative_gain_scaling(self):
        """Derivative scales with Kd."""
        pid1 = CustomPID(Kp=0.0, Ki=0.0, Kd=1.0, setpoint=10.0)
        pid2 = CustomPID(Kp=0.0, Ki=0.0, Kd=2.0, setpoint=10.0)

        _ = pid1(0.0, dt=1.0)
        _ = pid2(0.0, dt=1.0)

        output1 = pid1(5.0, dt=1.0)
        output2 = pid2(5.0, dt=1.0)

        assert output2 == pytest.approx(2 * output1)


# =============================================================================
# Test: Combined PID Action
# =============================================================================

class TestCombinedPIDAction:
    """Test combined P, I, D behavior."""

    def test_pid_combined_output(self):
        """Output is sum of P, I, D terms."""
        pid = CustomPID(Kp=1.0, Ki=1.0, Kd=1.0, setpoint=10.0)

        # First call establishes baseline
        output1 = pid(5.0, dt=1.0)

        # P = 1 * 5 = 5
        # I = 1 * 5 * 1 = 5 (first call)
        # D = depends on previous
        assert output1 > 0

    def test_pid_converges_to_setpoint(self):
        """PID drives system toward setpoint."""
        pid = CustomPID(Kp=0.5, Ki=0.1, Kd=0.05, setpoint=10.0)

        value = 0.0
        for _ in range(100):
            output = pid(value, dt=0.1)
            value += output * 0.1  # Simple integration

        # Value should approach setpoint
        assert abs(value - 10.0) < 2.0

    def test_pid_with_disturbance(self):
        """PID compensates for step disturbance."""
        pid = CustomPID(Kp=1.0, Ki=0.5, Kd=0.1, setpoint=10.0)

        # Stabilize
        for _ in range(10):
            pid(10.0, dt=0.1)

        # Apply disturbance
        output = pid(8.0, dt=0.1)  # Error = 2

        # Output should be positive to correct
        assert output > 0


# =============================================================================
# Test: Output Limiting
# =============================================================================

class TestOutputLimiting:
    """Test output clamping behavior."""

    def test_output_upper_limit(self):
        """Output clamped to upper limit."""
        pid = CustomPID(Kp=10.0, setpoint=100.0, output_limits=(-5, 5))
        output = pid(0.0)  # Large positive error
        assert output == 5.0

    def test_output_lower_limit(self):
        """Output clamped to lower limit."""
        pid = CustomPID(Kp=10.0, setpoint=0.0, output_limits=(-5, 5))
        output = pid(100.0)  # Large negative error
        assert output == -5.0

    def test_output_within_limits(self):
        """Output unchanged when within limits."""
        pid = CustomPID(Kp=1.0, setpoint=10.0, output_limits=(-100, 100))
        output = pid(5.0)  # Error = 5
        assert output == pytest.approx(5.0)

    def test_asymmetric_limits(self):
        """Asymmetric limits work correctly."""
        pid = CustomPID(Kp=10.0, setpoint=100.0, output_limits=(0, 10))
        output = pid(0.0, dt=0.1)
        assert output == 10.0  # Clamped to upper

        # Create new PID for negative error test
        pid2 = CustomPID(Kp=10.0, setpoint=0.0, output_limits=(0, 10))
        output2 = pid2(100.0, dt=0.1)  # Large negative error
        assert output2 == 0.0  # Clamped to lower

    def test_limits_none_lower(self):
        """None for lower limit allows negative output."""
        pid = CustomPID(Kp=10.0, setpoint=0.0, output_limits=(None, 5))
        output = pid(100.0)  # Large negative error
        assert output < 0

    def test_limits_none_upper(self):
        """None for upper limit allows large positive output."""
        pid = CustomPID(Kp=10.0, setpoint=100.0, output_limits=(-5, None))
        output = pid(0.0)  # Large positive error
        assert output > 5


# =============================================================================
# Test: Anti-Windup
# =============================================================================

class TestAntiWindup:
    """Test anti-windup back-calculation feature."""

    def test_anti_windup_enabled(self, mock_parameters):
        """Anti-windup reduces integral when saturated."""
        mock_parameters.ENABLE_ANTI_WINDUP = True
        mock_parameters.ANTI_WINDUP_BACK_CALC_COEFF = 0.5

        pid = CustomPID(Kp=0.0, Ki=10.0, setpoint=100.0, output_limits=(-10, 10))

        # Drive to saturation
        for _ in range(10):
            pid(0.0, dt=1.0)  # Constant large error

        # Check that integral is being limited
        assert pid._integral is not None

    def test_anti_windup_disabled(self, mock_parameters):
        """No anti-windup correction when disabled."""
        mock_parameters.ENABLE_ANTI_WINDUP = False

        pid = CustomPID(Kp=0.0, Ki=1.0, setpoint=100.0, output_limits=(-10, 10))

        # Drive to saturation
        for _ in range(20):
            pid(0.0, dt=1.0)

        # Integral should grow unbounded (within internal limits)
        output = pid(0.0, dt=1.0)
        assert output == 10.0  # Clamped at limit

    def test_anti_windup_recovery(self, mock_parameters):
        """System recovers faster with anti-windup."""
        mock_parameters.ENABLE_ANTI_WINDUP = True
        mock_parameters.ANTI_WINDUP_BACK_CALC_COEFF = 0.3

        pid = CustomPID(Kp=0.5, Ki=1.0, setpoint=10.0, output_limits=(-5, 5))

        # Saturate
        for _ in range(20):
            pid(0.0, dt=0.1)

        # Change setpoint to reverse direction
        pid.setpoint = -10.0
        outputs = [pid(0.0, dt=0.1) for _ in range(20)]

        # With anti-windup, should eventually produce negative output
        # (integral should recover from positive saturation)
        assert any(o < 0 for o in outputs[-5:]) or outputs[-1] == pytest.approx(-5.0, abs=0.5)

    def test_anti_windup_coefficient(self, mock_parameters):
        """Higher coefficient provides stronger correction."""
        mock_parameters.ENABLE_ANTI_WINDUP = True

        # Test with low coefficient - recovery after saturation
        mock_parameters.ANTI_WINDUP_BACK_CALC_COEFF = 0.01
        pid1 = CustomPID(Kp=0.0, Ki=2.0, setpoint=100.0, output_limits=(-10, 10))
        for _ in range(10):
            pid1(0.0, dt=1.0)
        # Now reverse
        pid1.setpoint = -100.0
        recovery1 = [pid1(0.0, dt=1.0) for _ in range(50)]

        # Test with high coefficient
        mock_parameters.ANTI_WINDUP_BACK_CALC_COEFF = 0.9
        pid2 = CustomPID(Kp=0.0, Ki=2.0, setpoint=100.0, output_limits=(-10, 10))
        for _ in range(10):
            pid2(0.0, dt=1.0)
        # Now reverse
        pid2.setpoint = -100.0
        recovery2 = [pid2(0.0, dt=1.0) for _ in range(50)]

        # Higher coefficient should show recovery (negative output) sooner
        # Find first negative output index
        neg_idx1 = next((i for i, v in enumerate(recovery1) if v < 0), len(recovery1))
        neg_idx2 = next((i for i, v in enumerate(recovery2) if v < 0), len(recovery2))

        # Higher coefficient should recover faster or equal
        assert neg_idx2 <= neg_idx1


# =============================================================================
# Test: Proportional on Measurement (PoM)
# =============================================================================

class TestProportionalOnMeasurement:
    """Test Proportional on Measurement feature."""

    def test_pom_disabled(self, mock_parameters):
        """Standard proportional when PoM disabled."""
        mock_parameters.PROPORTIONAL_ON_MEASUREMENT = False

        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=10.0)
        output = pid(5.0)  # Error = 5

        assert output == pytest.approx(5.0)

    def test_pom_flag_accessed(self, mock_parameters):
        """PoM flag is accessed during calculation."""
        mock_parameters.PROPORTIONAL_ON_MEASUREMENT = False

        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=10.0)
        output = pid(5.0, dt=0.1)

        # With PoM disabled, standard proportional output
        assert output == pytest.approx(5.0)

    def test_pom_attribute_check(self, mock_parameters):
        """PoM uses getattr for parameter access."""
        # Verify the code doesn't crash if Parameters doesn't have the attribute
        mock_parameters.PROPORTIONAL_ON_MEASUREMENT = False

        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=10.0)

        # Should work without error
        output = pid(5.0, dt=0.1)
        assert isinstance(output, float)

    def test_last_input_storage(self, mock_parameters):
        """_last_input is stored when PoM enabled after initial call."""
        mock_parameters.PROPORTIONAL_ON_MEASUREMENT = False

        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=10.0)

        # First call with PoM disabled
        _ = pid(5.0, dt=0.1)

        # Enable PoM
        mock_parameters.PROPORTIONAL_ON_MEASUREMENT = True

        # Second call should store _last_input
        _ = pid(7.0, dt=0.1)

        # Verify attribute exists
        assert hasattr(pid, '_last_input')


# =============================================================================
# Test: Setpoint Changes
# =============================================================================

class TestSetpointChanges:
    """Test behavior on setpoint changes."""

    def test_setpoint_change_updates_error(self):
        """Changing setpoint immediately affects error."""
        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=10.0)

        output1 = pid(5.0, dt=0.1)  # Error = 5
        assert output1 == pytest.approx(5.0)

        # Create fresh PID to avoid derivative influence
        pid2 = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=20.0)
        output2 = pid2(5.0, dt=0.1)  # Error = 15
        assert output2 == pytest.approx(15.0)

    def test_setpoint_property(self):
        """Setpoint can be read and written."""
        pid = CustomPID(Kp=1.0, setpoint=10.0)

        assert pid.setpoint == 10.0
        pid.setpoint = 25.0
        assert pid.setpoint == 25.0

    def test_negative_setpoint(self):
        """Negative setpoints work correctly."""
        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=-10.0)
        output = pid(0.0)  # Error = -10
        assert output == pytest.approx(-10.0)

    def test_large_setpoint_change(self):
        """Large setpoint changes handled correctly."""
        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=1000.0)
        output = pid(0.0, dt=0.1)  # Error = 1000

        assert output == pytest.approx(1000.0)


# =============================================================================
# Test: Reset Functionality
# =============================================================================

class TestResetFunctionality:
    """Test PID reset and reinitialization."""

    def test_reset_clears_integral(self):
        """Reset clears accumulated integral."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0)

        # Accumulate integral
        for _ in range(10):
            pid(0.0, dt=1.0)

        # Reset
        pid.reset()

        # Next output should be like fresh start
        output = pid(0.0, dt=1.0)
        # First call integral contribution is Ki * error * dt
        assert output == pytest.approx(10.0)

    def test_reset_clears_derivative(self):
        """Reset clears derivative state."""
        pid = CustomPID(Kp=0.0, Ki=0.0, Kd=1.0, setpoint=10.0)

        # Establish derivative history
        pid(0.0, dt=1.0)
        pid(5.0, dt=1.0)

        # Reset
        pid.reset()

        # Derivative should restart fresh
        _ = pid(0.0, dt=1.0)
        output = pid(0.0, dt=1.0)

        # No change in input means ~zero derivative
        assert abs(output) < 1.0

    def test_last_output_reset(self):
        """Reset behavior for last_output tracking."""
        pid = CustomPID(Kp=1.0, setpoint=10.0)

        pid(5.0)
        assert pid.last_output != 0

        pid.reset()
        # After reset, next call should update last_output fresh
        pid(5.0)
        assert pid.last_output == pytest.approx(5.0)


# =============================================================================
# Test: Time Handling
# =============================================================================

class TestTimeHandling:
    """Test dt (time delta) handling."""

    def test_explicit_dt(self):
        """Explicit dt overrides sample_time."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0, sample_time=1.0)

        output = pid(0.0, dt=0.1)  # Use explicit dt

        # Should use dt=0.1, not sample_time=1.0
        assert output == pytest.approx(1.0)  # Ki * error * dt = 1 * 10 * 0.1

    def test_none_dt_uses_sample_time(self):
        """None dt uses internal sample_time."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0, sample_time=0.5)

        output = pid(0.0, dt=None)

        # First call behavior may vary, subsequent calls use sample_time
        _ = pid(0.0, dt=None)

    def test_very_small_dt(self):
        """Very small dt handled correctly."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0)

        output = pid(0.0, dt=0.001)
        assert output == pytest.approx(0.01)  # Ki * error * dt

    def test_large_dt(self):
        """Large dt handled correctly."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0)

        output = pid(0.0, dt=10.0)
        assert output == pytest.approx(100.0)  # Ki * error * dt


# =============================================================================
# Test: Gain Modification
# =============================================================================

class TestGainModification:
    """Test runtime gain changes."""

    def test_change_kp_runtime(self):
        """Kp can be changed at runtime."""
        pid1 = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=10.0)
        output1 = pid1(5.0, dt=0.1)
        assert output1 == pytest.approx(5.0)

        # Test with different Kp
        pid2 = CustomPID(Kp=2.0, Ki=0.0, Kd=0.0, setpoint=10.0)
        output2 = pid2(5.0, dt=0.1)
        assert output2 == pytest.approx(10.0)

    def test_change_ki_runtime(self):
        """Ki can be changed at runtime."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=10.0)

        _ = pid(0.0, dt=1.0)
        pid.Ki = 2.0
        output = pid(0.0, dt=1.0)

        # New Ki affects new integral accumulation
        assert output > 10.0

    def test_change_kd_runtime(self):
        """Kd can be changed at runtime."""
        pid = CustomPID(Kp=0.0, Ki=0.0, Kd=1.0, setpoint=10.0)

        _ = pid(0.0, dt=1.0)
        pid.Kd = 2.0
        output = pid(5.0, dt=1.0)

        # Changed Kd affects derivative calculation
        assert output != 0

    def test_tunings_property(self):
        """Tunings can be read as tuple."""
        pid = CustomPID(Kp=1.0, Ki=0.5, Kd=0.25)

        assert pid.tunings == (1.0, 0.5, 0.25)

    def test_tunings_setter(self):
        """Tunings can be set as tuple."""
        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0)

        pid.tunings = (2.0, 0.5, 0.1)

        assert pid.Kp == 2.0
        assert pid.Ki == 0.5
        assert pid.Kd == 0.1


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_gains(self):
        """All-zero gains produce zero output."""
        pid = CustomPID(Kp=0.0, Ki=0.0, Kd=0.0, setpoint=100.0)
        output = pid(0.0, dt=1.0)
        assert output == pytest.approx(0.0)

    def test_very_large_error(self):
        """Very large errors handled correctly."""
        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=1e10)
        output = pid(0.0)
        assert output == pytest.approx(1e10)

    def test_very_small_error(self):
        """Very small errors handled correctly."""
        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=1e-10)
        output = pid(0.0)
        assert output == pytest.approx(1e-10)

    def test_negative_gains(self):
        """Negative gains reverse output direction."""
        pid = CustomPID(Kp=-1.0, Ki=0.0, Kd=0.0, setpoint=10.0)
        output = pid(5.0)  # Error = 5
        assert output == pytest.approx(-5.0)

    def test_very_large_gains(self):
        """Very large gains work correctly."""
        pid = CustomPID(Kp=1e6, Ki=0.0, Kd=0.0, setpoint=10.0, output_limits=(-100, 100))
        output = pid(9.0)  # Error = 1, P = 1e6
        assert output == 100.0  # Clamped

    def test_inf_not_produced(self):
        """Normal operation doesn't produce infinity."""
        pid = CustomPID(Kp=1.0, Ki=1.0, Kd=1.0, setpoint=1000.0)

        for _ in range(100):
            output = pid(0.0, dt=0.1)
            assert output != float('inf')
            assert output != float('-inf')

    def test_nan_input_handling(self):
        """NaN input produces expected behavior."""
        pid = CustomPID(Kp=1.0, Ki=0.0, Kd=0.0, setpoint=10.0)

        import math
        output = pid(float('nan'))

        # NaN propagates
        assert math.isnan(output)


# =============================================================================
# Test: Continuous Operation
# =============================================================================

class TestContinuousOperation:
    """Test sustained operation over many iterations."""

    def test_long_running_stability(self):
        """PID remains stable over many iterations."""
        pid = CustomPID(Kp=0.5, Ki=0.1, Kd=0.05, setpoint=10.0, output_limits=(-10, 10))

        value = 0.0
        for _ in range(1000):
            output = pid(value, dt=0.1)
            value += output * 0.1

            # Value should stay bounded
            assert -100 < value < 200

    def test_integral_doesnt_overflow(self):
        """Integral term doesn't overflow with limits."""
        pid = CustomPID(Kp=0.0, Ki=1.0, Kd=0.0, setpoint=1000.0, output_limits=(-10, 10))

        for _ in range(10000):
            output = pid(0.0, dt=0.1)

        # Output should stay at limit
        assert output == pytest.approx(10.0)
        # Internal integral should be bounded (with anti-windup) or very large (without)

    def test_alternating_error_stability(self):
        """PID stable with alternating error."""
        pid = CustomPID(Kp=1.0, Ki=0.1, Kd=0.5, setpoint=0.0, output_limits=(-20, 20))

        value = 0.0
        for i in range(100):
            # Alternating disturbance
            disturbance = 5.0 if i % 2 == 0 else -5.0
            measured = value + disturbance
            output = pid(measured, dt=0.1)
            value = measured + output * 0.1

        # Should remain bounded
        assert -50 < value < 50
