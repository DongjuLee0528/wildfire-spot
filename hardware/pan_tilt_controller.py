from utils.config import CAMERA_CENTER_ANGLE, CAMERA_SCAN_ANGLES, TIME_SLEEP_SCAN, SERVO_ANGLE_MIN, SERVO_ANGLE_MAX
from hardware.servo_controller import Controllers
import time

class PanTiltController:

    def __init__(self, controller):
        self._controller = controller

    def pan(self, speed):
        try:
            if speed < SERVO_ANGLE_MIN:
                speed = SERVO_ANGLE_MIN
            if speed > SERVO_ANGLE_MAX:
                speed = SERVO_ANGLE_MAX
            self._controller.set_camera_pan(speed)
        except Exception as e:
            print(f"Pan control failed: {e}")

    def tilt(self, angle):
        try:
            if angle < SERVO_ANGLE_MIN:
                angle = SERVO_ANGLE_MIN
            if angle > SERVO_ANGLE_MAX:
                angle = SERVO_ANGLE_MAX
            self._controller.set_camera_tilt(angle)
        except Exception as e:
            print(f"Tilt control failed: {e}")

    def center(self):
        self._controller.set_camera_pan(CAMERA_CENTER_ANGLE)
        self._controller.set_camera_tilt(CAMERA_CENTER_ANGLE)

    def scan(self):
        self._controller.set_camera_pan(CAMERA_SCAN_ANGLES[0])
        time.sleep(TIME_SLEEP_SCAN[0])

        self._controller.set_camera_pan(CAMERA_CENTER_ANGLE)
        time.sleep(TIME_SLEEP_SCAN[1])

        self._controller.set_camera_pan(CAMERA_SCAN_ANGLES[1])
        time.sleep(TIME_SLEEP_SCAN[0])

        self._controller.set_camera_pan(CAMERA_CENTER_ANGLE)
        time.sleep(TIME_SLEEP_SCAN[1])

        self.center()

    def rotate_to_angle(self, pan_speed, tilt_angle):
        try:
            if tilt_angle < SERVO_ANGLE_MIN:
                tilt_angle = SERVO_ANGLE_MIN
            if tilt_angle > SERVO_ANGLE_MAX:
                tilt_angle = SERVO_ANGLE_MAX

            self.pan(pan_speed)
            self.tilt(tilt_angle)
        except Exception as e:
            print(f"Rotate to angle failed: {e}")

    def reset(self):
        self.center()