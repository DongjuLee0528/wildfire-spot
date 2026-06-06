from utils.config import *
from hardware.sensor_manager import SensorManager
from hardware.gps_manager import GPSManager


class FireDetector:
    def __init__(self, sensor_manager, gps_manager):
        self.sensor_manager = sensor_manager
        self.gps_manager = gps_manager
        self.camera_detected = False
        self.sensor_detected = False

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

    def is_fire_detected(self):
        try:
            camera_detection = self.detect_by_camera()
            sensor_detection = self.detect_by_sensor()

            if camera_detection and sensor_detection:
                return True
            elif camera_detection and not self.sensor_detected:
                return self.detect_by_sensor()
            elif sensor_detection and not self.camera_detected:
                return self.detect_by_camera()

            return False

        except Exception as e:
            return False

    def get_fire_location(self):
        try:
            if self.is_fire_detected():
                return self.gps_manager.get_coordinates()
            return None
        except Exception as e:
            return None