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
        self._constructor_proportional_on_measurement = self.proportional_on_measurement

    def reset(self):
        """Clear both the base controller and subclass anti-windup history."""
        super().reset()
        self.last_output = 0.0

    def __call__(self, input_, dt=None):
        self.proportional_on_measurement = (
            self._constructor_proportional_on_measurement
            or getattr(Parameters, 'PROPORTIONAL_ON_MEASUREMENT', False)
        )
        output = super().__call__(input_, dt)
        if output is None:
            return None

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
