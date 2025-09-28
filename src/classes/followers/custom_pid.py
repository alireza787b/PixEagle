from simple_pid import PID
from classes.parameters import Parameters  # Ensure Parameters class is imported or accessible

class CustomPID(PID):
    """
    Custom PID controller that integrates standard PID functionalities with advanced features:
    - Proportional on Measurement (PoM): Enhances stability by applying proportional control based on the current measurement.
    - Anti-windup using back-calculation: Prevents integral windup by adjusting the integral term when output is at saturation limits.

    Attributes:
        last_output (float): Stores the last output value to assist in anti-windup calculations.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_output = 0  # Initialize last output for anti-windup calculation

    def __call__(self, input_, dt=None):
        # Apply Proportional on Measurement if enabled
        if getattr(Parameters, 'PROPORTIONAL_ON_MEASUREMENT', False):
            # Store original setpoint and temporarily modify it
            original_setpoint = self.setpoint
            # For PoM, we want proportional term to be based on measurement change
            # This prevents derivative kick on setpoint changes
            if hasattr(self, '_last_input'):
                # Calculate proportional term based on input change instead of error
                self.setpoint = self._last_input
            self._last_input = input_

            output = super().__call__(input_, dt)

            # Restore original setpoint
            self.setpoint = original_setpoint
        else:
            output = super().__call__(input_, dt)

        # Apply anti-windup correction if enabled
        if getattr(Parameters, 'ENABLE_ANTI_WINDUP', False):
            if (output != self.last_output and
                self.output_limits and
                (output >= self.output_limits[1] or output <= self.output_limits[0])):
                # Back-calculate to adjust the integral term
                diff = output - self.last_output
                back_calc_coeff = getattr(Parameters, 'ANTI_WINDUP_BACK_CALC_COEFF', 0.1)
                self._integral -= diff * back_calc_coeff

        self.last_output = output  # Update last output
        return output
