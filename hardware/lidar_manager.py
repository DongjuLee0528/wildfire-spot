import serial
import time
from utils.config import (LIDAR_UART_PORT, LIDAR_BAUDRATE, LIDAR_OBSTACLE_THRESHOLD,
                         LIDAR_DIRECTION_ANGLES, LIDAR_DATA_SIZE, LIDAR_PACKET_HEADER,
                         LIDAR_FULL_SCAN_SIZE, LIDAR_DIRECTION_COUNT, LIDAR_ANGLE_RANGE,
                         LIDAR_REVERSE_DIRECTION, LIDAR_PATH_CHECK_RANGE, LIDAR_READ_TIMEOUT)

class LidarManager:

    def __init__(self):
        try:
            self.serial_port = serial.Serial(LIDAR_UART_PORT, LIDAR_BAUDRATE, timeout=1)
            self._available = True
        except (OSError, serial.SerialException):
            self.serial_port = None
            self._available = False
        self.obstacle_threshold = LIDAR_OBSTACLE_THRESHOLD
        self.directions = LIDAR_DIRECTION_ANGLES

    def read_scan(self):
        if not self._available or self.serial_port is None:
            return {}
        try:
            distance_data = {}
            start_time = time.time()
            while True:
                if time.time() - start_time > LIDAR_READ_TIMEOUT:
                    break

                data = self.serial_port.read(LIDAR_DATA_SIZE)

                if len(data) == LIDAR_DATA_SIZE and data[0] == LIDAR_PACKET_HEADER[0] and data[1] == LIDAR_PACKET_HEADER[1]:
                    angle = ((data[4] | (data[5] << 8)) / 100.0) % 360

                    for i in range(12):
                        point_distance = data[6 + 3*i] | (data[7 + 3*i] << 8)
                        point_angle = (angle + i * 0.5) % 360
                        if point_distance > 0:
                            distance_data[point_angle] = point_distance

                    if len(distance_data) >= LIDAR_FULL_SCAN_SIZE:
                        break
            return distance_data
        except (serial.SerialException, IndexError, ValueError):
            return {}

    def get_obstacle_direction(self):
        scan_data = self.read_scan()
        if not scan_data:
            return [False] * LIDAR_DIRECTION_COUNT

        obstacles = [False] * LIDAR_DIRECTION_COUNT
        for i, direction in enumerate(self.directions):
            min_distance = float('inf')

            for angle in range(direction - LIDAR_ANGLE_RANGE, direction + LIDAR_ANGLE_RANGE + 1):
                normalized_angle = angle % 360
                if normalized_angle in scan_data:
                    min_distance = min(min_distance, scan_data[normalized_angle])

            if min_distance <= self.obstacle_threshold:
                obstacles[i] = True

        return obstacles

    def vfh_avoid(self):
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

    def is_path_clear(self, direction_deg, threshold_mm):
        scan_data = self.read_scan()
        if not scan_data:
            return False

        min_distance = float('inf')
        for angle in range(direction_deg - LIDAR_PATH_CHECK_RANGE, direction_deg + LIDAR_PATH_CHECK_RANGE + 1):
            normalized_angle = angle % 360
            if normalized_angle in scan_data:
                min_distance = min(min_distance, scan_data[normalized_angle])

        return min_distance > threshold_mm

    def close(self):
        if self._available and self.serial_port is not None:
            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
                self._available = False
            except (OSError, serial.SerialException) as e:
                pass