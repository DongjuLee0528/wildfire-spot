"""
Fire detection module integrating multiple sensors and camera.

Combines sensor data (smoke, temperature, humidity, flame) with
optional camera-based detection to identify and locate wildfires.
"""

from utils.config import (MQ2_SMOKE_THRESHOLD, TEMP_THRESHOLD, HUMIDITY_THRESHOLD,
                         DIRECTION_ANGLE_MULTIPLIER, DEFAULT_DIRECTION_VALUE, KY026_COUNT,
                         EVIDENCE_DIR)
from utils.logger import WildfireLogger
from detection.fire_events import AlertEvent, DetectionState, ReportEvent
from math import isfinite
import copy
import time


def _safe_number(value, default):
    """Return value as a finite float, or default if conversion fails or the result is non-finite."""
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not isfinite(number):
        return default
    return number


def _flame_values(flame_data):
    """Normalise flame sensor data into a flat list of values regardless of input type."""
    if isinstance(flame_data, dict):
        return list(flame_data.values())
    if isinstance(flame_data, bool):
        return [flame_data]
    try:
        return list(flame_data)
    except TypeError:
        return [bool(flame_data)]


class FireDetector:
    """
    Multi-modal fire detection system.

    Integrates:
    - Sensor-based detection (smoke, temperature, humidity, flame)
    - Optional CameraVision candidate detection
    - GPS location tracking
    - Pan-tilt camera control for fire direction tracking
    """

    def __init__(self, sensor_manager, gps_manager, pan_tilt_controller, camera_vision=None):
        """
        Initialize fire detector with hardware managers.

        Args:
            sensor_manager: SensorManager instance for reading sensors
            gps_manager: GPSManager instance for location tracking
            pan_tilt_controller: PanTiltController for camera aiming
            camera_vision: Optional CameraVision instance for AI-based detection
        """
        self.sensor_manager = sensor_manager
        self.gps_manager = gps_manager
        self.pan_tilt_controller = pan_tilt_controller
        self.camera_vision = camera_vision
        self.camera_detected = False          # True when camera AI reports fire/smoke
        self.sensor_detected = False           # True when hardware sensors exceed thresholds
        self.detection_log = []               # History of fire detections for direction analysis
        self._last_detection_result = False   # Result of the most recent is_fire_detected() call
        self._current_fire_state = DetectionState.NORMAL  # State from the most recent evaluate()
        self._latest_alert_event = None       # AlertEvent from the most recent SUSPECTED_FIRE
        self._latest_report_event = None      # ReportEvent from the most recent VERIFIED_FIRE
        self.logger = WildfireLogger("FireDetector")

    def _check_sensor_thresholds(self, sensor_data):
        """
        Check if sensor readings exceed fire detection thresholds.

        Args:
            sensor_data: Dictionary containing sensor readings

        Returns:
            True if any threshold exceeded (fire conditions detected)
            False otherwise

        Fire indicators:
        - High smoke level (MQ2)
        - High temperature
        - Low humidity (dry conditions)
        - Any flame sensor triggered
        """
        try:
            if sensor_data is None or not hasattr(sensor_data, 'get'):
                self.sensor_detected = False
                return False

            smoke_level = sensor_data.get('smoke', 0)
            temperature = sensor_data.get('temperature', 0)
            humidity = sensor_data.get('humidity', 100)
            flame_detected = sensor_data.get('flame', False)
            smoke_level = _safe_number(smoke_level, 0)
            temperature = _safe_number(temperature, 0)
            humidity = _safe_number(humidity, 100)
            flame_detected = any(bool(value) for value in _flame_values(flame_detected))

            # Check if any fire indicator threshold is exceeded
            if (smoke_level > MQ2_SMOKE_THRESHOLD or
                temperature > TEMP_THRESHOLD or
                humidity < HUMIDITY_THRESHOLD or
                flame_detected):
                self.sensor_detected = True
                return True

            self.sensor_detected = False
            return False

        except (ValueError, RuntimeError, KeyError, TypeError) as e:
            self.logger.log_error("FireDetector._check_sensor_thresholds", str(e))
            return False

    def detect_by_sensor(self):
        """
        Perform sensor-based fire detection.

        Returns:
            True if fire detected by sensors, False otherwise
        """
        try:
            sensor_data = self.sensor_manager.read_all()
            return self._check_sensor_thresholds(sensor_data)
        except (ValueError, RuntimeError, KeyError) as e:
            self.logger.log_error("FireDetector.detect_by_sensor", str(e))
            return False

    def detect_by_camera(self):
        """
        Perform camera-based fire detection using AI inference.

        Returns:
            True if CameraVision detects fire or smoke, False otherwise.
            Returns False if no CameraVision instance is attached or inference fails.
        """
        if self.camera_vision is None:
            return False
        try:
            result = self.camera_vision.detect()
            self.camera_detected = bool(result.get("detected", False))
            return self.camera_detected
        except Exception as e:
            self.logger.log_error("FireDetector.detect_by_camera", str(e))
            self.camera_detected = False
            return False

    def track_fire_direction(self, sensor_data):
        """
        Determine fire direction from flame sensors and aim camera.

        Args:
            sensor_data: Dictionary containing flame sensor readings

        Returns:
            Average direction angle (degrees) where flame detected
            None if no flame detected or error occurs

        Uses 4 KY-026 flame sensors positioned at different angles.
        Calculates average direction and rotates pan-tilt camera to face it.
        """
        try:
            if sensor_data is None or not hasattr(sensor_data, 'get'):
                return DEFAULT_DIRECTION_VALUE

            flame_sensors = sensor_data.get('flame', [False] * KY026_COUNT)
            flame_sensors = _flame_values(flame_sensors)

            if any(flame_sensors):
                detected_directions = []
                # Convert sensor index to angle based on sensor positions
                for i, detected in enumerate(flame_sensors):
                    if detected:
                        detected_directions.append(i * DIRECTION_ANGLE_MULTIPLIER)

                if detected_directions:
                    # Calculate average angle of detected flames
                    avg_direction = sum(detected_directions) / len(detected_directions)
                    # Point camera toward fire
                    self.pan_tilt_controller.rotate_to_angle(avg_direction, DEFAULT_DIRECTION_VALUE)
                    return avg_direction

            return DEFAULT_DIRECTION_VALUE

        except (ValueError, RuntimeError, KeyError, ZeroDivisionError, TypeError) as e:
            self.logger.log_error("FireDetector.track_fire_direction", str(e))
            return DEFAULT_DIRECTION_VALUE

    def log_detection(self, location, direction, sensor_data):
        """
        Record a fire detection event with full context.

        Args:
            location: GPS coordinates (latitude, longitude) or None
            direction: Fire direction angle or None
            sensor_data: Dictionary of all sensor readings

        Stores detection in internal log and writes to logger.
        Detection history can be used to track fire movement or find strongest signal.
        """
        try:
            detection_record = {
                "timestamp": time.time(),
                "latitude": location[0] if (location and len(location) >= 2) else DEFAULT_DIRECTION_VALUE,
                "longitude": location[1] if (location and len(location) >= 2) else DEFAULT_DIRECTION_VALUE,
                "direction": direction if direction is not None else DEFAULT_DIRECTION_VALUE,
                "smoke": sensor_data.get('smoke', 0),
                "temperature": sensor_data.get('temperature', 0.0),
                "humidity": sensor_data.get('humidity', 0.0),
                "flame": sensor_data.get('flame', [False] * KY026_COUNT)
            }
            self.detection_log.append(detection_record)
            self.logger.log_fire_detected(location, sensor_data, direction)

        except (ValueError, RuntimeError, KeyError) as e:
            self.logger.log_error("FireDetector", str(e))

    def get_strongest_direction(self):
        """
        Get direction of strongest fire detection from log history.

        Returns:
            Direction angle with highest smoke reading
            None if no detections logged or error occurs

        Useful for determining primary fire source when multiple detections exist.
        """
        try:
            if not self.detection_log:
                return None

            # Find detection with highest smoke level
            strongest_record = max(self.detection_log, key=lambda x: x['smoke'])
            return strongest_record['direction']

        except (ValueError, KeyError) as e:
            self.logger.log_error("FireDetector.get_strongest_direction", str(e))
            return None

    def is_fire_detected(self):
        """
        Perform comprehensive fire detection check.

        Returns:
            True if fire detected by hardware sensors
            False otherwise

        Camera detection is recorded as candidate evidence but does not
        replace hardware sensor confirmation. If fire is confirmed by
        sensors, automatically logs the event with GPS location and tracks
        fire direction with pan-tilt camera.
        """
        try:
            sensor_data = self.sensor_manager.read_all()

            # Run camera detection for logging/evidence even though it is not
            # authoritative — only hardware sensor thresholds determine fire_detected.
            self.detect_by_camera()
            sensor_detection = self._check_sensor_thresholds(sensor_data)

            # Camera result is stored but does not override sensor-based decision
            fire_detected = sensor_detection

            # On sensor-confirmed detection, record full context and aim camera
            if fire_detected:
                location = self.gps_manager.get_coordinates()
                direction = self.track_fire_direction(sensor_data)
                self.log_detection(location, direction, sensor_data)

            self._last_detection_result = fire_detected
            return fire_detected

        except (ValueError, RuntimeError, KeyError) as e:
            self.logger.log_error("FireDetector.is_fire_detected", str(e))
            return False

    def get_fire_location(self):
        """
        Get GPS coordinates of last fire detection.

        Returns:
            Tuple of (latitude, longitude) if fire detected
            None if no fire detected or GPS unavailable

        Only returns location if most recent detection check found fire.
        """
        try:
            if self._last_detection_result:
                return self.gps_manager.get_coordinates()
            return None
        except (ValueError, RuntimeError) as e:
            self.logger.log_error("FireDetector.get_fire_location", str(e))
            return None

    def evaluate(self):
        """
        Run staged fire verification and return current state with any generated event.

        Detection rules:
        - SUSPECTED_FIRE: camera detects fire/smoke OR MQ2 smoke threshold exceeded OR
          any KY026 flame sensor triggered. DHT11 alone does not trigger.
        - VERIFIED_FIRE: camera detection AND (MQ2 threshold exceeded OR KY026 triggered).
          DHT11 readings alone never produce VERIFIED_FIRE.

        Returns:
            Tuple of (DetectionState, Optional[AlertEvent], Optional[ReportEvent]).
            Exactly one of AlertEvent or ReportEvent is non-None when state is not NORMAL.
        """
        try:
            sensor_data = self.sensor_manager.read_all()
        except Exception as e:
            self.logger.log_error("FireDetector.evaluate", f"sensor read failed: {e}")
            sensor_data = {}

        if sensor_data is None:
            sensor_data = {}

        smoke = _safe_number(sensor_data.get("smoke", 0), 0)
        temperature = _safe_number(sensor_data.get("temperature", 0), 0)
        humidity = _safe_number(sensor_data.get("humidity", 100), 100)
        flame_raw = sensor_data.get("flame", False)
        flame_values = _flame_values(flame_raw)

        mq2_triggered = smoke > MQ2_SMOKE_THRESHOLD
        ky026_triggered = any(bool(v) for v in flame_values)

        try:
            camera_result = self.camera_vision.detect() if self.camera_vision is not None else None
            camera_fire = bool(camera_result.get("detected", False)) if camera_result else False
        except Exception as e:
            self.logger.log_error("FireDetector.evaluate", f"camera detection failed: {e}")
            camera_result = None
            camera_fire = False

        self.camera_detected = camera_fire

        try:
            coords = self.gps_manager.get_coordinates()
            lat = coords[0] if (coords and len(coords) >= 2) else None
            lon = coords[1] if (coords and len(coords) >= 2) else None
        except Exception:
            lat = None
            lon = None

        # Hard sensor triggers: MQ2 smoke above threshold OR any KY026 flame sensor active.
        # DHT11 temperature/humidity readings alone never produce a hard trigger.
        sensor_hard_triggered = mq2_triggered or ky026_triggered
        # Suspected if either the camera AI or any hard sensor triggered
        suspected = camera_fire or sensor_hard_triggered

        self.sensor_detected = sensor_hard_triggered

        if not suspected:
            # Clear any stale event state when conditions return to normal
            self._current_fire_state = DetectionState.NORMAL
            self._latest_alert_event = None
            self._latest_report_event = None
            return DetectionState.NORMAL, None, None

        # VERIFIED_FIRE requires both camera confirmation AND at least one hard sensor
        if camera_fire and sensor_hard_triggered:
            state = DetectionState.VERIFIED_FIRE
            reasons = []
            if mq2_triggered:
                reasons.append("mq2")
            if ky026_triggered:
                reasons.append("ky026")
            if camera_fire:
                reasons.append("camera")
            reason_str = "+".join(reasons)  # e.g. "mq2+ky026+camera"
            image_path = None
            if self.camera_vision is not None:
                try:
                    # Save a JPEG frame as forensic evidence for the report
                    image_path = self.camera_vision.save_evidence_image("verified_fire", EVIDENCE_DIR)
                except Exception as e:
                    self.logger.log_error("FireDetector.evaluate", f"evidence save failed: {e}")
            now = time.time()
            event = ReportEvent(
                state=state,
                timestamp=now,
                report_timestamp=now,
                latitude=lat,
                longitude=lon,
                smoke=smoke,
                temperature=temperature,
                humidity=humidity,
                flame=flame_raw,
                camera_detected=camera_fire,
                camera_result=camera_result,
                verification_reason=reason_str,
                image_path=image_path,
            )
            self._current_fire_state = state
            self._latest_report_event = event
            self.logger.info(f"FIRE_EVAL | VERIFIED_FIRE | reason={reason_str} | lat={lat}, lon={lon}")
            return state, None, event

        # SUSPECTED_FIRE: camera OR hard sensor, but not both simultaneously
        reasons = []
        if camera_fire:
            reasons.append("camera")
        if mq2_triggered:
            reasons.append("mq2")
        if ky026_triggered:
            reasons.append("ky026")
        reason_str = "+".join(reasons)  # e.g. "camera" or "mq2+ky026"
        state = DetectionState.SUSPECTED_FIRE
        image_path = None
        if self.camera_vision is not None:
            try:
                # Save preliminary evidence image for the alert
                image_path = self.camera_vision.save_evidence_image("suspected_fire", EVIDENCE_DIR)
            except Exception as e:
                self.logger.log_error("FireDetector.evaluate", f"evidence save failed: {e}")
        event = AlertEvent(
            state=state,
            timestamp=time.time(),
            latitude=lat,
            longitude=lon,
            smoke=smoke,
            temperature=temperature,
            humidity=humidity,
            flame=flame_raw,
            camera_detected=camera_fire,
            camera_result=camera_result,
            verification_reason=reason_str,
            image_path=image_path,
        )
        self._current_fire_state = state
        self._latest_alert_event = event
        self._latest_report_event = None
        self.logger.info(f"FIRE_EVAL | SUSPECTED_FIRE | reason={reason_str} | lat={lat}, lon={lon}")
        return state, event, None

    def get_current_fire_state(self):
        """
        Return the DetectionState from the most recent evaluate() call.

        Returns:
            DetectionState: NORMAL, SUSPECTED_FIRE, or VERIFIED_FIRE.
        """
        return self._current_fire_state

    def get_latest_alert_event(self):
        """
        Return a defensive copy of the AlertEvent from the most recent SUSPECTED_FIRE evaluation.

        Returns:
            AlertEvent copy or None.
        """
        if self._latest_alert_event is None:
            return None
        return copy.deepcopy(self._latest_alert_event)

    def get_latest_report_event(self):
        """
        Return a defensive copy of the ReportEvent from the most recent VERIFIED_FIRE evaluation.

        Returns:
            ReportEvent copy or None.
        """
        if self._latest_report_event is None:
            return None
        return copy.deepcopy(self._latest_report_event)

    def get_latest_evaluation(self):
        """
        Return a defensive copy snapshot of the most recent evaluate() result.

        Returns:
            dict with keys: state, alert_event, report_event.
        """
        return {
            "state": self._current_fire_state,
            "alert_event": copy.deepcopy(self._latest_alert_event),
            "report_event": copy.deepcopy(self._latest_report_event),
        }
