from utils.config import *
from hardware.sensor_manager import SensorManager
from hardware.gps_manager import GPSManager
from hardware.pan_tilt_controller import PanTiltController
import time


class FireDetector:

    def __init__(self, sensor_manager, gps_manager, pan_tilt_controller):
        self.sensor_manager = sensor_manager
        self.gps_manager = gps_manager
        self.pan_tilt_controller = pan_tilt_controller
        self.camera_detected = False
        self.sensor_detected = False
        self.detection_log = []

    def detect_by_sensor(self):
        try:
            sensor_data = self.sensor_manager.read_all_sensors()

            smoke_level = sensor_data.get('mq2_smoke', 0)
            temperature = sensor_data.get('temperature', 0)
            humidity = sensor_data.get('humidity', 100)
            flame_detected = sensor_data.get('ky026_flame', False)

            if (smoke_level > MQ2_SMOKE_THRESHOLD or
                temperature > TEMP_THRESHOLD or
                humidity < HUMIDITY_THRESHOLD or
                flame_detected):
                self.sensor_detected = True
                return True

            self.sensor_detected = False
            return False

        except Exception as e:
            return False

    def detect_by_camera(self):
        return False

    def track_fire_direction(self, sensor_data):
        try:
            flame_sensors = sensor_data.get('ky026_flame', [False, False, False, False])

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

        except Exception as e:
            return None

    def log_detection(self, location, direction, sensor_data):
        try:
            detection_record = {
                "timestamp": time.time(),
                "latitude": location[0] if location else DEFAULT_DIRECTION_VALUE,
                "longitude": location[1] if location else DEFAULT_DIRECTION_VALUE,
                "direction": direction if direction else DEFAULT_DIRECTION_VALUE,
                "smoke": sensor_data.get('mq2_smoke', 0),
                "temperature": sensor_data.get('temperature', 0.0),
                "humidity": sensor_data.get('humidity', 0.0),
                "flame": sensor_data.get('ky026_flame', [False, False, False, False])
            }
            self.detection_log.append(detection_record)

        except Exception as e:
            pass

    def get_strongest_direction(self):
        try:
            if not self.detection_log:
                return None

            strongest_record = max(self.detection_log, key=lambda x: x['smoke'])
            return strongest_record['direction']

        except Exception as e:
            return None

    def is_fire_detected(self):
        try:
            camera_detection = self.detect_by_camera()
            sensor_detection = self.detect_by_sensor()

            fire_detected = False

            if sensor_detection:
                fire_detected = True
                if camera_detection:
                    self.camera_detected = True
            elif camera_detection:
                fire_detected = True
                self.camera_detected = True

            if fire_detected:
                sensor_data = self.sensor_manager.read_all_sensors()
                location = self.gps_manager.get_coordinates()
                direction = self.track_fire_direction(sensor_data)
                self.log_detection(location, direction, sensor_data)

            return fire_detected

        except Exception as e:
            return False

    def get_fire_location(self):
        try:
            if self.is_fire_detected():
                return self.gps_manager.get_coordinates()
            return None
        except Exception as e:
            return None