from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FlameStatus:
    front_left: bool
    front_right: bool
    left: bool
    right: bool


@dataclass
class RobotStatusData:
    state: str
    mode: str
    robot_connected: bool
    last_update: datetime


@dataclass
class RobotGpsData:
    latitude: float
    longitude: float
    fix: bool
    updated_at: datetime


@dataclass
class RobotSensorData:
    temperature: float
    humidity: float
    mq2_gas: int
    flame: FlameStatus
    lidar_status: str


@dataclass
class RobotHealthData:
    robot_core: bool
    camera: bool
    gps: bool
    lidar: bool
    sensors: bool


@dataclass
class RobotFireStatusData:
    hardware_confirmed: bool
    camera_detected: bool
    final_confirmed_fire: bool


@dataclass
class RobotLogEntry:
    level: str
    message: str
    timestamp: datetime


@dataclass
class RobotLogsData:
    logs: list[RobotLogEntry] = field(default_factory=list)
