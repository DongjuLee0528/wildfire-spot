"""
Servo controller for the Wildfire Spot quadruped robot.

Manages two PCA9685 PWM driver boards via I2C:
- Front leg servos  (channels 0-5,  address PCA9685_FRONT_LEGS)
- Rear leg servos   (channels 0-5,  address PCA9685_BACK_LEGS)

Camera pan/tilt (front board channels 6-7) is managed separately
by CameraControlManager.

Accepts joint angles in radians from the kinematics solver, converts them
to per-servo degree commands with per-channel offset correction, and writes
the values to the hardware.
"""

from utils.config import (I2C_SCL, I2C_SDA, PCA9685_FRONT_LEGS, PCA9685_BACK_LEGS,
                         PWM_FREQUENCY, PWM_MIN_PULSE, PWM_MAX_PULSE, SERVO_CHANNELS,
                         FRONT_LEG_CHANNELS, SERVO_OFFSETS,
                         SERVO_ANGLE_MIN, SERVO_ANGLE_MAX, SERVO_TEST_ENDPOINT_VALUES,
                         SERVO_MAX_ANGLE, SERVO_MIN_ANGLE, SERVO_ANGLE_ADJUSTMENT)

import numpy as np
import time as _time

def _load_servo_hardware():
    """Import and return PCA9685, servo, and busio modules; raises RuntimeError if unavailable."""
    try:
        from adafruit_pca9685 import PCA9685
        from adafruit_motor import servo
        import busio
    except ImportError as exc:
        raise RuntimeError("Servo hardware dependencies are not available") from exc
    return PCA9685, servo, busio

