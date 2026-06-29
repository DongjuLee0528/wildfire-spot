"""
LIDAR sensor management for obstacle detection and avoidance.

Processes 360-degree scanning LIDAR data for:
- Obstacle detection in multiple directions
- Path clearance verification
- VFH (Vector Field Histogram) based navigation

Transport: Unitree L2 LiDAR via Ethernet UDP
"""

import socket
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
        diff = abs((angle - target_angle + 180) % 360 - 180)
        return diff <= angle_range

    def _parse_udp_packet(self, data: bytes) -> dict:
        try:
            if not data:
                return {}
            return {}
        except Exception as e:
            self.logger.log_error("LidarManager._parse_udp_packet", str(e))
            return {}

    def read_scan(self) -> dict:
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
        return self._available

    def close(self):
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError as e:
                self.logger.log_error("LidarManager.close", str(e))
            finally:
                self._socket = None
                self._available = False
