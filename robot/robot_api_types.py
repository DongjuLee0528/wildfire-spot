"""
Shared data transfer types for the Robot API layer.

All types are plain dataclasses used to pass data between
RobotDataCollector implementations and the FastAPI server.
No business logic belongs here.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FlameStatus:
    """Per-direction flame sensor readings from the four KY-026 sensors."""
    front_left: bool
    front_right: bool
    left: bool
    right: bool


@dataclass
class RobotStatusData:
    """Current robot operational state and connection status."""
    state: str
    mode: str
    robot_connected: bool
    last_update: datetime


@dataclass
class RobotGpsData:
    """Most recent GPS fix with coordinates and validity flag."""
    latitude: float
    longitude: float
    fix: bool
    updated_at: datetime


@dataclass
class RobotSensorData:
    """Snapshot of all environmental sensor readings."""
    temperature: float
    humidity: float
    mq2_gas: int
    flame: FlameStatus
    lidar_status: str


@dataclass
class RobotHealthData:
    """Availability flags for each hardware subsystem."""
    robot_core: bool
    camera: bool
    gps: bool
    lidar: bool
    sensors: bool


@dataclass
class RobotFireStatusData:
    """Aggregated fire detection result from hardware and camera channels."""
    hardware_confirmed: bool
    camera_detected: bool
    final_confirmed_fire: bool


@dataclass
class RobotLogEntry:
    """Single structured log entry with level, message, and timestamp."""
    level: str
    message: str
    timestamp: datetime


@dataclass
class RobotLogsData:
    """Collection of recent log entries for the API log endpoint."""
    logs: list[RobotLogEntry] = field(default_factory=list)
