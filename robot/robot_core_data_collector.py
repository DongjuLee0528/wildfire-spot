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

_DEFAULT_LIDAR_STATUS = "UNAVAILABLE"  # Reported when LidarManager is None or unavailable
_FALLBACK_MODE = "UNKNOWN"              # Reported when StateMachine cannot supply a mode string


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
        """
        Store references to all Robot Core managers.

        Args:
            state_machine: StateMachine providing the current robot state.
            gps_manager: GPSManager for location reads.
            sensor_manager: SensorManager for environmental sensor reads.
            lidar_manager: LidarManager used to derive lidar_status.
            fire_detector: FireDetector exposing detection flags.
            log_reader: Zero-argument callable returning list[dict] with keys
                        'level', 'message', and 'timestamp'.
        """
        self._state_machine = state_machine
        self._gps_manager = gps_manager
        self._sensor_manager = sensor_manager
        self._lidar_manager = lidar_manager
        self._fire_detector = fire_detector
        self._log_reader = log_reader

    @classmethod
    def from_runtime_context(cls, context, log_reader=None):
        """
        Construct a RobotCoreDataCollector from a RobotRuntimeContext.

        This is the canonical factory used by main.py and SpringTelemetry so
        that exactly one set of manager instances is ever referenced.

        Args:
            context: RobotRuntimeContext instance.
            log_reader: Optional zero-argument callable returning list[dict].
                        Defaults to returning an empty list.
        """
        return cls(
            state_machine=context.state_machine,
            gps_manager=context.gps_manager,
            sensor_manager=context.sensor_manager,
            lidar_manager=context.lidar_manager,
            fire_detector=context.fire_detector,
            log_reader=log_reader if log_reader is not None else (lambda: []),
        )

    def get_status(self) -> RobotStatusData:
        """
        Read current state and mode from StateMachine and return as RobotStatusData.

        robot_connected is always True because this method is only reachable
        when the robot core process is running. Returns UNKNOWN fallbacks when
        the StateMachine is None or raises.
        """
        if self._state_machine is None:
            return RobotStatusData(
                state="UNKNOWN",
                mode=_FALLBACK_MODE,
                robot_connected=True,
                last_update=datetime.now(),
            )

        try:
            state = self._state_machine.get_state().value
        except Exception as e:
            logger.error("get_status: state_machine error: %s", e)
            state = "UNKNOWN"

        try:
            mode = self._state_machine.get_mode().value
        except Exception as e:
            logger.error("get_status: state_machine mode error: %s", e)
            mode = _FALLBACK_MODE

        return RobotStatusData(
            state=state,
            mode=mode,
            robot_connected=True,
            last_update=datetime.now(),
        )

    def get_gps(self):
        """Read one GPS fix from GPSManager; returns None when manager is absent or no fix available."""
        if self._gps_manager is None:
            logger.debug("get_gps: GPS manager unavailable, skipping")
            return None

        try:
            coordinates = self._gps_manager.get_location()
        except Exception as e:
            logger.error("get_gps: gps_manager error: %s", e)
            return None

        if coordinates is None:
            # GPS module present but no valid fix yet
            return None

        try:
            latitude = float(coordinates[0])
            longitude = float(coordinates[1])
        except (TypeError, ValueError, IndexError) as e:
            logger.error("get_gps: invalid coordinates %r: %s", coordinates, e)
            return None

        # fix=True because get_location() only returns when status == 'A'
        return RobotGpsData(
            latitude=latitude,
            longitude=longitude,
            fix=True,
            updated_at=datetime.now(),
        )

    def get_sensors(self):
        """
        Read all environmental sensors and report LIDAR availability.

        Returns None when sensor manager is absent or read fails entirely.
        Calls SensorManager.read_all() and maps the result into RobotSensorData.
        FlameStatus is populated from either a dict or an ordered iterable.
        lidar_status is set to 'SCANNING' if LidarManager is available, else 'UNAVAILABLE'.
        """
        if self._sensor_manager is None:
            logger.debug("get_sensors: sensor manager unavailable, skipping")
            return None

        try:
            sensor_data = self._sensor_manager.read_all()
        except Exception as e:
            logger.error("get_sensors: sensor_manager.read_all() error: %s", e)
            return None
        if not sensor_data:
            return None

        try:
            raw_temperature = sensor_data.get("temperature")
            raw_humidity = sensor_data.get("humidity")
            raw_mq2_gas = sensor_data.get("smoke")
            raw_flame = sensor_data.get("flame")

            if raw_temperature is None or raw_humidity is None or raw_mq2_gas is None or raw_flame is None:
                logger.debug("get_sensors: required sensor data unavailable, skipping")
                return None

            temperature = float(raw_temperature)
            humidity = float(raw_humidity)
            mq2_gas = int(raw_mq2_gas)

            if isinstance(raw_flame, dict):
                # SensorManager.read_ky026() returns a FlameReadings dict keyed by position
                if any(value is None for value in raw_flame.values()):
                    logger.debug("get_sensors: flame sensor data partially unavailable, skipping")
                    return None
                flame = FlameStatus(
                    front_left=bool(raw_flame.get("front_left", False)),
                    front_right=bool(raw_flame.get("front_right", False)),
                    left=bool(raw_flame.get("left", False)),
                    right=bool(raw_flame.get("right", False)),
                )
            elif hasattr(raw_flame, "__iter__"):
                # Fallback: treat as ordered iterable [front_left, front_right, left, right]
                values = list(raw_flame)
                if len(values) < 4 or any(value is None for value in values[:4]):
                    logger.debug("get_sensors: flame sensor data unavailable, skipping")
                    return None
                flame = FlameStatus(
                    front_left=bool(values[0]) if len(values) > 0 else False,
                    front_right=bool(values[1]) if len(values) > 1 else False,
                    left=bool(values[2]) if len(values) > 2 else False,
                    right=bool(values[3]) if len(values) > 3 else False,
                )
            else:
                logger.debug("get_sensors: flame sensor data unavailable, skipping")
                return None
        except Exception as e:
            logger.error("get_sensors: sensor data mapping error: %s", e)
            return None

        # Derive lidar_status from LidarManager availability (no data upload channel for lidar)
        lidar_status = _DEFAULT_LIDAR_STATUS
        try:
            if self._lidar_manager is not None:
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
        """
        Poll each subsystem for availability and return a health snapshot.

        robot_core is always True (this method is only reachable if the core is running).
        camera is always False because CameraVision is wired into robot_api directly
        and is not referenced by this collector.
        gps, lidar, and sensors reflect each manager's is_available() result.
        """
        robot_core = True
        camera = False
        gps = False
        lidar = False
        sensors = False

        try:
            if self._gps_manager is not None:
                gps = self._gps_manager.is_available()
        except Exception as e:
            logger.error("get_health: gps check error: %s", e)

        try:
            if self._lidar_manager is not None:
                lidar = self._lidar_manager.is_available()
        except Exception as e:
            logger.error("get_health: lidar check error: %s", e)

        try:
            if self._sensor_manager is not None:
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

    def get_fire_status(self):
        """
        Read the latest staged fire detection result from FireDetector.

        Returns None when fire detector is absent.
        Uses public FireDetector methods: get_current_fire_state(),
        get_latest_alert_event(), get_latest_report_event().
        No sensor I/O is performed.
        """
        if self._fire_detector is None:
            logger.debug("get_fire_status: fire detector unavailable, skipping")
            return None

        try:
            from detection.fire_events import DetectionState
            fire_state = self._fire_detector.get_current_fire_state()
            # Map DetectionState enum value to uppercase API string
            state_str = {
                "normal": "NORMAL",
                "suspected_fire": "SUSPECTED_FIRE",
                "verified_fire": "VERIFIED_FIRE",
            }.get(fire_state.value, "NORMAL") if fire_state else "NORMAL"
            # suspected is True for both SUSPECTED and VERIFIED states
            suspected = fire_state in (DetectionState.SUSPECTED_FIRE, DetectionState.VERIFIED_FIRE)
            verified = fire_state is DetectionState.VERIFIED_FIRE
            camera_detected = bool(self._fire_detector.camera_detected)
            sensor_detected = bool(self._fire_detector.sensor_detected)
            # Defensive copies are produced by FireDetector to prevent external mutation
            latest_alert_event = self._fire_detector.get_latest_alert_event()
            latest_report_event = self._fire_detector.get_latest_report_event()
        except Exception as e:
            logger.error("get_fire_status: fire_detector error: %s", e)
            return None

        return RobotFireStatusData(
            state=state_str,
            suspected=suspected,
            verified=verified,
            camera_detected=camera_detected,
            sensor_detected=sensor_detected,
            latest_alert_event=latest_alert_event,
            latest_report_event=latest_report_event,
        )

    def get_logs(self) -> RobotLogsData:
        """
        Fetch recent log entries via the injected log_reader callable.

        Each raw dict is mapped to a RobotLogEntry; malformed entries are skipped
        and logged at ERROR level rather than raising.
        """
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
