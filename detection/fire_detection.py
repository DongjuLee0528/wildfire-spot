from utils.config import (MQ2_SMOKE_THRESHOLD, TEMP_THRESHOLD, HUMIDITY_THRESHOLD,
                         DIRECTION_ANGLE_MULTIPLIER, DEFAULT_DIRECTION_VALUE, KY026_COUNT)
from hardware.sensor_manager import SensorManager
from hardware.gps_manager import GPSManager
from hardware.pan_tilt_controller import PanTiltController
from utils.logger import WildfireLogger
import time


class FireDetector:

    def __init__(self, sensor_manager, gps_manager, pan_tilt_controller):
        self.sensor_manager = sensor_manager
        self.gps_manager = gps_manager
        self.pan_tilt_controller = pan_tilt_controller
        self.camera_detected = False
        self.sensor_detected = False
        self.detection_log = []
        self._last_detection_result = False
        self.logger = WildfireLogger("FireDetector")

    def _check_sensor_thresholds(self, sensor_data):
        try:
            smoke_level = sensor_data.get('smoke', 0)
            temperature = sensor_data.get('temperature', 0)
            humidity = sensor_data.get('humidity', 100)
            flame_detected = sensor_data.get('flame', False)
            if isinstance(flame_detected, list):
                flame_detected = any(flame_detected)

            if (smoke_level > MQ2_SMOKE_THRESHOLD or
                temperature > TEMP_THRESHOLD or
                humidity < HUMIDITY_THRESHOLD or
                flame_detected):
                self.sensor_detected = True
                return True

            self.sensor_detected = False
            return False

        except (ValueError, RuntimeError, KeyError) as e:
            self.logger.log_error("FireDetector._check_sensor_thresholds", str(e))
            return False

    def detect_by_sensor(self):
        try:
            sensor_data = self.sensor_manager.read_all()
            return self._check_sensor_thresholds(sensor_data)
        except (ValueError, RuntimeError, KeyError) as e:
            self.logger.log_error("FireDetector.detect_by_sensor", str(e))
            return False

    def detect_by_camera(self):
        return False

    def track_fire_direction(self, sensor_data):
        try:
            flame_sensors = sensor_data.get('flame', [False] * KY026_COUNT)

            if any(flame_sensors):
                detected_directions = []
                for i, detected in enumerate(flame_sensors):
                    if detected:
                        detected_directions.append(i * DIRECTION_ANGLE_MULTIPLIER)

                if detected_directions:
                    avg_direction = sum(detected_directions) / len(detected_directions)
                    self.pan_tilt_controller.rotate_to_angle(avg_direction, DEFAULT_DIRECTION_VALUE)
                    return avg_direction

            return None

        except (ValueError, RuntimeError, KeyError, ZeroDivisionError) as e:
            self.logger.log_error("FireDetector.track_fire_direction", str(e))
            return None

    def log_detection(self, location, direction, sensor_data):
        try:
            detection_record = {
                "timestamp": time.time(),
                "latitude": location[0] if (location and len(location) >= 2) else DEFAULT_DIRECTION_VALUE,
                "longitude": location[1] if (location and len(location) >= 2) else DEFAULT_DIRECTION_VALUE,
                "direction": direction if direction else DEFAULT_DIRECTION_VALUE,
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
        try:
            if not self.detection_log:
                return None

            strongest_record = max(self.detection_log, key=lambda x: x['smoke'])
            return strongest_record['direction']

        except (ValueError, KeyError) as e:
            self.logger.log_error("FireDetector.get_strongest_direction", str(e))
            return None

    def is_fire_detected(self):
        try:
            sensor_data = self.sensor_manager.read_all()

            camera_detection = self.detect_by_camera()
            sensor_detection = self._check_sensor_thresholds(sensor_data)

            fire_detected = False

            if sensor_detection:
                fire_detected = True
                if camera_detection:
                    self.camera_detected = True
            elif camera_detection:
                fire_detected = True
                self.camera_detected = True

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
        try:
            if self._last_detection_result:
                return self.gps_manager.get_coordinates()
            return None
        except (ValueError, RuntimeError) as e:
            self.logger.log_error("FireDetector.get_fire_location", str(e))
            return None