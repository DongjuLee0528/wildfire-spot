"""
LiDAR Manager Module for Obstacle Detection and Navigation

This module provides LiDAR sensor management for 360-degree distance measurement
and obstacle avoidance. It implements Vector Field Histogram (VFH) algorithm
for path planning and provides directional obstacle detection capabilities.

Classes:
    LidarManager: Interface for LiDAR sensor data processing and obstacle avoidance

Features:
    - 360-degree distance scanning
    - Directional obstacle detection
    - VFH-based path planning algorithm
    - Path clearance verification
    - Serial communication with LiDAR sensor

Dependencies:
    - Serial communication for LiDAR data
    - Mathematical calculations for angle normalization
"""

import serial
import math
import numpy as np
from utils.config import *

class LidarManager:
    """
    LiDAR sensor management class for obstacle detection and navigation.

    Handles serial communication with LiDAR sensor, processes distance measurements,
    and implements obstacle avoidance algorithms including VFH (Vector Field Histogram).

    Attributes:
        serial_port: Serial connection to LiDAR sensor
        obstacle_threshold (int): Distance threshold for obstacle detection (mm)
        directions (list): Angular directions for directional obstacle detection
    """

    def __init__(self):
        """Initialize LiDAR manager with serial communication and detection parameters."""
        # Establish serial communication with LiDAR sensor
        self.serial_port = serial.Serial(LIDAR_UART_PORT, LIDAR_BAUDRATE, timeout=1)

        # Set obstacle detection threshold distance
        self.obstacle_threshold = LIDAR_OBSTACLE_THRESHOLD

        # Define direction angles for 8-directional obstacle detection
        self.directions = LIDAR_DIRECTION_ANGLES

    def read_scan(self):
        """
        Read complete 360-degree scan data from LiDAR sensor.

        Processes LiDAR data packets and builds a dictionary of angle-distance pairs.
        Each packet contains 12 measurement points with 0.5-degree angular resolution.

        Returns:
            dict: Distance measurements keyed by angle {angle: distance_mm}
                Empty dict if scan fails or no data available
        """
        try:
            distance_data = {}
            while True:
                # Read one data packet from LiDAR
                data = self.serial_port.read(LIDAR_DATA_SIZE)

                # Validate packet header and size
                if len(data) == LIDAR_DATA_SIZE and data[0] == LIDAR_PACKET_HEADER[0] and data[1] == LIDAR_PACKET_HEADER[1]:
                    # Extract starting angle from packet (in degrees * 100)
                    angle = (data[4] | (data[5] << 8)) / 100.0

                    # Process 12 measurement points in this packet
                    for i in range(12):
                        # Extract distance value (16-bit little endian)
                        point_distance = data[6 + 3*i] | (data[7 + 3*i] << 8)
                        # Calculate absolute angle for this point (0.5-degree increments)
                        point_angle = angle + i * 0.5
                        # Store valid distance measurements only
                        if point_distance > 0:
                            distance_data[point_angle] = point_distance

                    # Stop when we have enough data for full scan
                    if len(distance_data) >= LIDAR_FULL_SCAN_SIZE:
                        break
            return distance_data
        except Exception as e:
            return {}

    def get_obstacle_direction(self):
        """
        Detect obstacles in 8 cardinal and intercardinal directions.

        Analyzes LiDAR scan data to determine obstacle presence in predefined
        angular sectors around the robot. Each direction covers a range of angles.

        Returns:
            list: Boolean list indicating obstacle presence in each direction
                [N, NE, E, SE, S, SW, W, NW] where True = obstacle detected
                Returns [False] * 8 if scan data unavailable
        """
        scan_data = self.read_scan()
        if not scan_data:
            return [False] * 8

        obstacles = [False] * LIDAR_DIRECTION_COUNT
        for i, direction in enumerate(self.directions):
            min_distance = float('inf')

            # Check angular range around each direction
            for angle in range(direction - LIDAR_ANGLE_RANGE, direction + LIDAR_ANGLE_RANGE + 1):
                normalized_angle = angle % 360  # Normalize angle to 0-359 range
                if normalized_angle in scan_data:
                    # Find minimum distance in this angular sector
                    min_distance = min(min_distance, scan_data[normalized_angle])

            # Mark as obstacle if minimum distance is below threshold
            if min_distance <= self.obstacle_threshold:
                obstacles[i] = True

        return obstacles

    def vfh_avoid(self):
        """
        Implement Vector Field Histogram (VFH) obstacle avoidance algorithm.

        Analyzes obstacle directions and selects the best clear direction for navigation.
        Prefers forward movement (0 degrees) when possible, otherwise selects the
        clear direction closest to forward.

        Returns:
            int: Best navigation direction in degrees:
                - 0 degrees = forward (preferred)
                - LIDAR_REVERSE_DIRECTION if all directions blocked
                - Closest clear direction to forward otherwise
        """
        obstacles = self.get_obstacle_direction()

        # Find all clear (non-obstacle) directions
        clear_directions = []
        for i, is_obstacle in enumerate(obstacles):
            if not is_obstacle:
                clear_directions.append(self.directions[i])

        # If all directions blocked, reverse
        if not clear_directions:
            return LIDAR_REVERSE_DIRECTION

        # Prefer forward direction (0 degrees) if available
        if 0 in clear_directions:
            return 0

        # Find clear direction closest to forward (0 degrees)
        min_diff = float('inf')
        best_direction = clear_directions[0]
        for direction in clear_directions:
            # Calculate angular difference considering 0/360 wrap-around
            diff = min(abs(direction - 0), abs(direction - 360))
            if diff < min_diff:
                min_diff = diff
                best_direction = direction

        return best_direction

    def is_path_clear(self, direction_deg, threshold_mm):
        """
        Check if a specific path direction is clear of obstacles.

        Verifies that a given angular direction has sufficient clearance
        by checking minimum distance within an angular range.

        Args:
            direction_deg (int): Target direction in degrees (0-359)
            threshold_mm (int): Minimum required clearance distance in millimeters

        Returns:
            bool: True if path is clear (min distance > threshold), False otherwise
                Also returns False if scan data unavailable
        """
        scan_data = self.read_scan()
        if not scan_data:
            return False

        min_distance = float('inf')
        # Check angular range around target direction
        for angle in range(direction_deg - LIDAR_PATH_CHECK_RANGE, direction_deg + LIDAR_PATH_CHECK_RANGE + 1):
            normalized_angle = angle % 360  # Normalize to 0-359 range
            if normalized_angle in scan_data:
                # Track minimum distance in this angular sector
                min_distance = min(min_distance, scan_data[normalized_angle])

        # Path is clear if minimum distance exceeds threshold
        return min_distance > threshold_mm

    def close(self):
        """
        Close serial connection to LiDAR sensor.

        Safely terminates communication with the sensor to free resources.
        """
        if self.serial_port.is_open:
            self.serial_port.close()