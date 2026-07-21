"""
Single shared runtime context for the Wildfire Spot Robot Core.

Owns one instance of each hardware manager and the state machine.
Both Robot Core logic (PatrolZoneCalibrator, main loop, robot_api) and
SpringTelemetry must read from this object — never from separately
constructed manager instances.

Unavailable managers
--------------------
lidar_manager : None
    LidarManager requires Ethernet UDP access to the Unitree L2 sensor.
    It is not instantiated in the keyboard-control runtime (main.py).
    Telemetry will report lidar_status=UNAVAILABLE and skip no uploads
    because lidar data is not a telemetry upload channel.

camera_vision : None
    CameraControlManager / CameraVision is created separately and wired
    into robot_api.  FireDetector accepts it as an optional argument; when
    None, camera-based detection is simply skipped.
"""

import logging

logger = logging.getLogger(__name__)


class RobotRuntimeContext:
    """
    Owns the single shared instance of every Robot Core manager.

    Create once at startup, then pass to PatrolZoneCalibrator, robot_api,
    RobotCoreDataCollector, and SpringTelemetry.

    All attributes are public and read-only after construction.
    """

    def __init__(self):
        """
        Initialise all hardware managers in dependency order.

        Managers that fail to initialise are left as None; callers must
        handle None values. Initialisation order matters:
        1. StateMachine — no hardware dependency
        2. GPSManager   — UART/USB GPS device
        3. SensorManager — I2C/GPIO sensors (DHT11, KY026)
        4. FireDetector — requires sensor_manager and gps_manager
        """
        self.gps_manager = None
        self.sensor_manager = None
        self.lidar_manager = None    # Not initialised here; see module docstring
        self.state_machine = None
        self.fire_detector = None

        self._init_state_machine()
        self._init_gps()
        self._init_sensors()
        self._init_fire_detector()

    def _init_state_machine(self):
        """Instantiate StateMachine; sets self.state_machine or logs and leaves it None."""
        try:
            from utils.state_machine import StateMachine
            self.state_machine = StateMachine()
            logger.info("RobotRuntimeContext: StateMachine initialised")
        except Exception as e:
            logger.error("RobotRuntimeContext: StateMachine init failed: %s", e)

    def _init_gps(self):
        """Open the GPS serial device; sets self.gps_manager or logs and leaves it None."""
        try:
            from hardware.gps_manager import GPSManager
            self.gps_manager = GPSManager()
            logger.info("RobotRuntimeContext: GPSManager initialised")
        except Exception as e:
            logger.error("RobotRuntimeContext: GPSManager init failed: %s", e)

    def _init_sensors(self):
        """Initialise I2C/GPIO sensors; sets self.sensor_manager or logs and leaves it None."""
        try:
            from hardware.sensor_manager import SensorManager
            self.sensor_manager = SensorManager()
            logger.info("RobotRuntimeContext: SensorManager initialised")
        except Exception as e:
            logger.error("RobotRuntimeContext: SensorManager init failed: %s", e)

    def _init_fire_detector(self):
        """
        Instantiate FireDetector if both sensor_manager and gps_manager are available.

        pan_tilt_controller is passed as None because CameraControlManager is
        initialised separately (after servo hardware) and wired into robot_api;
        FireDetector can operate without it and will skip camera-based detection.
        """
        if self.sensor_manager is None or self.gps_manager is None:
            logger.warning(
                "RobotRuntimeContext: FireDetector skipped "
                "(sensor_manager=%s, gps_manager=%s)",
                self.sensor_manager,
                self.gps_manager,
            )
            return
        try:
            from detection.fire_detection import FireDetector
            self.fire_detector = FireDetector(
                sensor_manager=self.sensor_manager,
                gps_manager=self.gps_manager,
                pan_tilt_controller=None,
            )
            logger.info("RobotRuntimeContext: FireDetector initialised")
        except Exception as e:
            logger.error("RobotRuntimeContext: FireDetector init failed: %s", e)

    def close(self):
        """Release all hardware resources owned by this context."""
        for name, mgr in [
            ("gps_manager", self.gps_manager),
            ("sensor_manager", self.sensor_manager),
            ("lidar_manager", self.lidar_manager),
        ]:
            if mgr is not None and hasattr(mgr, "close"):
                try:
                    mgr.close()
                except Exception as e:
                    logger.error("RobotRuntimeContext: %s.close() error: %s", name, e)
        if self.state_machine is not None and hasattr(self.state_machine, "close"):
            try:
                self.state_machine.close()
            except Exception as e:
                logger.error("RobotRuntimeContext: state_machine.close() error: %s", e)
