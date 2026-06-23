import os
from pathlib import Path


def _env_path(name, default):
    return str(Path(os.environ.get(name, default)).expanduser())


def _env_int(name, default):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        print(f"Invalid integer for {name}: {value}. Using default: {default}")
        return default


def _env_int_or_auto(name, default):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    if value.strip().lower() == "auto":
        return "auto"
    try:
        return int(value)
    except ValueError:
        print(f"Invalid integer for {name}: {value}. Using default: {default}")
        return default


def _env_float(name, default):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        print(f"Invalid float for {name}: {value}. Using default: {default}")
        return default


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

try:
    import board
    I2C_SCL = board.SCL_1
    I2C_SDA = board.SDA_1
except (ImportError, AttributeError):
    I2C_SCL = None
    I2C_SDA = None

BASE_DIR = _env_path("WILDFIRE_BASE_DIR", "/workspace")
LOG_DIR = _env_path("WILDFIRE_LOG_DIR", os.path.join(BASE_DIR, "wildfire_logs"))

PCA9685_FRONT_LEGS = 0x40
PCA9685_BACK_LEGS = 0x41
PCA9685_CAMERA = 0x42

ADS1115_MQ2_1 = 0x48
ADS1115_MQ2_2 = 0x49

SHT31_ADDRESS = 0x44
MPU6050_ADDRESS = 0x68

PWM_FREQUENCY = 60
PWM_MIN_PULSE = 460
PWM_MAX_PULSE = 2440
SERVO_ANGLE_MIN = 0
SERVO_ANGLE_MAX = 180

FL_LOWER = 0
FL_UPPER = 1
FL_SHOULDER = 2

FR_LOWER = 3
FR_UPPER = 4
FR_SHOULDER = 5

BL_LOWER = 6
BL_UPPER = 7
BL_SHOULDER = 8

BR_LOWER = 9
BR_UPPER = 10
BR_SHOULDER = 11

CAMERA_PAN = 0
CAMERA_TILT = 1

SERVO_OFFSETS = [180, 90, 90, 1, 90, 90, 180, 90, 90, 1, 90, 90]

GPS_UART_PORT = "/dev/ttyTHS1"
GPS_BAUDRATE = 9600

LIDAR_UART_PORT = "/dev/ttyTHS0"
LIDAR_BAUDRATE = 230400

KY026_FRONT_LEFT_PIN = 11
KY026_FRONT_RIGHT_PIN = 13
KY026_LEFT_PIN = 15
KY026_RIGHT_PIN = 16
KY026_PIN_1 = KY026_FRONT_LEFT_PIN
KY026_PIN_2 = KY026_FRONT_RIGHT_PIN
KY026_PIN_3 = KY026_LEFT_PIN
KY026_PIN_4 = KY026_RIGHT_PIN
KY026_COUNT = 4

HCSR04_TRIGGER_PIN = 18
HCSR04_ECHO_PIN = 22

CAMERA_DEVICE = "/dev/video0"
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30

MQ2_SMOKE_THRESHOLD = 300

TEMP_THRESHOLD = 60
HUMIDITY_THRESHOLD = 20

STEP_HEIGHT = 40
FORWARD_DISTANCE = 120
BACKWARD_DISTANCE = -50

SERVO_CHANNELS = 12
FRONT_LEG_CHANNELS = 6

CAMERA_CENTER_ANGLE = 90.0
CAMERA_SCAN_ANGLES = [45.0, 135.0]
TIME_SLEEP_SCAN = [2, 1]

LIDAR_OBSTACLE_THRESHOLD = 500
LIDAR_DATA_SIZE = 42
LIDAR_PACKET_HEADER = [0xAA, 0xAA]
LIDAR_FULL_SCAN_SIZE = 360
LIDAR_DIRECTION_COUNT = 8
LIDAR_DIRECTION_ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]
LIDAR_ANGLE_RANGE = 22
LIDAR_REVERSE_DIRECTION = 180
LIDAR_PATH_CHECK_RANGE = 10

GAIT_STEP_GAIN = 0.8
GAIT_MAX_SL = 2
GAIT_BODY_POS = (0, 100, 0)
GAIT_BODY_ROT = (0, 0, 0)
GAIT_TIMING = [300, 1200, 300, 200]
GAIT_INITIAL_VALUES = [0.0, 0, 0]
GAIT_FOOT_POSITIONS = [87, 77]
GAIT_RC = [-50, 0, 0, 1]
GAIT_ANGLE_STEP = 0.5
GAIT_END_Y = 0
GAIT_TOTAL_TIME_CALC = 1000

ROBOT_L1 = 50
ROBOT_L2 = 20
ROBOT_L3 = 100
ROBOT_L4 = 100
ROBOT_L = 140
ROBOT_W = 75

ROBOT_LEG_FRONT = 0
ROBOT_LEG_BACK = 2
ROBOT_LEG_LEFT = 0
ROBOT_LEG_RIGHT = 1

ROBOT_BODY_HEIGHT = -100

KB_KEY_VALUES = {'w': 0, 'a': 0, 's': 0, 'd': 0, 'q': 0, 'e': 0, 'move': False}
KB_CONTROL_OFFSET = {'IDstepLength': 0.0, 'IDstepWidth': 0.0, 'IDstepAlpha': 0.0, 'StartStepping': False}
KB_X_STEP_DIVISOR = 12.0
KB_Y_STEP = 5.0
KB_YAW_STEP = 3.0

