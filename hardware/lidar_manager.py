import serial
import math
import numpy as np
from utils.config import *

class LidarManager:
    def __init__(self):
        self.serial_port = serial.Serial(LIDAR_UART_PORT, LIDAR_BAUDRATE, timeout=1)
        self.obstacle_threshold = 500
        self.directions = [0, 45, 90, 135, 180, 225, 270, 315]

    def read_scan(self):
        try:
            distance_data = {}
            while True:
                data = self.serial_port.read(42)
                if len(data) == 42 and data[0] == 0xAA and data[1] == 0xAA:
                    angle = (data[4] | (data[5] << 8)) / 100.0
                    for i in range(12):
                        point_distance = data[6 + 3*i] | (data[7 + 3*i] << 8)
                        point_angle = angle + i * 0.5
                        if point_distance > 0:
                            distance_data[point_angle] = point_distance
                    if len(distance_data) >= 360:
                        break
            return distance_data
        except Exception as e:
            return {}

    def get_obstacle_direction(self):
        scan_data = self.read_scan()
        if not scan_data:
            return [False] * 8

        obstacles = [False] * 8
        for i, direction in enumerate(self.directions):
            min_distance = float('inf')
            for angle in range(direction - 22, direction + 23):
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
            return 180

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
        for angle in range(direction_deg - 10, direction_deg + 11):
            normalized_angle = angle % 360
            if normalized_angle in scan_data:
                min_distance = min(min_distance, scan_data[normalized_angle])

        return min_distance > threshold_mm

    def close(self):
        if self.serial_port.is_open:
            self.serial_port.close()