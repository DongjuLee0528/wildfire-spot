"""
Camera pan/tilt control manager for the Wildfire Spot robot.

Drives two servos on the front PCA9685 board (address PCA9685_FRONT_LEGS):
- Channel CAMERA_PAN_CHANNEL  (6): 360-degree continuous servo — throttle-controlled
- Channel CAMERA_TILT_CHANNEL (7): 180-degree positional servo — angle-controlled
"""

from utils.config import (
    I2C_SCL, I2C_SDA, PCA9685_FRONT_LEGS,
    PWM_FREQUENCY, PWM_MIN_PULSE, PWM_MAX_PULSE,
    CAMERA_PAN_CHANNEL, CAMERA_TILT_CHANNEL,
    CAMERA_PAN_STOP_THROTTLE, CAMERA_PAN_LEFT_THROTTLE, CAMERA_PAN_RIGHT_THROTTLE,
    CAMERA_TILT_INITIAL_ANGLE, CAMERA_TILT_MIN_ANGLE, CAMERA_TILT_MAX_ANGLE,
    CAMERA_TILT_STEP_ANGLE,
)


def _load_camera_hardware():
    """Import and return PCA9685, servo, and busio modules; raises RuntimeError if unavailable."""
    try:
        from adafruit_pca9685 import PCA9685
        from adafruit_motor import servo
        import busio
    except ImportError as exc:
        raise RuntimeError("Camera hardware dependencies are not available") from exc
    return PCA9685, servo, busio


class CameraControlManager:
    """
    Controls the camera pan/tilt gimbal on the Wildfire Spot robot.

    Pan uses a 360-degree continuous servo driven by throttle values.
    Tilt uses a 180-degree positional servo driven by absolute angle.

    Both servos reside on the front PCA9685 board (PCA9685_FRONT_LEGS)
    at channels CAMERA_PAN_CHANNEL and CAMERA_TILT_CHANNEL respectively.
    """

    def __init__(self):
        """
        Open an I2C connection to the front PCA9685 board and initialise
        the pan and tilt servo channels.

        Raises RuntimeError if hardware dependencies or the I2C bus are
        unavailable.
        """
        self._i2c_interface = None
        self._front_driver = None
        self._pan_motor = None
        self._tilt_motor = None
        self._tilt_angle = float(CAMERA_TILT_INITIAL_ANGLE)
        self._pan_state = "stopped"

        try:
            PCA9685, servo, busio = _load_camera_hardware()
            self._i2c_interface = busio.I2C(I2C_SCL, I2C_SDA)
            self._front_driver = PCA9685(self._i2c_interface, address=PCA9685_FRONT_LEGS)
            self._front_driver.frequency = PWM_FREQUENCY
            self._pan_motor = servo.ContinuousServo(
                self._front_driver.channels[CAMERA_PAN_CHANNEL],
                min_pulse=PWM_MIN_PULSE,
                max_pulse=PWM_MAX_PULSE,
            )
            self._tilt_motor = servo.Servo(
                self._front_driver.channels[CAMERA_TILT_CHANNEL],
                min_pulse=PWM_MIN_PULSE,
                max_pulse=PWM_MAX_PULSE,
            )
            self._pan_motor.throttle = CAMERA_PAN_STOP_THROTTLE
            self._tilt_motor.angle = self._tilt_angle
        except (ValueError, RuntimeError, OSError) as e:
            print(f"Camera hardware initialization failed: {type(e).__name__}: {e}")
            self.close()
            raise

    def is_available(self):
        """Return True if the camera hardware is initialised and ready."""
        return self._pan_motor is not None and self._tilt_motor is not None

    def camera_left(self):
        """Start panning the camera to the left."""
        return self._set_pan(CAMERA_PAN_LEFT_THROTTLE, "left", "CAMERA_LEFT")

    def camera_right(self):
        """Start panning the camera to the right."""
        return self._set_pan(CAMERA_PAN_RIGHT_THROTTLE, "right", "CAMERA_RIGHT")

    def camera_pan_stop(self):
        """Stop camera panning."""
        return self._set_pan(CAMERA_PAN_STOP_THROTTLE, "stopped", "CAMERA_PAN_STOP")

    def camera_up(self):
        """Tilt the camera up by one step."""
        new_angle = min(self._tilt_angle + CAMERA_TILT_STEP_ANGLE, CAMERA_TILT_MAX_ANGLE)
        return self._set_tilt(new_angle, "CAMERA_UP")

    def camera_down(self):
        """Tilt the camera down by one step."""
        new_angle = max(self._tilt_angle - CAMERA_TILT_STEP_ANGLE, CAMERA_TILT_MIN_ANGLE)
        return self._set_tilt(new_angle, "CAMERA_DOWN")

    def camera_center(self):
        """Stop panning and return tilt to the initial centre angle."""
        if not self.is_available():
            return self._unavailable_response("CAMERA_CENTER")
        try:
            self._pan_motor.throttle = CAMERA_PAN_STOP_THROTTLE
            self._pan_state = "stopped"
            self._tilt_motor.angle = float(CAMERA_TILT_INITIAL_ANGLE)
            self._tilt_angle = float(CAMERA_TILT_INITIAL_ANGLE)
            return {
                "accepted": True,
                "command": "CAMERA_CENTER",
                "reason": "ok",
                "position": self._position(),
            }
        except (ValueError, RuntimeError, OSError) as e:
            print(f"camera_center failed: {type(e).__name__}: {e}")
            return {"accepted": False, "command": "CAMERA_CENTER", "reason": str(e), "position": self._position()}

    def get_camera_position(self):
        """Return the current camera position without issuing any movement."""
        return {
            "accepted": True,
            "command": "GET_POSITION",
            "reason": "ok",
            "position": self._position(),
        }

    def close(self):
        """Deinitialise the PCA9685 driver and release the I2C bus."""
        try:
            if self._front_driver is not None:
                self._front_driver.deinit()
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Camera driver shutdown failed: {type(e).__name__}: {e}")
        try:
            if self._i2c_interface is not None:
                self._i2c_interface.deinit()
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Camera I2C shutdown failed: {type(e).__name__}: {e}")

    def _set_pan(self, throttle, state_label, command):
        if not self.is_available():
            return self._unavailable_response(command)
        try:
            self._pan_motor.throttle = throttle
            self._pan_state = state_label
            return {
                "accepted": True,
                "command": command,
                "reason": "ok",
                "position": self._position(),
            }
        except (ValueError, RuntimeError, OSError) as e:
            print(f"{command} failed: {type(e).__name__}: {e}")
            return {"accepted": False, "command": command, "reason": str(e), "position": self._position()}

    def _set_tilt(self, new_angle, command):
        if not self.is_available():
            return self._unavailable_response(command)
        try:
            self._tilt_motor.angle = float(new_angle)
            self._tilt_angle = float(new_angle)
            return {
                "accepted": True,
                "command": command,
                "reason": "ok",
                "position": self._position(),
            }
        except (ValueError, RuntimeError, OSError) as e:
            print(f"{command} failed: {type(e).__name__}: {e}")
            return {"accepted": False, "command": command, "reason": str(e), "position": self._position()}

    def _position(self):
        return {"pan": self._pan_state, "tilt": self._tilt_angle}

    def _unavailable_response(self, command):
        return {
            "accepted": False,
            "command": command,
            "reason": "camera hardware unavailable",
            "position": self._position(),
        }
