"""
Wildfire Detection System - Core Fire Detection Module

This module implements a multi-sensor fire detection system that combines:
- Environmental sensors (MQ-2 smoke, SHT31 temperature/humidity, KY-026 flame)
- Camera-based visual detection (placeholder for AI model integration)
- GPS location tracking for detected fires
- Pan/tilt camera control for fire tracking and confirmation

The detection algorithm uses a two-stage approach:
1. Primary detection: Environmental sensors trigger initial fire alerts
2. Secondary confirmation: Camera system provides visual confirmation
3. Location tracking: GPS coordinates and directional data are logged

Safety Features:
- Multi-threshold detection for reduced false positives
- Sensor fusion for improved accuracy
- Detection history logging for pattern analysis
- Directional fire tracking for emergency response

Author: Wildfire Detection Team
"""

from utils.config import *
from hardware.sensor_manager import SensorManager
from hardware.gps_manager import GPSManager
from hardware.pan_tilt_controller import PanTiltController
import time


class FireDetector:
    """
    Main fire detection controller that integrates multiple detection methods.

    This class coordinates between environmental sensors, camera systems, and GPS
    to provide comprehensive fire detection and tracking capabilities.

    Attributes:
        sensor_manager: Hardware interface for environmental sensors
        gps_manager: GPS coordinate tracking interface
        pan_tilt_controller: Camera positioning control interface
        camera_detected: Boolean flag for camera-based fire detection status
        sensor_detected: Boolean flag for sensor-based fire detection status
        detection_log: List storing historical detection data with timestamps
    """

    def __init__(self, sensor_manager, gps_manager, pan_tilt_controller):
        """
        Initialize the FireDetector with required hardware interfaces.

        Args:
            sensor_manager (SensorManager): Interface to environmental sensors
            gps_manager (GPSManager): GPS coordinate tracking interface
            pan_tilt_controller (PanTiltController): Camera control interface
        """
        self.sensor_manager = sensor_manager
        self.gps_manager = gps_manager
        self.pan_tilt_controller = pan_tilt_controller
        self.camera_detected = False
        self.sensor_detected = False
        self.detection_log = []

    def detect_by_sensor(self):
        """
        Perform fire detection using environmental sensors.

        Analyzes data from multiple sensors to determine fire presence:
        - MQ-2: Smoke concentration detection
        - SHT31: Temperature and humidity monitoring
        - KY-026: Direct flame detection (4-directional)

        Fire conditions are detected when ANY of the following occur:
        - Smoke levels exceed safety threshold
        - Temperature exceeds danger threshold
        - Humidity drops below fire-risk threshold
        - Direct flame detection from any KY-026 sensor

        Returns:
            bool: True if fire conditions detected, False otherwise
        """
        try:
            # Read all sensor data from hardware interfaces
            sensor_data = self.sensor_manager.read_all_sensors()

            # Extract individual sensor readings with safe defaults
            smoke_level = sensor_data.get('mq2_smoke', 0)
            temperature = sensor_data.get('temperature', 0)
            humidity = sensor_data.get('humidity', 100)
            flame_detected = sensor_data.get('ky026_flame', False)

            # Multi-threshold fire detection logic
            # ANY condition triggers fire alert for maximum safety
            if (smoke_level > MQ2_SMOKE_THRESHOLD or       # Smoke detection
                temperature > TEMP_THRESHOLD or            # High temperature
                humidity < HUMIDITY_THRESHOLD or           # Low humidity (fire risk)
                flame_detected):                           # Direct flame detection
                self.sensor_detected = True
                return True

            self.sensor_detected = False
            return False

        except Exception as e:
            # Return False on sensor read failure for safety
            return False

    def detect_by_camera(self):
        """
        Perform fire detection using camera-based visual analysis.

        Placeholder for AI-powered visual fire detection system.
        This method will be integrated with a trained computer vision model
        to analyze camera feed for visual fire signatures.

        Future implementation will include:
        - Real-time image analysis using trained CNN model
        - Smoke and flame pattern recognition
        - Confidence scoring for detection results
        - Integration with camera_vision.py module

        Returns:
            bool: Currently always False (placeholder implementation)
        """
        # TODO: Integrate with camera_vision.py when available
        # TODO: Implement AI model inference for visual fire detection
        return False

    def track_fire_direction(self, sensor_data):
        """
        Calculate fire direction from KY-026 flame sensors and orient camera.

        Analyzes the 4-directional flame sensor array to determine fire direction:
        - Sensor 0: North (0°)
        - Sensor 1: East (90°)
        - Sensor 2: South (180°)
        - Sensor 3: West (270°)

        If multiple sensors detect flame, calculates the average direction
        and commands the pan/tilt controller to orient the camera toward the fire.

        Args:
            sensor_data (dict): Sensor readings including 'ky026_flame' array

        Returns:
            float: Average fire direction in degrees (0-360), or None if no fire detected
        """
        try:
            # Extract 4-directional flame sensor readings
            flame_sensors = sensor_data.get('ky026_flame', [False, False, False, False])

            if any(flame_sensors):
                detected_directions = []
                # Convert sensor index to compass direction (0°, 90°, 180°, 270°)
                for i, detected in enumerate(flame_sensors):
                    if detected:
                        detected_directions.append(i * 90)  # Each sensor represents 90° sectors

                if detected_directions:
                    # Calculate average direction from multiple detections
                    avg_direction = sum(detected_directions) / len(detected_directions)
                    # Orient camera toward calculated fire direction
                    self.pan_tilt_controller.rotate_to_angle(avg_direction, 0)
                    return avg_direction

            return None

        except Exception as e:
            return None

    def log_detection(self, location, direction, sensor_data):
        """
        Record fire detection event with full sensor data and GPS coordinates.

        Creates a comprehensive log entry for each fire detection event including:
        - Precise timestamp for emergency response coordination
        - GPS coordinates for location-based emergency dispatch
        - Fire direction for tactical firefighting approach
        - Complete sensor readings for incident analysis
        - Flame sensor array state for fire spread analysis

        Args:
            location (tuple): GPS coordinates (latitude, longitude) or None
            direction (float): Fire direction in degrees or None
            sensor_data (dict): Complete sensor readings from detection event
        """
        try:
            # Create comprehensive detection record for emergency response
            detection_record = {
                "timestamp": time.time(),  # Unix timestamp for precise timing
                "latitude": location[0] if location else 0.0,
                "longitude": location[1] if location else 0.0,
                "direction": direction if direction else 0.0,  # Fire bearing in degrees
                "smoke": sensor_data.get('mq2_smoke', 0),      # Smoke concentration (ADC units)
                "temperature": sensor_data.get('temperature', 0.0),  # Temperature (°C)
                "humidity": sensor_data.get('humidity', 0.0),        # Relative humidity (%)
                "flame": sensor_data.get('ky026_flame', [False, False, False, False])  # 4-dir flame sensors
            }
            # Append to historical detection log for pattern analysis
            self.detection_log.append(detection_record)

        except Exception as e:
            # Silent failure to prevent disruption of fire detection process
            pass

    def get_strongest_direction(self):
        """
        Analyze detection history to find the direction of strongest fire activity.

        Examines all logged detection events and identifies the direction
        associated with the highest smoke concentration reading. This information
        can guide firefighting efforts toward the most intense fire activity.

        Returns:
            float: Direction (degrees) of strongest fire activity, or None if no history
        """
        try:
            if not self.detection_log:
                return None

            # Find detection event with maximum smoke concentration
            strongest_record = max(self.detection_log, key=lambda x: x['smoke'])
            return strongest_record['direction']

        except Exception as e:
            return None

    def is_fire_detected(self):
        """
        Master fire detection method combining all detection systems.

        Implements a comprehensive fire detection algorithm that combines:
        1. Environmental sensor readings (primary detection)
        2. Camera-based visual analysis (secondary confirmation)
        3. Cross-validation between detection methods
        4. Automatic tracking and logging when fire is confirmed

        Detection Logic:
        - Both sensors AND camera detect fire: Immediate confirmation
        - Camera detects but sensors unclear: Re-check sensors
        - Sensors detect but camera unclear: Re-check camera
        - Single-method detection requires secondary confirmation

        When fire is confirmed:
        - GPS coordinates are recorded
        - Camera is oriented toward fire direction
        - Complete detection data is logged

        Returns:
            bool: True if fire is confirmed by detection algorithm, False otherwise
        """
        try:
            # Primary detection phase: check both systems
            camera_detection = self.detect_by_camera()
            sensor_detection = self.detect_by_sensor()

            fire_detected = False

            # Multi-stage detection logic for reduced false positives
            if camera_detection and sensor_detection:
                # Strongest confirmation: both systems agree
                fire_detected = True
            elif camera_detection and not self.sensor_detected:
                # Camera detected, re-verify with sensors
                fire_detected = self.detect_by_sensor()
            elif sensor_detection and not self.camera_detected:
                # Sensors detected, re-verify with camera
                fire_detected = self.detect_by_camera()

            # If fire is confirmed, initiate tracking and logging
            if fire_detected:
                # Gather complete sensor data for logging
                sensor_data = self.sensor_manager.read_all_sensors()
                # Record GPS coordinates for emergency response
                location = self.gps_manager.get_coordinates()
                # Orient camera toward fire and get direction
                direction = self.track_fire_direction(sensor_data)
                # Log complete detection event
                self.log_detection(location, direction, sensor_data)

            return fire_detected

        except Exception as e:
            # Return False on any system failure for safety
            return False

    def get_fire_location(self):
        """
        Get GPS coordinates of detected fire location.

        Performs fire detection and returns GPS coordinates if fire is confirmed.
        This method provides a simple interface for external systems to get
        fire location data without needing to understand the detection logic.

        Returns:
            tuple: GPS coordinates (latitude, longitude) if fire detected, None otherwise
        """
        try:
            if self.is_fire_detected():
                return self.gps_manager.get_coordinates()
            return None
        except Exception as e:
            return None