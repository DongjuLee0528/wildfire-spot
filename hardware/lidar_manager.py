"""
LIDAR sensor management for obstacle detection and avoidance.

Processes 360-degree scanning LIDAR data for:
- Obstacle detection in multiple directions
- Path clearance verification
- VFH (Vector Field Histogram) based navigation

Transport: Unitree L2 LiDAR via Ethernet UDP
"""

import math
import socket
import struct
import time
from utils.config import (LIDAR_ETHERNET_RX_PORT, LIDAR_SOCKET_TIMEOUT, LIDAR_OBSTACLE_THRESHOLD,
                          LIDAR_DIRECTION_ANGLES, LIDAR_FULL_SCAN_SIZE,
                          LIDAR_DIRECTION_COUNT, LIDAR_ANGLE_RANGE,
                          LIDAR_REVERSE_DIRECTION, LIDAR_PATH_CHECK_RANGE,
                          LIDAR_READ_TIMEOUT)
from utils.logger import WildfireLogger

_UDP_BUFFER_SIZE = 65535


class LidarManager:
    """
    Manages LIDAR sensor for obstacle detection and navigation.

    Reads 360-degree scan data via Ethernet UDP and provides methods for:
    - Multi-directional obstacle detection
    - Safe path finding (VFH algorithm)
    - Path clearance verification
    """

    def __init__(self):
        """
        Initialize the UDP socket for receiving LIDAR scan data.

        Binds to LIDAR_ETHERNET_RX_PORT on all interfaces. If the socket
        cannot be opened (e.g. port in use, permission denied), the manager
        stays in an unavailable state and all methods return safe defaults.
        """
        self.logger = WildfireLogger("LidarManager")
        self._socket = None
        self._available = False
        self.obstacle_threshold = LIDAR_OBSTACLE_THRESHOLD
        self.directions = LIDAR_DIRECTION_ANGLES

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind(("", LIDAR_ETHERNET_RX_PORT))
            self._socket.settimeout(LIDAR_SOCKET_TIMEOUT)
            self._available = True
        except OSError as e:
            self.logger.log_error("LidarManager.__init__", str(e))
            if self._socket is not None:
                try:
                    self._socket.close()
                except OSError:
                    pass
            self._socket = None
            self._available = False

    def _angle_in_range(self, angle, target_angle, angle_range):
        """Return True if angle is within angle_range degrees of target_angle (wraps at 360)."""
        diff = abs((angle - target_angle + 180) % 360 - 180)
        return diff <= angle_range

    def _parse_udp_packet(self, data: bytes) -> dict:
        """Parse a raw UDP packet from the LIDAR into an {angle: distance_mm} dict.

        Packet layout (all little-endian unless noted):
          data[0:4]   magic (uint32, must be 0x55AA050A)
          data[4:8]   packet_type (uint32, must be 102)
          data[8:12]  packet_size (uint32)
          data[112:116] h_angle_start (float32, degrees)
          data[120:124] h_step (float32, radians)
          data[128:132] point_num (uint32, ≤ 300)
          data[132:732] ranges: 300 × uint16 (distance in mm, 0 = invalid)
        """
        _MAGIC = 0x0A05AA55
        _PACKET_TYPE = 102
        _MIN_SIZE = 1044
        _H_ANGLE_START_OFFSET = 112
        _H_STEP_OFFSET = 120
        _POINT_NUM_OFFSET = 128
        _RANGES_OFFSET = 132
        _MAX_POINTS = 300

        try:
            if not data:
                return {}

            if len(data) < _MIN_SIZE:
                return {}

            magic, packet_type, _ = struct.unpack_from("<III", data, 0)
            if magic != _MAGIC or packet_type != _PACKET_TYPE:
                return {}

            (h_angle_start,) = struct.unpack_from("<f", data, _H_ANGLE_START_OFFSET)
            (h_step_rad,) = struct.unpack_from("<f", data, _H_STEP_OFFSET)

            if h_step_rad == 0.0:
                return {}

            h_angle_step = math.degrees(h_step_rad)

            (point_num,) = struct.unpack_from("<I", data, _POINT_NUM_OFFSET)
            point_num = min(point_num, _MAX_POINTS)

            ranges = struct.unpack_from(f"<{_MAX_POINTS}H", data, _RANGES_OFFSET)

            result = {}
            for i in range(point_num):
                distance_mm = ranges[i]
                if distance_mm == 0:
                    continue
                angle_raw = h_angle_start + i * h_angle_step
                angle_deg = int(angle_raw % 360)
                if angle_deg < 0:
                    angle_deg += 360
                result[angle_deg] = distance_mm

            return result

        except Exception as e:
            self.logger.log_error("LidarManager._parse_udp_packet", str(e))
            return {}

    def read_scan(self) -> dict:
        """
        Collect a full 360-degree scan from the LIDAR via UDP.

        Receives UDP packets until a socket timeout occurs or LIDAR_READ_TIMEOUT
        seconds have elapsed. Each packet is parsed into angle→distance_mm pairs
        and merged into a single scan dict.

        Returns:
            dict mapping angle (int, 0-359) to distance in mm.
            Empty dict if the socket is unavailable or no packets arrive.
        """

        if not self._available or self._socket is None:
            return {}

        scan_data = {}
        start_time = time.time()

        try:
            while True:
                if time.time() - start_time > LIDAR_READ_TIMEOUT:
                    break

                try:
                    data, _ = self._socket.recvfrom(_UDP_BUFFER_SIZE)
                except socket.timeout:
                    break

                if not data:
                    continue

                parsed = self._parse_udp_packet(data)
                if parsed:
                    scan_data.update(parsed)

        except OSError as e:
            self.logger.log_error("LidarManager.read_scan", str(e))

        return scan_data

    def get_obstacle_direction(self) -> list:
        """
        Determine which of the 8 cardinal/intercardinal directions contain obstacles.

        For each direction in LIDAR_DIRECTION_ANGLES, takes the minimum distance from
        all scan points within LIDAR_ANGLE_RANGE degrees of that heading and flags the
        direction as blocked if that minimum is at or below the obstacle threshold.

        Returns:
            List of 8 booleans aligned with LIDAR_DIRECTION_ANGLES.
            True means an obstacle was detected in that direction.
            All-False list is returned if no scan data is available.
        """

        scan_data = self.read_scan()
        if not scan_data:
            return [False] * LIDAR_DIRECTION_COUNT

        obstacles = [False] * LIDAR_DIRECTION_COUNT
        for i, direction in enumerate(self.directions):
            min_distance = float('inf')
            for angle, distance in scan_data.items():
                try:
                    if self._angle_in_range(angle, direction, LIDAR_ANGLE_RANGE):
                        min_distance = min(min_distance, distance)
                except Exception as e:
                    self.logger.log_error("LidarManager.get_obstacle_direction", str(e))
            if min_distance <= self.obstacle_threshold:
                obstacles[i] = True

        return obstacles

    def vfh_avoid(self) -> int:
        """
        Choose a safe heading using a simplified Vector Field Histogram (VFH) strategy.

        Algorithm:
        1. Classify each of the 8 directions as clear or blocked via get_obstacle_direction().
        2. If forward (0°) is clear, return 0 immediately.
        3. Among all clear directions, pick the one whose angular distance to 0° is smallest.
        4. If every direction is blocked, return LIDAR_REVERSE_DIRECTION (180°) to reverse.

        Returns:
            Heading in degrees (one of LIDAR_DIRECTION_ANGLES, or LIDAR_REVERSE_DIRECTION).
        """

        obstacles = self.get_obstacle_direction()

        clear_directions = []
        for i, is_obstacle in enumerate(obstacles):
            if not is_obstacle:
                clear_directions.append(self.directions[i])

        if not clear_directions:
            return LIDAR_REVERSE_DIRECTION

        if 0 in clear_directions:
            return 0

        min_diff = float('inf')
        best_direction = clear_directions[0]
        for direction in clear_directions:
            diff = min(abs(direction - 0), abs(direction - 360))
            if diff < min_diff:
                min_diff = diff
                best_direction = direction

        return best_direction

    def is_path_clear(self, direction_deg, threshold_mm) -> bool:
        """
        Check whether a specific heading is free of obstacles.

        Reads a fresh scan and examines all points within LIDAR_PATH_CHECK_RANGE
        degrees of direction_deg. The path is considered clear only if the closest
        point in that cone is farther than threshold_mm.

        Args:
            direction_deg: Heading to check in degrees (0-359).
            threshold_mm: Minimum acceptable clearance distance in mm.

        Returns:
            True if the path is clear beyond threshold_mm, False otherwise.
            Also returns False when no scan data is available.
        """

        scan_data = self.read_scan()
        if not scan_data:
            return False

        min_distance = float('inf')
        for angle, distance in scan_data.items():
            try:
                if self._angle_in_range(angle, direction_deg, LIDAR_PATH_CHECK_RANGE):
                    min_distance = min(min_distance, distance)
            except Exception as e:
                self.logger.log_error("LidarManager.is_path_clear", str(e))

        if min_distance == float('inf'):
            return False

        return min_distance > threshold_mm

    def is_available(self) -> bool:
        """Return True if the UDP socket opened successfully and LIDAR data can be received."""
        return self._available

    def close(self):
        """Close the UDP socket and mark the manager as unavailable."""
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError as e:
                self.logger.log_error("LidarManager.close", str(e))
            finally:
                self._socket = None
                self._available = False
