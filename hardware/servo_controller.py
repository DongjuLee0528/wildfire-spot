from utils.config import *

import Kinematics.kinematics as kn
import numpy as np

from adafruit_pca9685 import PCA9685
from adafruit_motor import servo
import board
import busio
import time

class Controllers:
    def __init__(self):
        print("Initializing Servos")
        self._i2c_bus0=(busio.I2C(I2C_SCL, I2C_SDA))
        print("Initializing ServoKit")
        self._pca_1 = PCA9685(self._i2c_bus0, address=PCA9685_FRONT_LEGS)
        self._pca_1.frequency = PWM_FREQUENCY
        self._pca_2 = PCA9685(self._i2c_bus0, address=PCA9685_BACK_LEGS)
        self._pca_2.frequency = PWM_FREQUENCY
        self._pca_3 = PCA9685(self._i2c_bus0, address=PCA9685_CAMERA)
        self._pca_3.frequency = PWM_FREQUENCY

        self._servos = list()
        for i in range(0, 12):
            if i<6:
                self._servos.append(servo.Servo(self._pca_1.channels[i], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE))
            else:
                self._servos.append(servo.Servo(self._pca_2.channels[i], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE))

        self._pan_servo = servo.Servo(self._pca_3.channels[CAMERA_PAN], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE)
        self._tilt_servo = servo.Servo(self._pca_3.channels[CAMERA_TILT], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE)

        print("Done initializing")

        self._servo_offsets = SERVO_OFFSETS

        self._val_list = [ x for x in range(12) ]
        self._thetas = []

    def getDegreeAngles(self, La):
        La *= 180/np.pi
        La = [ [ int(x) for x in y ] for y in La ]
        self._thetas = La

    def angleToServo(self, La):
        self.getDegreeAngles(La)
        self._val_list[0] = self._servo_offsets[0] - self._thetas[0][2]
        self._val_list[1] = self._servo_offsets[1] - self._thetas[0][1]
        self._val_list[2] = self._servo_offsets[2] + self._thetas[0][0]
        self._val_list[3] = self._servo_offsets[3] + self._thetas[1][2]
        self._val_list[4] = self._servo_offsets[4] + self._thetas[1][1]
        self._val_list[5] = self._servo_offsets[5] - self._thetas[1][0]
        self._val_list[6] = self._servo_offsets[6] - self._thetas[2][2]
        self._val_list[7] = self._servo_offsets[7] - self._thetas[2][1]
        self._val_list[8] = self._servo_offsets[8] - self._thetas[2][0]
        self._val_list[9] = self._servo_offsets[9] + self._thetas[3][2]
        self._val_list[10] = self._servo_offsets[10] + self._thetas[3][1]
        self._val_list[11] = self._servo_offsets[11] + self._thetas[3][0]     

    def getServoAngles(self):
        return self._val_list

    def servoRotate(self, thetas):
        self.angleToServo(thetas)

        for x in range(len(self._val_list)):
            if (self._val_list[x] > SERVO_ANGLE_MAX):
                print("Over 180!!")
                self._val_list[x] = SERVO_ANGLE_MAX - 1
            if (self._val_list[x] <= SERVO_ANGLE_MIN):
                print("Under 0!!")
                self._val_list[x] = SERVO_ANGLE_MIN + 1
            self._servos[x].angle = float(self._val_list[x])

    def set_camera_pan(self, angle):
        if angle < SERVO_ANGLE_MIN:
            angle = SERVO_ANGLE_MIN
        if angle > SERVO_ANGLE_MAX:
            angle = SERVO_ANGLE_MAX
        self._pan_servo.angle = float(angle)

    def set_camera_tilt(self, angle):
        if angle < SERVO_ANGLE_MIN:
            angle = SERVO_ANGLE_MIN
        if angle > SERVO_ANGLE_MAX:
            angle = SERVO_ANGLE_MAX
        self._tilt_servo.angle = float(angle)

if __name__=="__main__":
    legEndpoints=np.array([[100,-100,87.5,1],[100,-100,-87.5,1],[-100,-100,87.5,1],[-100,-100,-87.5,1]])
    thetas = kn.initIK(legEndpoints)
    controller = Controllers()
    controller.servoRotate(thetas)
    svAngle = controller.getServoAngles()
    print(svAngle)
    kn.plotKinematics()
