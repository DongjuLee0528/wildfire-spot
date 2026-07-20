"""
Fire detection module integrating KY-026 flame sensors and camera AI.

Combines KY-026 flame sensor data with optional camera-based detection
to identify and locate wildfires. DHT11 temperature/humidity is used
only for environmental logging, not for fire boolean decisions.
"""

from utils.config import (DIRECTION_ANGLE_MULTIPLIER, DEFAULT_DIRECTION_VALUE, KY026_COUNT,
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
    - Camera-based fire/smoke AI detection (CameraVision)
    - KY-026 flame sensor detection
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
        self.sensor_detected = False           # True when KY026 flame sensor triggered
        self._current_fire_state = DetectionState.NORMAL  # State from the most recent evaluate()
        self._latest_alert_event = None       # AlertEvent from the most recent SUSPECTED_FIRE
        self._latest_report_event = None      # ReportEvent from the most recent VERIFIED_FIRE
        self.logger = WildfireLogger("FireDetector")

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

    def evaluate(self):
        """
        Run staged fire verification and return current state with any generated event.

        Detection rules:
        - SUSPECTED_FIRE: camera detects fire/smoke OR any KY026 flame sensor triggered.
          DHT11 alone does not trigger.
        - VERIFIED_FIRE: camera detection AND KY026 triggered.
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

        temperature = _safe_number(sensor_data.get("temperature", 0), 0)
        humidity = _safe_number(sensor_data.get("humidity", 100), 100)
        flame_raw = sensor_data.get("flame", False)
        flame_values = _flame_values(flame_raw)

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

        # Hard sensor trigger: any KY026 flame sensor active.
        # DHT11 temperature/humidity readings alone never produce a hard trigger.
        sensor_hard_triggered = ky026_triggered
        # Suspected if either the camera AI or KY026 triggered
        suspected = camera_fire or sensor_hard_triggered

        self.sensor_detected = sensor_hard_triggered

        if not suspected:
            # Clear any stale event state when conditions return to normal
            self._current_fire_state = DetectionState.NORMAL
            self._latest_alert_event = None
            self._latest_report_event = None
            return DetectionState.NORMAL, None, None

        # VERIFIED_FIRE requires both camera confirmation AND KY026 trigger
        if camera_fire and sensor_hard_triggered:
            state = DetectionState.VERIFIED_FIRE
            reasons = []
            if ky026_triggered:
                reasons.append("ky026")
            if camera_fire:
                reasons.append("camera")
            reason_str = "+".join(reasons)  # e.g. "ky026+camera" or "camera"
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

        # SUSPECTED_FIRE: camera OR KY026, but not both simultaneously
        reasons = []
        if camera_fire:
            reasons.append("camera")
        if ky026_triggered:
            reasons.append("ky026")
        reason_str = "+".join(reasons)  # e.g. "camera" or "ky026"
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
