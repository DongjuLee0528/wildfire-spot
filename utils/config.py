
"""
Hardware configuration settings for wildfire detection quadruped robot.

This module contains all configuration constants for the quadruped robot system including:
- I2C device addresses for sensors and servo controllers
- GPIO pin assignments for various sensors
- PWM settings for servo motors
- Camera and LIDAR configuration parameters
- Robot kinematics and gait parameters
- Fire detection thresholds and safety limits
- Dataset paths for AI training

Usage:
    from utils.config import *

Author: Wildfire Detection Team
"""

import board

# ===== I2C Device Addresses =====
# PCA9685 PWM controllers for servo motor control
PCA9685_FRONT_LEGS = 0x40   # Controls front leg servos (FL, FR)
PCA9685_BACK_LEGS = 0x41    # Controls back leg servos (BL, BR)
PCA9685_CAMERA = 0x42       # Controls camera pan/tilt servos

# ADS1115 ADC modules for analog sensor readings
ADS1115_MQ2_1 = 0x48        # First MQ-2 smoke sensor ADC
ADS1115_MQ2_2 = 0x49        # Second MQ-2 smoke sensor ADC

# Environmental and motion sensors
SHT31_ADDRESS = 0x44        # Temperature and humidity sensor
MPU6050_ADDRESS = 0x68      # 6-axis gyroscope and accelerometer

# I2C bus configuration for Jetson Nano
# Using I2C bus 0 (pins 28,27) instead of default bus 1 (pins 5,3)
I2C_SCL = board.SCL_1        # Clock line for I2C bus 0
I2C_SDA = board.SDA_1        # Data line for I2C bus 0

# ===== PWM and Servo Configuration =====
PWM_FREQUENCY = 60           # 60Hz PWM frequency for servo control
PWM_MIN_PULSE = 460          # Minimum pulse width (microseconds) for 0° servo position
PWM_MAX_PULSE = 2440         # Maximum pulse width (microseconds) for 180° servo position
SERVO_ANGLE_MIN = 0          # Minimum servo angle (degrees)
SERVO_ANGLE_MAX = 180        # Maximum servo angle (degrees)

# ===== Servo Channel Mapping =====
# Front Left leg servo channels
FL_LOWER = 0                 # Front left lower leg servo
FL_UPPER = 1                 # Front left upper leg servo
FL_SHOULDER = 2              # Front left shoulder servo

# Front Right leg servo channels
FR_LOWER = 3                 # Front right lower leg servo
FR_UPPER = 4                 # Front right upper leg servo
FR_SHOULDER = 5              # Front right shoulder servo

# Back Left leg servo channels
BL_LOWER = 6                 # Back left lower leg servo
BL_UPPER = 7                 # Back left upper leg servo
BL_SHOULDER = 8              # Back left shoulder servo

# Back Right leg servo channels
BR_LOWER = 9                 # Back right lower leg servo
BR_UPPER = 10                # Back right upper leg servo
BR_SHOULDER = 11             # Back right shoulder servo

# Camera servo channels
CAMERA_PAN = 0               # Camera pan (horizontal rotation) servo channel
CAMERA_TILT = 1              # Camera tilt (vertical rotation) servo channel

# Servo calibration offsets to compensate for mechanical alignment
# Values represent angular offsets (degrees) for each servo channel
SERVO_OFFSETS = [180, 90, 90, 1, 90, 90, 180, 90, 90, 1, 90, 90]

# ===== Communication Ports =====
# GPS module serial communication
GPS_UART_PORT = "/dev/ttyTHS1"   # UART port for GPS module
GPS_BAUDRATE = 9600              # Standard GPS communication baud rate

# LIDAR sensor serial communication
LIDAR_UART_PORT = "/dev/ttyTHS0" # UART port for LIDAR sensor
LIDAR_BAUDRATE = 230400          # High-speed LIDAR communication baud rate

# ===== GPIO Pin Assignments =====
# KY-026 flame sensor pins (4-directional flame detection)
KY026_PIN_1 = None              # North direction flame sensor pin
KY026_PIN_2 = None              # East direction flame sensor pin
KY026_PIN_3 = None              # South direction flame sensor pin
KY026_PIN_4 = None              # West direction flame sensor pin

# HC-SR04 ultrasonic distance sensor pins
HCSR04_TRIGGER_PIN = None       # Trigger pin for ultrasonic sensor
HCSR04_ECHO_PIN = None          # Echo pin for ultrasonic sensor

# ===== Camera Configuration =====
CAMERA_DEVICE = "/dev/video0"   # Video device path for camera
CAMERA_WIDTH = 640              # Camera frame width (pixels)
CAMERA_HEIGHT = 480             # Camera frame height (pixels)
CAMERA_FPS = 30                 # Camera frames per second

# ===== Fire Detection Thresholds =====
# Critical safety thresholds for fire detection algorithms
MQ2_SMOKE_THRESHOLD = 300       # Smoke concentration threshold (ADC units) for fire alert

# Environmental thresholds indicating fire conditions
TEMP_THRESHOLD = 60             # Temperature threshold (°C) for fire detection
HUMIDITY_THRESHOLD = 20         # Low humidity threshold (%) indicating fire risk

