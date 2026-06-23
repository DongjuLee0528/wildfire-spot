from utils.config import (I2C_SCL, I2C_SDA, PCA9685_FRONT_LEGS, PCA9685_BACK_LEGS, PCA9685_CAMERA,
                         PWM_FREQUENCY, PWM_MIN_PULSE, PWM_MAX_PULSE, SERVO_CHANNELS,
                         FRONT_LEG_CHANNELS, CAMERA_PAN, CAMERA_TILT, SERVO_OFFSETS,
                         SERVO_ANGLE_MIN, SERVO_ANGLE_MAX, SERVO_TEST_ENDPOINT_VALUES,
                         SERVO_MAX_ANGLE, SERVO_MIN_ANGLE, SERVO_ANGLE_ADJUSTMENT)

import numpy as np

def _load_servo_hardware():
    try:
        from adafruit_pca9685 import PCA9685
        from adafruit_motor import servo
        import busio
    except ImportError as exc:
        raise RuntimeError("Servo hardware dependencies are not available") from exc
    return PCA9685, servo, busio

class QuadrupedServoManager:

    def __init__(self):
        self._i2c_interface = None
        self._front_driver = None
        self._rear_driver = None
        self._camera_driver = None
        try:
            PCA9685, servo, busio = _load_servo_hardware()
            print("Initializing servo hardware")
            self._i2c_interface = busio.I2C(I2C_SCL, I2C_SDA)
            print("Setting up servo drivers")

            self._front_driver = PCA9685(self._i2c_interface, address=PCA9685_FRONT_LEGS)
            self._front_driver.frequency = PWM_FREQUENCY
            self._rear_driver = PCA9685(self._i2c_interface, address=PCA9685_BACK_LEGS)
            self._rear_driver.frequency = PWM_FREQUENCY
            self._camera_driver = PCA9685(self._i2c_interface, address=PCA9685_CAMERA)
            self._camera_driver.frequency = PWM_FREQUENCY
        except (ValueError, RuntimeError, OSError) as e:
            print(f"Servo driver initialization failed: {type(e).__name__}: {e}")
            self.shutdown_servos()
            raise

        self._servo_array = list()
        for servo_index in range(0, SERVO_CHANNELS):
            if servo_index < FRONT_LEG_CHANNELS:
                self._servo_array.append(servo.Servo(self._front_driver.channels[servo_index], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE))
            else:
                self._servo_array.append(servo.Servo(self._rear_driver.channels[servo_index-FRONT_LEG_CHANNELS], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE))

        self._pan_motor = servo.Servo(self._camera_driver.channels[CAMERA_PAN], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE)
        self._tilt_motor = servo.Servo(self._camera_driver.channels[CAMERA_TILT], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE)

        print("Servo initialization complete")

        self._offset_values = SERVO_OFFSETS

        self._angle_array = [servo_index for servo_index in range(SERVO_CHANNELS)]
        self._joint_angles = []

    def convert_to_degrees(self, angle_radians):
        angle_degrees = angle_radians * 180/np.pi
        angle_degrees_int = [[int(value) for value in row] for row in angle_degrees]
        self._joint_angles = angle_degrees_int

    def process_angle_mapping(self, angle_radians):
        self.convert_to_degrees(angle_radians)

        if len(self._joint_angles) < 4 or any(len(leg) < 3 for leg in self._joint_angles):
            print("Invalid joint angles array size")
            return

        self._angle_array[0] = self._offset_values[0] - self._joint_angles[0][2]
        self._angle_array[1] = self._offset_values[1] - self._joint_angles[0][1]
        self._angle_array[2] = self._offset_values[2] + self._joint_angles[0][0]

        self._angle_array[3] = self._offset_values[3] + self._joint_angles[1][2]
        self._angle_array[4] = self._offset_values[4] + self._joint_angles[1][1]
        self._angle_array[5] = self._offset_values[5] - self._joint_angles[1][0]

        self._angle_array[6] = self._offset_values[6] - self._joint_angles[2][2]
        self._angle_array[7] = self._offset_values[7] - self._joint_angles[2][1]
        self._angle_array[8] = self._offset_values[8] - self._joint_angles[2][0]

        self._angle_array[9] = self._offset_values[9] + self._joint_angles[3][2]
        self._angle_array[10] = self._offset_values[10] + self._joint_angles[3][1]
        self._angle_array[11] = self._offset_values[11] + self._joint_angles[3][0]

    def get_current_angles(self):
        return self._angle_array

    def execute_servo_motion(self, joint_angles):
        self.process_angle_mapping(joint_angles)

        for servo_index in range(len(self._angle_array)):
            if (self._angle_array[servo_index] > SERVO_MAX_ANGLE):
                print("Angle exceeds maximum limit")
                self._angle_array[servo_index] = SERVO_MAX_ANGLE - SERVO_ANGLE_ADJUSTMENT
            if (self._angle_array[servo_index] <= SERVO_MIN_ANGLE):
                print("Angle below minimum limit")
                self._angle_array[servo_index] = SERVO_MIN_ANGLE + SERVO_ANGLE_ADJUSTMENT
            self._servo_array[servo_index].angle = float(self._angle_array[servo_index])

    def set_pan_angle(self, target_angle):
        if target_angle < SERVO_ANGLE_MIN:
            target_angle = SERVO_ANGLE_MIN
        if target_angle > SERVO_ANGLE_MAX:
            target_angle = SERVO_ANGLE_MAX
        self._pan_motor.angle = float(target_angle)

    def set_tilt_angle(self, target_angle):
        if target_angle < SERVO_ANGLE_MIN:
            target_angle = SERVO_ANGLE_MIN
        if target_angle > SERVO_ANGLE_MAX:
            target_angle = SERVO_ANGLE_MAX
        self._tilt_motor.angle = float(target_angle)

    def shutdown_servos(self):
        try:
            if self._front_driver is not None:
                self._front_driver.deinit()
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Front servo driver shutdown failed: {type(e).__name__}: {e}")
        try:
            if self._rear_driver is not None:
                self._rear_driver.deinit()
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Rear servo driver shutdown failed: {type(e).__name__}: {e}")
        try:
            if self._camera_driver is not None:
                self._camera_driver.deinit()
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Camera servo driver shutdown failed: {type(e).__name__}: {e}")
        try:
            if self._i2c_interface is not None:
                self._i2c_interface.deinit()
        except (ValueError, RuntimeError, AttributeError) as e:
            print(f"Servo I2C shutdown failed: {type(e).__name__}: {e}")

if __name__=="__main__":
    import Kinematics.kinematics as kn

    test_endpoints = np.array(SERVO_TEST_ENDPOINT_VALUES)
    kinematics_solver = kn.DHParameterSolver()
    calculated_angles = kinematics_solver.init_ik(test_endpoints)
    servo_manager = QuadrupedServoManager()
    servo_manager.execute_servo_motion(calculated_angles)
    current_angles = servo_manager.get_current_angles()
    print(current_angles)
    servo_manager.shutdown_servos()
    kinematics_solver.plot()
