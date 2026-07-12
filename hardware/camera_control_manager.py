"""
Camera pan/tilt control manager for the Wildfire Spot robot.

Drives two servos on the front PCA9685 board (address PCA9685_FRONT_LEGS):
- Channel CAMERA_PAN_CHANNEL  (6): 360-degree continuous servo — throttle-controlled
- Channel CAMERA_TILT_CHANNEL (7): 180-degree positional servo — angle-controlled

The front PCA9685 board is shared with QuadrupedServoManager (CH0-CH5 are leg
servos). To avoid double-deinit of the shared board, callers may inject the
already-initialised PCA9685 driver via the `front_driver` parameter.

Ownership rules:
- If `front_driver` is provided by the caller → CameraControlManager does NOT
  own it and will NOT call deinit() on it in close().
- If `front_driver` is None → CameraControlManager creates its own driver and
  owns it; close() will deinit it.
"""

from utils.config import (
    I2C_SCL, I2C_SDA, PCA9685_FRONT_LEGS,
    PWM_FREQUENCY, PWM_MIN_PULSE, PWM_MAX_PULSE,
    CAMERA_PAN_CHANNEL, CAMERA_TILT_CHANNEL,
    CAMERA_PAN_STOP_THROTTLE, CAMERA_PAN_LEFT_THROTTLE, CAMERA_PAN_RIGHT_THROTTLE,
    CAMERA_TILT_INITIAL_ANGLE, CAMERA_TILT_MIN_ANGLE, CAMERA_TILT_MAX_ANGLE,
    CAMERA_TILT_STEP_ANGLE,
)


class CameraControlManager:
    """
    Controls the camera pan/tilt gimbal on the Wildfire Spot robot.

    Pan uses a 360-degree continuous servo driven by throttle values.
    Tilt uses a 180-degree positional servo driven by absolute angle.

    Both servos reside on the front PCA9685 board (PCA9685_FRONT_LEGS)
    at channels CAMERA_PAN_CHANNEL and CAMERA_TILT_CHANNEL respectively.

    Construction never raises — hardware unavailability is handled gracefully.
    Use is_available() to check readiness before issuing commands.
    """

    def __init__(self, front_driver=None):
        """
        Initialise the camera servo channels.

        Args:
            front_driver: Optional externally-owned PCA9685 driver for the front
                board. If provided, this manager will NOT deinit it on close().
                If None, an independent driver is created and owned by this manager.

        Never raises. On any hardware or library failure the manager enters an
        unavailable state; is_available() will return False.
        """
        self._i2c_interface = None   # Only set when this manager owns the I2C bus
        self._front_driver = None      # PCA9685 driver for the front board
        self._owns_driver = False      # True only when this manager created the driver
        self._pan_motor = None         # ContinuousServo on CAMERA_PAN_CHANNEL
        self._tilt_motor = None        # Servo on CAMERA_TILT_CHANNEL
        self._tilt_angle = float(CAMERA_TILT_INITIAL_ANGLE)  # Last commanded tilt angle
        self._pan_state = "stopped"    # Human-readable pan direction: 'left'/'right'/'stopped'

        try:
            from adafruit_motor import servo as servo_module

            if front_driver is not None:
                # Reuse the already-open PCA9685 driver from QuadrupedServoManager
                self._front_driver = front_driver
                self._owns_driver = False
            else:
                # No shared driver — create an independent I2C + PCA9685 pair
                from adafruit_pca9685 import PCA9685
                import busio
                self._i2c_interface = busio.I2C(I2C_SCL, I2C_SDA)
                self._front_driver = PCA9685(self._i2c_interface, address=PCA9685_FRONT_LEGS)
                self._front_driver.frequency = PWM_FREQUENCY
                self._owns_driver = True

            # CH6 = 360° continuous servo (pan); CH7 = 180° positional servo (tilt)
            self._pan_motor = servo_module.ContinuousServo(
                self._front_driver.channels[CAMERA_PAN_CHANNEL],
                min_pulse=PWM_MIN_PULSE,
                max_pulse=PWM_MAX_PULSE,
            )
            self._tilt_motor = servo_module.Servo(
                self._front_driver.channels[CAMERA_TILT_CHANNEL],
                min_pulse=PWM_MIN_PULSE,
                max_pulse=PWM_MAX_PULSE,
            )
            # Initialise both motors to a safe resting position
            self._pan_motor.throttle = CAMERA_PAN_STOP_THROTTLE
            self._tilt_motor.angle = self._tilt_angle
        except Exception as e:
            print(f"Camera hardware initialization failed: {type(e).__name__}: {e}")
            self._pan_motor = None
            self._tilt_motor = None
            if self._owns_driver:
                self._safe_deinit_owned()

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
        except Exception as e:
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
        """
        Stop pan and release owned resources.

        - Always attempts to stop pan throttle before releasing.
        - Deinits the PCA9685 driver only if this manager owns it
          (_owns_driver=True). Externally-provided drivers are never deinited.
        - Idempotent: safe to call multiple times.
        """
        if self._pan_motor is not None:
            try:
                self._pan_motor.throttle = CAMERA_PAN_STOP_THROTTLE
            except Exception as e:
                print(f"Camera pan stop on close failed: {type(e).__name__}: {e}")
        self._pan_motor = None
        self._tilt_motor = None

        if self._owns_driver:
            self._safe_deinit_owned()

    def _safe_deinit_owned(self):
        """Deinit driver and I2C resources that this manager owns."""
        try:
            if self._front_driver is not None:
                self._front_driver.deinit()
        except Exception as e:
            print(f"Camera driver shutdown failed: {type(e).__name__}: {e}")
        finally:
            self._front_driver = None
        try:
            if self._i2c_interface is not None:
                self._i2c_interface.deinit()
        except Exception as e:
            print(f"Camera I2C shutdown failed: {type(e).__name__}: {e}")
        finally:
            self._i2c_interface = None

    def _set_pan(self, throttle, state_label, command):
        """
        Apply a throttle value to the continuous pan servo.

        Args:
            throttle: Float in [-1.0, 1.0] where 0.0 = stop.
            state_label: Human-readable direction string stored in _pan_state.
            command: API command name included in the response dict.
        """
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
        except Exception as e:
            print(f"{command} failed: {type(e).__name__}: {e}")
            return {"accepted": False, "command": command, "reason": str(e), "position": self._position()}

    def _set_tilt(self, new_angle, command):
        """
        Move the tilt servo to a new absolute angle.

        Args:
            new_angle: Target angle in degrees, clamped by camera_up/camera_down
                       to [CAMERA_TILT_MIN_ANGLE, CAMERA_TILT_MAX_ANGLE].
            command: API command name included in the response dict.
        """
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
        except Exception as e:
            print(f"{command} failed: {type(e).__name__}: {e}")
            return {"accepted": False, "command": command, "reason": str(e), "position": self._position()}

    def _position(self):
        """Return the current pan state string and tilt angle as a dict."""
        return {"pan": self._pan_state, "tilt": self._tilt_angle}

    def _unavailable_response(self, command):
        """Return a standardised rejection dict when hardware is not initialised."""
        return {
            "accepted": False,
            "command": command,
            "reason": "camera hardware unavailable",
            "position": self._position(),
        }
