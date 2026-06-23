"""
LIDAR sensor management for obstacle detection and avoidance.

Processes 360-degree scanning LIDAR data for:
- Obstacle detection in multiple directions
- Path clearance verification
- VFH (Vector Field Histogram) based navigation
"""

import time
from utils.config import (LIDAR_UART_PORT, LIDAR_BAUDRATE, LIDAR_OBSTACLE_THRESHOLD,
                         LIDAR_DIRECTION_ANGLES, LIDAR_DATA_SIZE, LIDAR_PACKET_HEADER,
                         LIDAR_FULL_SCAN_SIZE, LIDAR_DIRECTION_COUNT, LIDAR_ANGLE_RANGE,
	                         LIDAR_REVERSE_DIRECTION, LIDAR_PATH_CHECK_RANGE, LIDAR_READ_TIMEOUT)

try:
    import serial
    SERIAL_EXCEPTIONS = (OSError, serial.SerialException)
except ImportError:
    serial = None
    SERIAL_EXCEPTIONS = (OSError,)
SERIAL_READ_EXCEPTIONS = SERIAL_EXCEPTIONS + (IndexError, ValueError)

class LidarManager:
    """
    Manages LIDAR sensor for obstacle detection and navigation.

    Reads 360-degree scan data and provides methods for:
    - Multi-directional obstacle detection
    - Safe path finding (VFH algorithm)
    - Path clearance verification
    """

    def __init__(self):
        """
        Initialize LIDAR serial connection.

        Attempts to connect to LIDAR sensor via UART.
        If connection fails, LIDAR remains unavailable but system continues.
        """
        if serial is None:
            print("LIDAR serial module is not available")
            self.serial_port = None
            self._available = False
            self.obstacle_threshold = LIDAR_OBSTACLE_THRESHOLD
            self.directions = LIDAR_DIRECTION_ANGLES
            return

        try:
            self.serial_port = serial.Serial(LIDAR_UART_PORT, LIDAR_BAUDRATE, timeout=1)
            self._available = True
        except SERIAL_EXCEPTIONS:
            self.serial_port = None
            self._available = False
        self.obstacle_threshold = LIDAR_OBSTACLE_THRESHOLD
        self.directions = LIDAR_DIRECTION_ANGLES

    def _angle_in_range(self, angle, target_angle, angle_range):
        diff = abs((angle - target_angle + 180) % 360 - 180)
        return diff <= angle_range

    def read_scan(self):
        """
        Read a full 360-degree LIDAR scan.

        Returns:
            Dictionary mapping angles (0-359) to distances in millimeters
            Empty dict if LIDAR unavailable or read fails

        Reads LIDAR data packets until a complete scan is obtained.
        Each packet contains 12 distance measurements at 0.5-degree increments.
        """
        if not self._available or self.serial_port is None:
            return {}
        try:
            distance_data = {}
            start_time = time.time()
            while True:
                # Timeout protection to prevent infinite loops
                if time.time() - start_time > LIDAR_READ_TIMEOUT:
                    break

                data = self.serial_port.read(LIDAR_DATA_SIZE)

                # Verify packet header and size
                if len(data) == LIDAR_DATA_SIZE and data[0] == LIDAR_PACKET_HEADER[0] and data[1] == LIDAR_PACKET_HEADER[1]:
                    # Extract starting angle from packet (in 0.01 degree units)
                    angle = ((data[4] | (data[5] << 8)) / 100.0) % 360

                    # Each packet contains 12 distance measurements
                    for i in range(12):
                        # Distance in millimeters (16-bit value)
                        point_distance = data[6 + 3*i] | (data[7 + 3*i] << 8)
                        # Calculate angle for this measurement point
                        point_angle = (angle + i * 0.5) % 360
                        if point_distance > 0:
                            distance_data[point_angle] = point_distance

                    # Stop when we have enough data points for a full scan
                    if len(distance_data) >= LIDAR_FULL_SCAN_SIZE:
                        break
            return distance_data
        except SERIAL_READ_EXCEPTIONS:
            return {}

    def get_obstacle_direction(self):
        """
        Detect obstacles in predefined directions.

        Returns:
            List of boolean values, one per configured direction
            True indicates obstacle detected within threshold distance

        Checks configured directions (typically 8: N, NE, E, SE, S, SW, W, NW)
        and reports if any obstacles are closer than the threshold.
        """
        scan_data = self.read_scan()
        if not scan_data:
            return [False] * LIDAR_DIRECTION_COUNT

        obstacles = [False] * LIDAR_DIRECTION_COUNT
        for i, direction in enumerate(self.directions):
            min_distance = float('inf')

            # Check all angles within the range for this direction
            for angle, distance in scan_data.items():
                if self._angle_in_range(angle, direction, LIDAR_ANGLE_RANGE):
                    min_distance = min(min_distance, distance)

            # Mark as obstacle if closest point is within threshold
            if min_distance <= self.obstacle_threshold:
                obstacles[i] = True

        return obstacles

    def vfh_avoid(self):
        """
        Vector Field Histogram obstacle avoidance algorithm.

        Returns:
            Recommended heading angle (0-359 degrees) to avoid obstacles
            Returns LIDAR_REVERSE_DIRECTION if all directions blocked

        Algorithm:
        1. Identify all clear (obstacle-free) directions
        2. If all blocked, recommend reversing
        3. Prefer forward (0 degrees) if clear
        4. Otherwise, choose clear direction closest to forward
        """
        obstacles = self.get_obstacle_direction()

        # Find all directions without obstacles
        clear_directions = []
        for i, is_obstacle in enumerate(obstacles):
            if not is_obstacle:
                clear_directions.append(self.directions[i])

        # If completely surrounded, recommend reverse
        if not clear_directions:
            return LIDAR_REVERSE_DIRECTION

        # Prefer moving straight forward if possible
        if 0 in clear_directions:
            return 0

        # Choose clear direction closest to forward (0 degrees)
        min_diff = float('inf')
        best_direction = clear_directions[0]
        for direction in clear_directions:
            # Handle wraparound (359 degrees is close to 0)
            diff = min(abs(direction - 0), abs(direction - 360))
            if diff < min_diff:
                min_diff = diff
                best_direction = direction

        return best_direction

    def is_path_clear(self, direction_deg, threshold_mm):
        """
        Check if a specific direction has a clear path.

        Args:
            direction_deg: Direction to check (0-359 degrees)
            threshold_mm: Minimum clearance distance in millimeters

        Returns:
            True if path is clear beyond threshold distance
            False if obstacle detected or LIDAR unavailable

        Checks a narrow angle range around the specified direction.
        """
        scan_data = self.read_scan()
        if not scan_data:
            return False

        min_distance = float('inf')
        # Check angles within LIDAR_PATH_CHECK_RANGE of target direction
        for angle, distance in scan_data.items():
            if self._angle_in_range(angle, direction_deg, LIDAR_PATH_CHECK_RANGE):
                min_distance = min(min_distance, distance)

        return min_distance > threshold_mm

    def close(self):
        """
        Close LIDAR serial connection.

        Releases the serial port. Should be called during system shutdown.
        """
        if self._available and self.serial_port is not None:
            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
                self._available = False
            except SERIAL_EXCEPTIONS as e:
                print(f"LIDAR close failed: {type(e).__name__}: {e}")
