"""
Concrete RobotDataCollector that reads from Robot Core managers.

Bridges:
    StateMachine   -> RobotStatusData
    GPSManager     -> RobotGpsData
    SensorManager  -> RobotSensorData  (+ LidarManager for lidar_status)
    all managers   -> RobotHealthData
    FireDetector   -> RobotFireStatusData
    WildfireLogger -> RobotLogsData

Business logic stays in the managers.
This class only maps data into API contract types.
"""

import logging
from datetime import datetime

from robot.robot_data_collector import RobotDataCollector
from robot.robot_api_types import (
    FlameStatus,
    RobotStatusData,
    RobotGpsData,
    RobotSensorData,
    RobotHealthData,
    RobotFireStatusData,
    RobotLogEntry,
    RobotLogsData,
)

logger = logging.getLogger(__name__)

# Phase 5 TODO:
# Replace this placeholder with runtime mode from StateMachine or ModeManager.
# For Phase 4-3 read-only scope, mode is always reported as AUTO.
_ROBOT_MODE = "AUTO"
_DEFAULT_LIDAR_STATUS = "UNAVAILABLE"


class RobotCoreDataCollector(RobotDataCollector):
    """
    Maps Robot Core managers into RobotDataCollector contract.

    Args:
        state_machine: StateMachine instance
        gps_manager: GPSManager instance
        sensor_manager: SensorManager instance
        lidar_manager: LidarManager instance
        fire_detector: FireDetector instance
        log_reader: callable that returns list[dict] with keys level/message/timestamp
    """

    def __init__(
        self,
        state_machine,
        gps_manager,
        sensor_manager,
        lidar_manager,
        fire_detector,
        log_reader,
    ):
        self._state_machine = state_machine
        self._gps_manager = gps_manager
        self._sensor_manager = sensor_manager
        self._lidar_manager = lidar_manager
        self._fire_detector = fire_detector
        self._log_reader = log_reader

    def get_status(self) -> RobotStatusData:
        try:
            state = self._state_machine.get_state().value
        except Exception as e:
            logger.error("get_status: state_machine error: %s", e)
            state = "UNKNOWN"

        return RobotStatusData(
            state=state,
            mode=_ROBOT_MODE,
            robot_connected=True,
            last_update=datetime.now(),
        )

    def get_gps(self) -> RobotGpsData:
        latitude = 0.0
        longitude = 0.0
        fix = False

        try:
            coordinates = self._gps_manager.get_location()
            if coordinates is not None:
                latitude, longitude = float(coordinates[0]), float(coordinates[1])
                fix = True
        except Exception as e:
            logger.error("get_gps: gps_manager error: %s", e)

        return RobotGpsData(
            latitude=latitude,
            longitude=longitude,
            fix=fix,
            updated_at=datetime.now(),
        )

    def get_sensors(self) -> RobotSensorData:
        temperature = 0.0
        humidity = 0.0
        mq2_gas = 0
        flame = FlameStatus(front_left=False, front_right=False, left=False, right=False)
        lidar_status = _DEFAULT_LIDAR_STATUS

        try:
            sensor_data = self._sensor_manager.read_all()
            temperature = float(sensor_data.get("temperature", 0.0))
            humidity = float(sensor_data.get("humidity", 0.0))
            mq2_gas = int(sensor_data.get("smoke", 0))

            raw_flame = sensor_data.get("flame", {})
            if isinstance(raw_flame, dict):
                flame = FlameStatus(
                    front_left=bool(raw_flame.get("front_left", False)),
                    front_right=bool(raw_flame.get("front_right", False)),
                    left=bool(raw_flame.get("left", False)),
                    right=bool(raw_flame.get("right", False)),
                )
            elif hasattr(raw_flame, "__iter__"):
                values = list(raw_flame)
                flame = FlameStatus(
                    front_left=bool(values[0]) if len(values) > 0 else False,
                    front_right=bool(values[1]) if len(values) > 1 else False,
                    left=bool(values[2]) if len(values) > 2 else False,
                    right=bool(values[3]) if len(values) > 3 else False,
                )
        except Exception as e:
            logger.error("get_sensors: sensor_manager error: %s", e)

        try:
            lidar_status = "SCANNING" if self._lidar_manager.is_available() else "UNAVAILABLE"
        except Exception as e:
            logger.error("get_sensors: lidar_manager error: %s", e)

        return RobotSensorData(
            temperature=temperature,
            humidity=humidity,
            mq2_gas=mq2_gas,
            flame=flame,
            lidar_status=lidar_status,
        )

    def get_health(self) -> RobotHealthData:
        robot_core = True
        camera = False
        gps = False
        lidar = False
        sensors = False

        try:
            gps = self._gps_manager.is_available()
        except Exception as e:
            logger.error("get_health: gps check error: %s", e)

        try:
            lidar = self._lidar_manager.is_available()
        except Exception as e:
            logger.error("get_health: lidar check error: %s", e)

        try:
            sensors = self._sensor_manager.is_available()
        except Exception as e:
            logger.error("get_health: sensor check error: %s", e)

        return RobotHealthData(
            robot_core=robot_core,
            camera=camera,
            gps=gps,
            lidar=lidar,
            sensors=sensors,
        )

    def get_fire_status(self) -> RobotFireStatusData:
        hardware_confirmed = False
        camera_detected = False
        final_confirmed_fire = False

        try:
            hardware_confirmed = bool(self._fire_detector.sensor_detected)
            camera_detected = bool(self._fire_detector.camera_detected)
            final_confirmed_fire = bool(self._fire_detector._last_detection_result)
        except Exception as e:
            logger.error("get_fire_status: fire_detector error: %s", e)

        return RobotFireStatusData(
            hardware_confirmed=hardware_confirmed,
            camera_detected=camera_detected,
            final_confirmed_fire=final_confirmed_fire,
        )

    def get_logs(self) -> RobotLogsData:
        entries = []
        try:
            raw_logs = self._log_reader()
            for record in raw_logs:
                try:
                    ts = record.get("timestamp", datetime.now())
                    if not isinstance(ts, datetime):
                        ts = datetime.now()
                    entries.append(
                        RobotLogEntry(
                            level=str(record.get("level", "INFO")),
                            message=str(record.get("message", "")),
                            timestamp=ts,
                        )
                    )
                except Exception as inner:
                    logger.error("get_logs: entry mapping error: %s", inner)
        except Exception as e:
            logger.error("get_logs: log_reader error: %s", e)

        return RobotLogsData(logs=entries)
