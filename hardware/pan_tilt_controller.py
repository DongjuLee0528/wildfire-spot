from utils.config import *
from hardware.servo_controller import Controllers
import time

class PanTiltController:
    def __init__(self, controller):
        self._controller = controller

    def pan(self, speed):
        if speed < SERVO_ANGLE_MIN:
            speed = SERVO_ANGLE_MIN
        if speed > SERVO_ANGLE_MAX:
            speed = SERVO_ANGLE_MAX
        self._controller.set_camera_pan(speed)

    def tilt(self, angle):
        if angle < SERVO_ANGLE_MIN:
            angle = SERVO_ANGLE_MIN
        if angle > SERVO_ANGLE_MAX:
            angle = SERVO_ANGLE_MAX
        self._controller.set_camera_tilt(angle)

    def center(self):
        self._controller.set_camera_pan(90.0)
        self._controller.set_camera_tilt(90.0)

    def scan(self):
        self._controller.set_camera_pan(45.0)
        time.sleep(2)
        self._controller.set_camera_pan(90.0)
        time.sleep(1)
        self._controller.set_camera_pan(135.0)
        time.sleep(2)
        self._controller.set_camera_pan(90.0)
        time.sleep(1)
        self.center()

    def reset(self):
        self.center()