# ===== Robot Movement Parameters =====
STEP_HEIGHT = 40                # Maximum leg lift height (mm) during walking
FORWARD_DISTANCE = 120          # Forward step distance (mm) per gait cycle
BACKWARD_DISTANCE = -50         # Backward step distance (mm) per gait cycle

# ===== System Configuration =====
SERVO_CHANNELS = 12             # Total number of servo channels (4 legs × 3 joints)
FRONT_LEG_CHANNELS = 6          # Number of servo channels for front legs

# Camera scanning behavior for fire detection
CAMERA_CENTER_ANGLE = 90.0      # Center position angle for camera pan servo
CAMERA_SCAN_ANGLES = [45.0, 135.0]  # Left and right scan angles for fire detection
TIME_SLEEP_SCAN = [2, 1]        # Sleep times [scan_pause, move_pause] in seconds

# ===== LIDAR Configuration =====
# Settings for LIDAR-based obstacle detection and navigation
LIDAR_OBSTACLE_THRESHOLD = 500  # Minimum distance (mm) to consider as obstacle
LIDAR_DATA_SIZE = 42            # Size of LIDAR data packet in bytes
LIDAR_PACKET_HEADER = [0xAA, 0xAA]  # Packet header bytes for LIDAR data validation
LIDAR_FULL_SCAN_SIZE = 360      # Full 360-degree scan size
LIDAR_DIRECTION_COUNT = 8       # Number of directional sectors for obstacle detection
LIDAR_DIRECTION_ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]  # Angle sectors (degrees)
LIDAR_ANGLE_RANGE = 22          # Angular range (±degrees) for each direction sector
LIDAR_REVERSE_DIRECTION = 180   # Direction (degrees) for reverse movement when blocked
LIDAR_PATH_CHECK_RANGE = 10     # Angular range (±degrees) for path clearance check

# ===== Gait and Movement Parameters =====
# Trotting gait configuration for quadruped locomotion
GAIT_STEP_GAIN = 0.8            # Step gain factor for gait amplitude control
GAIT_MAX_SL = 2                 # Maximum step length multiplier
GAIT_BODY_POS = (0, 100, 0)     # Default body position (x, y, z) in mm
GAIT_BODY_ROT = (0, 0, 0)       # Default body rotation (roll, pitch, yaw) in degrees
GAIT_TIMING = [300, 1200, 300, 200]  # Gait phase timing [lift, swing, place, stance] in ms
GAIT_INITIAL_VALUES = [0.0, 0, 0]    # Initial step [length, width, angle] values
GAIT_FOOT_POSITIONS = [87, 77]  # Front and rear foot Y-positions (mm) from body center
GAIT_RC = [-50, 0, 0, 1]        # Gait reference coordinates
GAIT_ANGLE_STEP = 0.5           # Angular step size (degrees) for rotation movements
GAIT_END_Y = 0                  # Final Y-coordinate for leg placement
GAIT_TOTAL_TIME_CALC = 1000     # Total time factor for gait calculations (ms)

# ===== Robot Physical Dimensions =====
# Link lengths and body dimensions for inverse kinematics calculations
ROBOT_L1 = 50                   # Shoulder offset length (mm)
ROBOT_L2 = 20                   # Upper leg offset length (mm)
ROBOT_L3 = 100                  # Upper leg length (mm)
ROBOT_L4 = 100                  # Lower leg length (mm)
ROBOT_L = 140                   # Body length (mm) between front and rear legs
ROBOT_W = 75                    # Body width (mm) between left and right legs

# Robot leg indexing for kinematic calculations
ROBOT_LEG_FRONT = 0             # Index offset for front legs (FL=0, FR=1)
ROBOT_LEG_BACK = 2              # Index offset for back legs (BL=2, BR=3)
ROBOT_LEG_LEFT = 0              # Index offset for left-side legs
ROBOT_LEG_RIGHT = 1             # Index offset for right-side legs

# Default robot stance
ROBOT_BODY_HEIGHT = -100        # Default body height (mm) above ground (negative = below shoulder)

# ===== Keyboard Control Configuration =====
# Default key states for keyboard-controlled robot movement
KB_KEY_VALUES = {'w': 0, 'a': 0, 's': 0, 'd': 0, 'q': 0, 'e': 0, 'move': False}
# Control offset values for translating key presses to robot movement
KB_CONTROL_OFFSET = {'IDstepLength': 0.0, 'IDstepWidth': 0.0, 'IDstepAlpha': 0.0, 'StartStepping': False}
# Keyboard movement scaling factors
KB_X_STEP_DIVISOR = 12.0        # Divisor for forward/backward movement scaling
KB_Y_STEP = 5.0                 # Step size for left/right strafing movement
KB_YAW_STEP = 3.0               # Step size for rotation movement

# ===== Mathematical Constants =====
MATH_PI_DIVISOR = 180           # Divisor for converting radians to degrees (180/π)

# ===== AI Training Configuration =====
# File paths for wildfire detection dataset processing and training
DATASET_BASE_PATH = "/Users/dongjulee/Documents/AIdatasets/wildfire-dataset"        # Base directory for input datasets
DATASET_OUTPUT_PATH = "/Users/dongjulee/Documents/AIdatasets/wildfire-dataset/unified_dataset"  # Output directory for processed unified dataset

# ===== Testing and Debug Configuration =====
KB_TEST_SLEEP_TIME = 1          # Sleep time (seconds) for keyboard testing loops