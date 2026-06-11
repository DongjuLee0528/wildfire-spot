"""
Pan-Tilt Camera Controller Module

This module provides camera pan and tilt control functionality for surveillance
and tracking applications. It manages servo-controlled camera movement with
safety limits and predefined scanning patterns.

Classes:
    PanTiltController: Camera positioning controller with pan/tilt capabilities

Features:
    - Horizontal pan and vertical tilt control
    - Angle safety limits and validation
    - Automated scanning patterns
    - Camera centering and reset functionality
    - Error handling for servo failures

Dependencies:
    - Servo controller for motor control
    - Configuration module for angle limits
"""

from utils.config import *
from hardware.servo_controller import Controllers
import time

class PanTiltController:
    """
    Pan-tilt camera controller for servo-driven camera positioning.

    Provides high-level interface for camera movement control including
    horizontal panning, vertical tilting, scanning patterns, and positioning.

    Attributes:
        _controller: Reference to servo controller for camera movement
    """

    def __init__(self, controller):
        """
        Initialize pan-tilt controller.

        Args:
            controller: Servo controller instance for camera servo control
        """
        self._controller = controller

    def pan(self, speed):
        """
        Control horizontal camera panning.

        Args:
            speed (float): Pan angle in degrees (0-180)
        """
        try:
            # Apply safety limits to prevent servo damage
            if speed < SERVO_ANGLE_MIN:
                speed = SERVO_ANGLE_MIN
            if speed > SERVO_ANGLE_MAX:
                speed = SERVO_ANGLE_MAX
            self._controller.set_camera_pan(speed)
        except Exception as e:
            print(f"Pan control failed: {e}")

    def tilt(self, angle):
        """
        Control vertical camera tilting.

        Args:
            angle (float): Tilt angle in degrees (0-180)
        """
        try:
            # Apply safety limits to prevent servo damage
            if angle < SERVO_ANGLE_MIN:
                angle = SERVO_ANGLE_MIN
            if angle > SERVO_ANGLE_MAX:
                angle = SERVO_ANGLE_MAX
            self._controller.set_camera_tilt(angle)
        except Exception as e:
            print(f"Tilt control failed: {e}")

    def center(self):
        """
        Center camera to default position.

        Sets both pan and tilt servos to center angle for neutral position.
        """
        self._controller.set_camera_pan(CAMERA_CENTER_ANGLE)
        self._controller.set_camera_tilt(CAMERA_CENTER_ANGLE)

    def scan(self):
        """
        Execute automated scanning pattern.

        Performs left-center-right-center scanning sequence with configured
        timing delays for surveillance or area monitoring.
        """
        # Pan left and pause
        self._controller.set_camera_pan(CAMERA_SCAN_ANGLES[0])
        time.sleep(TIME_SLEEP_SCAN[0])

        # Return to center and pause
        self._controller.set_camera_pan(CAMERA_CENTER_ANGLE)
        time.sleep(TIME_SLEEP_SCAN[1])

        # Pan right and pause
        self._controller.set_camera_pan(CAMERA_SCAN_ANGLES[1])
        time.sleep(TIME_SLEEP_SCAN[0])

        # Return to center and pause
        self._controller.set_camera_pan(CAMERA_CENTER_ANGLE)
        time.sleep(TIME_SLEEP_SCAN[1])

        # Final center position
        self.center()

    def rotate_to_angle(self, pan_speed, tilt_angle):
        """
        Position camera to specific pan and tilt angles simultaneously.

        Args:
            pan_speed (float): Pan angle in degrees
            tilt_angle (float): Tilt angle in degrees
        """
        try:
            # Apply safety limits to tilt angle
            if tilt_angle < SERVO_ANGLE_MIN:
                tilt_angle = SERVO_ANGLE_MIN
            if tilt_angle > SERVO_ANGLE_MAX:
                tilt_angle = SERVO_ANGLE_MAX

            # Set both pan and tilt positions
            self.pan(pan_speed)
            self.tilt(tilt_angle)
        except Exception as e:
            print(f"Rotate to angle failed: {e}")

    def reset(self):
        """
        Reset camera to center position.

        Alias for center() method to restore default camera position.
        """
        self.center()