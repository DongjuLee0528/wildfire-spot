"""
Abstract data-collection interface for the Robot API layer.

Defines the contract that every RobotDataCollector implementation must satisfy.
Concrete subclasses (e.g. RobotCoreDataCollector) adapt live hardware managers
to these typed return values; test doubles can provide mock data without hardware.
"""

from abc import ABC, abstractmethod
from robot.robot_api_types import (
    RobotStatusData,
    RobotGpsData,
    RobotSensorData,
    RobotHealthData,
    RobotFireStatusData,
    RobotLogsData,
)


class RobotDataCollector(ABC):
    """Abstract base class that supplies typed robot data to the API server."""

    @abstractmethod
    def get_status(self) -> RobotStatusData:
        """Return the current robot state and operational mode."""
        ...

    @abstractmethod
    def get_gps(self) -> RobotGpsData:
        """Return the latest GPS coordinates and fix validity."""
        ...

    @abstractmethod
    def get_sensors(self) -> RobotSensorData:
        """Return a snapshot of all environmental sensor readings."""
        ...

    @abstractmethod
    def get_health(self) -> RobotHealthData:
        """Return availability flags for each hardware subsystem."""
        ...

    @abstractmethod
    def get_fire_status(self) -> RobotFireStatusData:
        """Return the aggregated fire detection result from all detection channels."""
        ...

    @abstractmethod
    def get_logs(self) -> RobotLogsData:
        """Return recent structured log entries from the robot logger."""
        ...
