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
        if Parameters.PROPORTIONAL_ON_MEASUREMENT:
            # Adjust the proportional error calculation to be based on the measurement
            self.proportional = self.Kp * (self.setpoint - input_)
        
        output = super().__call__(input_, dt)

        # Apply anti-windup correction if enabled
        if Parameters.ENABLE_ANTI_WINDUP:
            if output != self.last_output and (output >= self.output_limits[1] or output <= self.output_limits[0]):
                # Back-calculate to adjust the integral term
                diff = output - self.last_output
                self._integral -= diff * Parameters.ANTI_WINDUP_BACK_CALC_COEFF

        self.last_output = output  # Update last output
        return output
