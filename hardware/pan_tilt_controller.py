"""
Camera pan/tilt gimbal controller.

Wraps a QuadrupedServoManager to provide high-level camera positioning,
scanning sweep, and angle clamping for the wildfire detection camera.
"""

from utils.config import CAMERA_CENTER_ANGLE, CAMERA_SCAN_ANGLES, TIME_SLEEP_SCAN, SERVO_ANGLE_MIN, SERVO_ANGLE_MAX
import time

class PanTiltController:
    """
    High-level controller for the camera pan/tilt gimbal.

    Delegates angle commands to a QuadrupedServoManager instance and adds
    angle clamping, preset positions (center), and automated scan sweeps.
    """

    def __init__(self, controller):
        """
        Args:
            controller: QuadrupedServoManager instance that drives the hardware servos.
        """
        self._controller = controller

    def pan(self, pan_angle):
        """
        Rotate the camera horizontally to pan_angle degrees.

        Args:
            pan_angle: Target pan angle in degrees; clamped to [SERVO_ANGLE_MIN, SERVO_ANGLE_MAX].
        """

        try:
            if pan_angle < SERVO_ANGLE_MIN:
                pan_angle = SERVO_ANGLE_MIN
            if pan_angle > SERVO_ANGLE_MAX:
                pan_angle = SERVO_ANGLE_MAX
            self._controller.set_pan_angle(pan_angle)
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Pan control failed: {e}")

    def tilt(self, angle):
        """
        Rotate the camera vertically to the given angle.

        Args:
            angle: Target tilt angle in degrees; clamped to [SERVO_ANGLE_MIN, SERVO_ANGLE_MAX].
        """

        try:
            if angle < SERVO_ANGLE_MIN:
                angle = SERVO_ANGLE_MIN
            if angle > SERVO_ANGLE_MAX:
                angle = SERVO_ANGLE_MAX
            self._controller.set_tilt_angle(angle)
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Tilt control failed: {e}")

    def center(self):
        """Move the camera to the forward-facing centre position (CAMERA_CENTER_ANGLE)."""

        self._controller.set_pan_angle(CAMERA_CENTER_ANGLE)
        self._controller.set_tilt_angle(CAMERA_CENTER_ANGLE)

    def scan(self):
        """
        Perform a left-right pan sweep for environmental scanning.

        Sequence: left scan angle → centre → right scan angle → centre → centre.
        Pauses at each position using TIME_SLEEP_SCAN durations to allow
        the camera to capture stable frames.
        """

        self._controller.set_pan_angle(CAMERA_SCAN_ANGLES[0])
        time.sleep(TIME_SLEEP_SCAN[0])

        self._controller.set_pan_angle(CAMERA_CENTER_ANGLE)
        time.sleep(TIME_SLEEP_SCAN[1])

        self._controller.set_pan_angle(CAMERA_SCAN_ANGLES[1])
        time.sleep(TIME_SLEEP_SCAN[0])

        self._controller.set_pan_angle(CAMERA_CENTER_ANGLE)
        time.sleep(TIME_SLEEP_SCAN[1])

        self.center()

    def rotate_to_angle(self, pan_angle, tilt_angle):
        """
        Move the camera to a specific pan and tilt position simultaneously.

        Args:
            pan_angle: Horizontal target angle in degrees.
            tilt_angle: Vertical target angle in degrees; clamped to [SERVO_ANGLE_MIN, SERVO_ANGLE_MAX].
        """

        try:
            if tilt_angle < SERVO_ANGLE_MIN:
                tilt_angle = SERVO_ANGLE_MIN
            if tilt_angle > SERVO_ANGLE_MAX:
                tilt_angle = SERVO_ANGLE_MAX

            self.pan(pan_angle)
            self.tilt(tilt_angle)
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Rotate to angle failed: {e}")

    def reset(self):
        """Reset the camera to the centre position."""

        self.center()