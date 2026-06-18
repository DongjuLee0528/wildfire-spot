"""
Wildfire detection system logging module.

Provides centralized logging functionality for the wildfire robot,
including file and console handlers, structured log formatting,
and specialized logging methods for fire detection events.
"""

import logging
import os
from datetime import datetime
from utils.config import LOG_DIR

class WildfireLogger:
    """
    Centralized logger for the wildfire detection robot system.

    Handles logging to both file and console with different severity levels.
    Creates daily log files with timestamps and provides specialized methods
    for logging fire detection events, sensor values, GPS locations, and system states.
    """

    def __init__(self, module_name):
        """
        Initialize the logger for a specific module.

        Args:
            module_name: Name of the module using this logger

        Sets up both file and console handlers with appropriate log levels.
        File handler logs DEBUG and above, console logs INFO and above.
        """
        self.logger = logging.getLogger(module_name)
        self.logger.setLevel(logging.DEBUG)
        self.file_handler = None
        self.console_handler = None

        # Only initialize handlers once to avoid duplicate log entries
        if not self.logger.handlers:
            try:
                os.makedirs(LOG_DIR, exist_ok=True)
            except OSError as e:
                print(f"Failed to create log directory {LOG_DIR}: {e}")
                return

            # Create daily log file with timestamp
            log_filename = datetime.now().strftime("wildfire_%Y%m%d.log")
            log_filepath = os.path.join(LOG_DIR, log_filename)

            try:
                self.file_handler = logging.FileHandler(log_filepath)
                self.file_handler.setLevel(logging.DEBUG)
            except (PermissionError, OSError) as e:
                print(f"Failed to create file handler for {log_filepath}: {e}")
                self.file_handler = None

            # Console handler for real-time monitoring (INFO level and above)
            self.console_handler = logging.StreamHandler()
            self.console_handler.setLevel(logging.INFO)

            # Consistent log format across all handlers
            formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

            if self.file_handler:
                self.file_handler.setFormatter(formatter)
                self.logger.addHandler(self.file_handler)

            self.console_handler.setFormatter(formatter)
            self.logger.addHandler(self.console_handler)

    def debug(self, message):
        """Log a debug-level message (detailed diagnostic information)."""
        self.logger.debug(message)

    def info(self, message):
        """Log an info-level message (general informational events)."""
        self.logger.info(message)

    def warning(self, message):
        """Log a warning-level message (potentially harmful situations)."""
        self.logger.warning(message)

    def error(self, message):
        """Log an error-level message (error events that might still allow operation)."""
        self.logger.error(message)

    def log_fire_detected(self, location, sensor_data, direction):
        """
        Log a fire detection event with full context.

        Args:
            location: GPS coordinates (latitude, longitude) or None
            sensor_data: Dictionary containing sensor readings
            direction: Direction angle where fire was detected

        Logs as WARNING level for immediate attention.
        """
        try:
            # Extract GPS coordinates with safe fallback
            latitude = location[0] if (location and len(location) >= 2) else 0.0
            longitude = location[1] if (location and len(location) >= 2) else 0.0

            # Extract all sensor values with defaults
            smoke = sensor_data.get('smoke', 0) if sensor_data else 0
            temperature = sensor_data.get('temperature', 0.0) if sensor_data else 0.0
            humidity = sensor_data.get('humidity', 0.0) if sensor_data else 0.0
            flame = sensor_data.get('flame', []) if sensor_data else []
            direction_val = direction if direction is not None else 0.0

            message = f"FIRE_DETECTED | Location: ({latitude:.6f}, {longitude:.6f}) | Direction: {direction_val:.1f} | Smoke: {smoke} | Temp: {temperature:.1f}C | Humidity: {humidity:.1f}% | Flame: {flame}"
            self.logger.warning(message)
        except (ValueError, TypeError, KeyError) as e:
            self.logger.error(f"Failed to log fire detected: {e}")

    def log_sensor_values(self, sensor_data):
        """
        Log current sensor readings for monitoring and debugging.

        Args:
            sensor_data: Dictionary containing all sensor readings

        Logs as DEBUG level to avoid cluttering console output.
        """
        try:
            smoke = sensor_data.get('smoke', 0) if sensor_data else 0
            temperature = sensor_data.get('temperature', 0.0) if sensor_data else 0.0
            humidity = sensor_data.get('humidity', 0.0) if sensor_data else 0.0
            flame = sensor_data.get('flame', []) if sensor_data else []
            distance = sensor_data.get('distance', 0.0) if sensor_data else 0.0

            message = f"SENSOR_VALUES | Smoke: {smoke} | Temp: {temperature:.1f}C | Humidity: {humidity:.1f}% | Flame: {flame} | Distance: {distance:.2f}cm"
            self.logger.debug(message)
        except (ValueError, TypeError, KeyError) as e:
            self.logger.error(f"Failed to log sensor values: {e}")

    def log_system_state(self, state):
        """
        Log robot state machine transitions.

        Args:
            state: Current state or state transition (e.g., "IDLE" or "IDLE -> PATROLLING")

        Logs as INFO level for operational tracking.
        """
        try:
            message = f"SYSTEM_STATE | State: {state}"
            self.logger.info(message)
        except (ValueError, TypeError) as e:
            self.logger.error(f"Failed to log system state: {e}")

    def log_gps_location(self, location):
        """
        Log GPS coordinates for robot position tracking.

        Args:
            location: Tuple of (latitude, longitude)

        Logs as DEBUG level since GPS is frequently updated.
        """
        try:
            latitude = location[0] if (location and len(location) >= 2) else 0.0
            longitude = location[1] if (location and len(location) >= 2) else 0.0

            message = f"GPS_LOCATION | Latitude: {latitude:.6f} | Longitude: {longitude:.6f}"
            self.logger.debug(message)
        except (ValueError, TypeError, IndexError) as e:
            self.logger.error(f"Failed to log GPS location: {e}")

    def log_error(self, module, error):
        """
        Log module-specific errors with context.

        Args:
            module: Module or function name where error occurred
            error: Error message or exception details

        Provides structured error logging for easier debugging.
        """
        try:
            message = f"ERROR | Module: {module} | Error: {error}"
            self.logger.error(message)
        except (ValueError, TypeError) as e:
            self.logger.error(f"Failed to log error: {e}")

    def close(self):
        """
        Cleanly close all logging handlers.

        Should be called during system shutdown to ensure
        all log entries are flushed and file handles are released.
        """
        try:
            if self.file_handler:
                self.file_handler.close()
                self.logger.removeHandler(self.file_handler)
            if self.console_handler:
                self.console_handler.close()
                self.logger.removeHandler(self.console_handler)
        except (ValueError, RuntimeError) as e:
            print(f"Error closing logger handlers: {e}")