class QuadrupedServoManager:
    """
    Controls all leg servos on the Wildfire Spot quadruped robot.

    Initializes two PCA9685 boards over a shared I2C bus and exposes
    methods to convert kinematics solver output into physical servo movements.
    Camera pan/tilt is managed by CameraControlManager.
    """

    def __init__(self):
        """
        Open the I2C bus and initialise the two PCA9685 PWM drivers.

        All 12 leg servos are configured with PWM_MIN_PULSE/PWM_MAX_PULSE limits.
        Raises RuntimeError if hardware dependencies or the I2C bus are unavailable.
        """
        self._i2c_interface = None
        self._front_driver = None
        self._rear_driver = None
        try:
            PCA9685, servo, busio = _load_servo_hardware()
            print("Initializing servo hardware")

            # One shared I2C bus for both PCA9685 boards.
            # SCL_1/SDA_1 maps to Jetson Orin Nano Super header pins 27/28.
            self._i2c_interface = busio.I2C(I2C_SCL, I2C_SDA)
            print("Setting up servo drivers")

            # Front board (0x41): channels 0-5 for FL/FR legs, channels 6-7 shared with camera
            self._front_driver = PCA9685(self._i2c_interface, address=PCA9685_FRONT_LEGS)
            self._front_driver.frequency = PWM_FREQUENCY

            # Rear board (0x42): channels 0-5 for BL/BR legs
            self._rear_driver = PCA9685(self._i2c_interface, address=PCA9685_BACK_LEGS)
            self._rear_driver.frequency = PWM_FREQUENCY
        except (ValueError, RuntimeError, OSError) as e:
            print(f"Servo driver initialization failed: {type(e).__name__}: {e}")
            self.shutdown_servos()
            raise

        # Build a flat list of 12 Servo objects indexed 0-11.
        # Indices 0-5  → front board channels 0-5  (FL then FR)
        # Indices 6-11 → rear  board channels 0-5  (BL then BR)
        self._servo_array = list()
        for servo_index in range(0, SERVO_CHANNELS):
            if servo_index < FRONT_LEG_CHANNELS:
                self._servo_array.append(servo.Servo(self._front_driver.channels[servo_index], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE))
            else:
                # Rear board channel = global index minus the front channel count
                self._servo_array.append(servo.Servo(self._rear_driver.channels[servo_index-FRONT_LEG_CHANNELS], min_pulse=PWM_MIN_PULSE, max_pulse=PWM_MAX_PULSE))

        print("Servo initialization complete")

        # Per-channel mechanical offsets applied during angle mapping
        self._offset_values = SERVO_OFFSETS

        # Working buffer for computed servo angles before they are written
        self._angle_array = [servo_index for servo_index in range(SERVO_CHANNELS)]
        self._joint_angles = []

        # Diagnostic rate-limit: last time SERVO_DEBUG was emitted
        self._diag_last_log = 0.0
        self._DIAG_INTERVAL = 1.0

    def convert_to_degrees(self, angle_radians):
        """
        Convert a 4x3 array of joint angles from radians to integer degrees.

        Args:
            angle_radians: numpy array of shape (4, 3) — one row per leg,
                           columns are [shoulder, femur, tibia] in radians.

        Stores the result in self._joint_angles as a list of lists of ints.
        """
        angle_degrees = angle_radians * 180/np.pi
        angle_degrees_int = [[int(value) for value in row] for row in angle_degrees]
        self._joint_angles = angle_degrees_int

    def process_angle_mapping(self, angle_radians):
        """
        Map kinematics solver joint angles to per-channel servo commands.

        Converts radians to degrees, then applies per-channel offset corrections
        and sign inversions to account for physical servo mounting orientation.
        Leg layout:
          Channels 0-2:  front-left  (FL)
          Channels 3-5:  front-right (FR)
          Channels 6-8:  back-left   (BL)
          Channels 9-11: back-right  (BR)

        Args:
            angle_radians: numpy array of shape (4, 3) in radians.
        """
        self.convert_to_degrees(angle_radians)

        if len(self._joint_angles) < 4 or any(len(leg) < 3 for leg in self._joint_angles):
            print("Invalid joint angles array size")
            return

        # Front-left leg (IK leg index 0) — servos on CH0-2 of front board
        self._angle_array[0] = self._offset_values[0] - self._joint_angles[0][2]  # tibia
        self._angle_array[1] = self._offset_values[1] - self._joint_angles[0][1]  # femur
        self._angle_array[2] = self._offset_values[2] + self._joint_angles[0][0]  # shoulder

        # Front-right leg (IK leg index 1) — servos on CH3-5 of front board
        # Right side joints are mirrored, so signs are inverted relative to FL
        self._angle_array[3] = self._offset_values[3] + self._joint_angles[1][2]  # tibia
        self._angle_array[4] = self._offset_values[4] + self._joint_angles[1][1]  # femur
        self._angle_array[5] = self._offset_values[5] - self._joint_angles[1][0]  # shoulder

        # Back-left leg (IK leg index 2) — servos on CH0-2 of rear board (global CH6-8)
        self._angle_array[6] = self._offset_values[6] - self._joint_angles[2][2]  # tibia
        self._angle_array[7] = self._offset_values[7] - self._joint_angles[2][1]  # femur
        self._angle_array[8] = self._offset_values[8] - self._joint_angles[2][0]  # shoulder

        # Back-right leg (IK leg index 3) — servos on CH3-5 of rear board (global CH9-11)
        self._angle_array[9]  = self._offset_values[9]  + self._joint_angles[3][2]  # tibia
        self._angle_array[10] = self._offset_values[10] + self._joint_angles[3][1]  # femur
        self._angle_array[11] = self._offset_values[11] + self._joint_angles[3][0]  # shoulder

    def get_front_driver(self):
        """
        Return the front PCA9685 driver instance.

        Allows callers (e.g. CameraControlManager) to reuse the same driver
        object for camera channels CH6/CH7, avoiding a second deinit on the
        shared board.  Returns None if the driver was not initialised.
        """
        return self._front_driver

    def get_current_angles(self):
        """Return the most recently computed per-channel servo angles (degrees)."""
        return self._angle_array

    def execute_servo_motion(self, joint_angles):
        """
        Convert joint angles and drive all 12 leg servos to the target positions.

        Clamps each channel to [SERVO_MIN_ANGLE+1, SERVO_MAX_ANGLE-1] before
        writing to the hardware to protect servo mechanical limits.

        Args:
            joint_angles: numpy array of shape (4, 3) in radians.
        """
        self.process_angle_mapping(joint_angles)

        # Snapshot angles before clamp for diagnostic comparison
        _before_clamp = list(self._angle_array)

        write_count = 0
        for servo_index in range(len(self._angle_array)):
            # Clamp to safe hardware limits before writing
            if (self._angle_array[servo_index] > SERVO_MAX_ANGLE):
                print("Angle exceeds maximum limit")
                self._angle_array[servo_index] = SERVO_MAX_ANGLE - SERVO_ANGLE_ADJUSTMENT
            if (self._angle_array[servo_index] <= SERVO_MIN_ANGLE):
                print("Angle below minimum limit")
                self._angle_array[servo_index] = SERVO_MIN_ANGLE + SERVO_ANGLE_ADJUSTMENT
            self._servo_array[servo_index].angle = float(self._angle_array[servo_index])
            write_count += 1

        # Diagnostic log — emitted at most once per second
        try:
            _now = _time.time()
            if _now - self._diag_last_log >= self._DIAG_INTERVAL:
                self._diag_last_log = _now
                _after_clamp = list(self._angle_array)
                _clamped_ch = [i for i in range(len(_before_clamp)) if _before_clamp[i] != _after_clamp[i]]
                print(
                    f"SERVO_DEBUG | "
                    f"mapped_before_clamp={[round(v, 1) for v in _before_clamp]} "
                    f"final_after_clamp={_after_clamp} "
                    f"clamped_channels={_clamped_ch} "
                    f"write_complete={write_count}"
                )
        except Exception:
            pass

    def shutdown_servos(self):
        """
        Deinitialize all PCA9685 drivers and release the I2C bus.

        Safe to call even if initialisation partially failed.
        Should be invoked during system shutdown.
        """
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
