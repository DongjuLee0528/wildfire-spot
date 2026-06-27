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

    @abstractmethod
    def get_status(self) -> RobotStatusData: ...

    @abstractmethod
    def get_gps(self) -> RobotGpsData: ...

    @abstractmethod
    def get_sensors(self) -> RobotSensorData: ...

    @abstractmethod
    def get_health(self) -> RobotHealthData: ...

    @abstractmethod
    def get_fire_status(self) -> RobotFireStatusData: ...

    @abstractmethod
    def get_logs(self) -> RobotLogsData: ...
