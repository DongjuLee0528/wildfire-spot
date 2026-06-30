"""
Fire detection module integrating multiple sensors and camera.

Combines sensor data (smoke, temperature, humidity, flame) with
optional camera-based detection to identify and locate wildfires.
"""

from utils.config import (MQ2_SMOKE_THRESHOLD, TEMP_THRESHOLD, HUMIDITY_THRESHOLD,
                         DIRECTION_ANGLE_MULTIPLIER, DEFAULT_DIRECTION_VALUE, KY026_COUNT)
from utils.logger import WildfireLogger
from math import isfinite
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
    - Camera-based detection (AI inference - not yet implemented)
    - GPS location tracking
    - Pan-tilt camera control for fire direction tracking
    """

    def __init__(self, sensor_manager, gps_manager, pan_tilt_controller):
        """
        Initialize fire detector with hardware managers.

        Args:
            sensor_manager: SensorManager instance for reading sensors
            gps_manager: GPSManager instance for location tracking
            pan_tilt_controller: PanTiltController for camera aiming
        """
        self.sensor_manager = sensor_manager
        self.gps_manager = gps_manager
        self.pan_tilt_controller = pan_tilt_controller
        self.camera_detected = False
        self.sensor_detected = False
        self.detection_log = []  # History of fire detections
        self._last_detection_result = False
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
            False (not yet implemented)

        TODO: Implement AI model inference for visual fire detection
        """
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
            True if fire detected by sensors or camera
            False otherwise

        Combines both sensor and camera detection methods.
        If fire detected, automatically logs the event with GPS location
        and tracks fire direction with pan-tilt camera.
        """
        try:
            sensor_data = self.sensor_manager.read_all()

            # Check both detection methods
            camera_detection = self.detect_by_camera()
            sensor_detection = self._check_sensor_thresholds(sensor_data)

            fire_detected = False

            # Fire confirmed if either detection method triggers
            if sensor_detection:
                fire_detected = True
                if camera_detection:
                    self.camera_detected = True
            elif camera_detection:
                fire_detected = True
                self.camera_detected = True

            # On detection, log full context and track fire direction
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