MATH_PI_DIVISOR = 180

DATASET_ROOT_PATH = _env_path("WILDFIRE_DATASET_ROOT", "/workspace/wildfire-dataset")

DATASET_OUTPUT_PATH = _env_path(
    "WILDFIRE_DATASET_OUTPUT",
    os.path.join(DATASET_ROOT_PATH, "unified_dataset"),
)

DFIRE_CLEAN_YOLO_PATH = _env_path(
    "DFIRE_CLEAN_YOLO_PATH",
    "/workspace/wildfire-extra-datasets/DFire/clean_yolo",
)

NASA_AMS_CLEAN_YOLO_PATH = _env_path(
    "NASA_AMS_CLEAN_YOLO_PATH",
    "/workspace/wildfire-extra-datasets/NASA AMS/clean_yolo_patches",
)

KB_TEST_SLEEP_TIME = 1

ULTRASONIC_DISTANCE_MULTIPLIER = 17150
DIRECTION_ANGLE_MULTIPLIER = 90
DEFAULT_DIRECTION_VALUE = 0.0
SERVO_TEST_ENDPOINT_VALUES = [[100, -100, 87.5, 1], [100, -100, -87.5, 1], [-100, -100, 87.5, 1], [-100, -100, -87.5, 1]]

PATROL_ZONE = []
PATROL_ZONE_MIN_POINTS = 3

GPS_READ_MAX_ATTEMPTS = 10

SENSOR_READ_TIMEOUT = 5.0
SENSOR_CHANNEL_DIVISOR = 2

LIDAR_READ_TIMEOUT = 10.0

SERVO_MAX_ANGLE = 180
SERVO_MIN_ANGLE = 0
SERVO_ANGLE_ADJUSTMENT = 1

DATASET_TRAIN_RATIO = 0.8
DATASET_VAL_RATIO = 0.1
DATASET_RANDOM_SEED = 42

AIHUB_DATASET_SUBPATH = "regional-safety-disaster-wildfire/01-1.official-open-data"
WANDB_PROJECT = os.environ.get("WANDB_PROJECT", "wildfire-detection")
WANDB_ENTITY = os.environ.get("WANDB_ENTITY") or None
TRAIN_MODEL_PATH = os.environ.get("WILDFIRE_TRAIN_MODEL", "yolov10s.pt")
TRAIN_DATA_YAML = _env_path(
    "WILDFIRE_TRAIN_DATA_YAML",
    os.path.join(DATASET_OUTPUT_PATH, "data.yaml"),
)
TRAIN_PROJECT_PATH = _env_path("WILDFIRE_TRAIN_PROJECT_PATH", "/workspace/runs")
TRAIN_OUTPUT_DIR = _env_path("WILDFIRE_TRAIN_OUTPUT_DIR", TRAIN_PROJECT_PATH)
TRAIN_EPOCHS = _env_int("WILDFIRE_TRAIN_EPOCHS", 200)
TRAIN_BATCH_SIZE = _env_int_or_auto("WILDFIRE_TRAIN_BATCH_SIZE", 32)
TRAIN_IMAGE_SIZE = _env_int("WILDFIRE_TRAIN_IMAGE_SIZE", 1280)
TRAIN_SAVE_PERIOD = _env_int("WILDFIRE_TRAIN_SAVE_PERIOD", 10)
TRAIN_PATIENCE = _env_int("WILDFIRE_TRAIN_PATIENCE", 30)
TRAIN_DEVICE = os.environ.get("WILDFIRE_TRAIN_DEVICE", "cuda")
TRAIN_NAME = os.environ.get("WILDFIRE_TRAIN_NAME", "wildfire_v1")
TRAIN_RUN_NAME = os.environ.get("WILDFIRE_TRAIN_RUN_NAME", TRAIN_NAME)
TRAIN_WORKERS = _env_int("WILDFIRE_TRAIN_WORKERS", 4)
TRAIN_RESUME = os.environ.get("WILDFIRE_TRAIN_RESUME", "").strip()
TRAIN_EXIST_OK = _env_bool("WILDFIRE_TRAIN_EXIST_OK", False)
TRAIN_AUGMENT = _env_bool("WILDFIRE_TRAIN_AUGMENT", True)
TRAIN_MOSAIC = _env_float("WILDFIRE_TRAIN_MOSAIC", 1.0)
TRAIN_HSV_H = _env_float("WILDFIRE_TRAIN_HSV_H", 0.02)
TRAIN_HSV_S = _env_float("WILDFIRE_TRAIN_HSV_S", 0.8)
TRAIN_HSV_V = _env_float("WILDFIRE_TRAIN_HSV_V", 0.4)
TRAIN_FLIPUD = _env_float("WILDFIRE_TRAIN_FLIPUD", 0.5)
TRAIN_FLIPLR = _env_float("WILDFIRE_TRAIN_FLIPLR", 0.5)

KINEMATICS_L1_DEFAULT = 50
KINEMATICS_L2_DEFAULT = 20
KINEMATICS_L3_DEFAULT = 100
KINEMATICS_L4_DEFAULT = 100
KINEMATICS_L_DEFAULT = 140
KINEMATICS_W_DEFAULT = 75
KINEMATICS_HEIGHT_DEFAULT = -100
KINEMATICS_BODY_POS_DEFAULT = (0, 100, 0)
KINEMATICS_BODY_ROT_DEFAULT = (0, 0, 0)
