from utils.config import CAMERA_CENTER_ANGLE, CAMERA_SCAN_ANGLES, TIME_SLEEP_SCAN, SERVO_ANGLE_MIN, SERVO_ANGLE_MAX
import time

class PanTiltController:

    def __init__(self, controller):
        self._controller = controller

    def pan(self, pan_angle):
        try:
            if pan_angle < SERVO_ANGLE_MIN:
                pan_angle = SERVO_ANGLE_MIN
            if pan_angle > SERVO_ANGLE_MAX:
                pan_angle = SERVO_ANGLE_MAX
            self._controller.set_pan_angle(pan_angle)
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Pan control failed: {e}")

    def tilt(self, angle):
        try:
            if angle < SERVO_ANGLE_MIN:
                angle = SERVO_ANGLE_MIN
            if angle > SERVO_ANGLE_MAX:
                angle = SERVO_ANGLE_MAX
            self._controller.set_tilt_angle(angle)
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Tilt control failed: {e}")

    def center(self):
        self._controller.set_pan_angle(CAMERA_CENTER_ANGLE)
        self._controller.set_tilt_angle(CAMERA_CENTER_ANGLE)

    def scan(self):
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
        self.center()