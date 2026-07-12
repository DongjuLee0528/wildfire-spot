"""
GPS management module for location tracking.

Reads GPS coordinates from UART-connected GPS module using NMEA protocol.
Parses GPRMC sentences to extract latitude and longitude.
"""

from utils.config import GPS_UART_PORT, GPS_BAUDRATE, GPS_READ_MAX_ATTEMPTS
from utils.logger import WildfireLogger
import serial
import pynmea2
import time

class GPSManager:
    """
    Manages GPS module communication and coordinate extraction.

    Reads NMEA sentences from serial GPS module and provides
    various methods to retrieve current location in different formats.
    """

    def __init__(self):
        """
        Initialize GPS serial connection.

        Attempts to open serial connection to GPS module.
        If connection fails, GPS remains unavailable but system continues.
        """
        self.logger = WildfireLogger("GPSManager")
        try:
            self._serial = serial.Serial(GPS_UART_PORT, GPS_BAUDRATE, timeout=1)
            self._available = True
        except (OSError, serial.SerialException) as e:
            self.logger.log_error("GPSManager.__init__", str(e))
            self._serial = None
            self._available = False

    def get_location(self):
        """
        Read one NMEA sentence and return coordinates if a valid GPRMC fix is found.

        Reads exactly one line from the serial port. If the line is not a GPRMC
        sentence or the fix status is 'V' (void), returns None without retrying.
        Callers that need a guaranteed reading should use get_current_coordinates().

        Returns:
            Tuple of (latitude, longitude) if valid fix available
            None if GPS unavailable, line is not GPRMC, or status != 'A'
        """
        if not self._available or self._serial is None:
            return None

        try:
            line = self._serial.readline().decode('ascii', errors='replace')
            # GPRMC = Recommended Minimum Specific GPS/Transit Data
            if line.startswith('$GPRMC'):
                msg = pynmea2.parse(line)
                # Status 'A' = active/valid fix; 'V' = void/invalid
                if msg.status == 'A' and msg.latitude is not None and msg.longitude is not None:
                    location = (float(msg.latitude), float(msg.longitude))
                    self.logger.log_gps_location(location)
                    return location
        except (serial.SerialException, UnicodeDecodeError, pynmea2.ParseError, ValueError) as e:
            self.logger.log_error("GPSManager.get_location", str(e))

        return None

    def get_location_string(self):
        """
        Return the current GPS location as a comma-separated string for logging.

        Reads one NMEA line; returns "N/A" when the GPS is unavailable,
        the line is not GPRMC, or the fix is void. No retry logic.

        Returns:
            String in format "latitude,longitude" (e.g., "37.123456,-122.654321")
            "N/A" if GPS unavailable or no valid fix
        """
        if not self._available or self._serial is None:
            return "N/A"

        try:
            line = self._serial.readline().decode('ascii', errors='replace')
            if line.startswith('$GPRMC'):
                msg = pynmea2.parse(line)
                if msg.status == 'A' and msg.latitude is not None and msg.longitude is not None:
                    lat = float(msg.latitude)
                    lon = float(msg.longitude)
                    return f"{lat},{lon}"
        except (serial.SerialException, UnicodeDecodeError, pynmea2.ParseError, ValueError) as e:
            self.logger.log_error("GPSManager.get_location_string", str(e))

        return "N/A"

    def is_available(self):
        """
        Return True if the serial port was successfully opened at construction time.

        Does not verify satellite lock; use get_location() to confirm an active fix.
        """
        return self._available

    def get_coordinates(self):
        """
        Single-read alias for get_location() used by FireDetector.

        Returns:
            Tuple of (latitude, longitude) if valid fix available
            None if GPS unavailable or no valid fix

        Equivalent to get_location() but does not call log_gps_location,
        so it avoids duplicate log entries when called inside a detection loop.
        """
        if not self._available or self._serial is None:
            return None

        try:
            line = self._serial.readline().decode('ascii', errors='replace')
            if line.startswith('$GPRMC'):
                msg = pynmea2.parse(line)
                if msg.status == 'A' and msg.latitude is not None and msg.longitude is not None:
                    return (float(msg.latitude), float(msg.longitude))
        except (serial.SerialException, UnicodeDecodeError, pynmea2.ParseError, ValueError) as e:
            self.logger.log_error("GPSManager.get_coordinates", str(e))

        return None

    def get_current_coordinates(self):
        """
        Get current GPS coordinates with retry logic.

        Returns:
            Tuple of (latitude, longitude) if valid fix obtained
            None if GPS unavailable or max attempts exceeded

        Retries up to GPS_READ_MAX_ATTEMPTS times to get a valid fix.
        Useful during calibration when a definite reading is needed.
        """
        if not self._available or self._serial is None:
            return None

        try:
            for attempt in range(GPS_READ_MAX_ATTEMPTS):
                if self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('ascii', errors='replace')
                    if line.startswith('$GPRMC'):
                        msg = pynmea2.parse(line)
                        if msg.status == 'A' and msg.latitude is not None and msg.longitude is not None:
                            location = (float(msg.latitude), float(msg.longitude))
                            self.logger.log_gps_location(location)
                            return location
                else:
                    # No bytes waiting yet — sleep briefly before the next attempt
                    time.sleep(0.01)
        except (serial.SerialException, UnicodeDecodeError, pynmea2.ParseError, ValueError) as e:
            self.logger.log_error("GPSManager.get_current_coordinates", str(e))

        return None

    def close(self):
        """
        Close GPS serial connection.

        Releases the serial port. Should be called during system shutdown.
        """
        if self._serial is not None:
            try:
                self._serial.close()
                self._available = False
            except (OSError, serial.SerialException) as e:
                self.logger.log_error("GPSManager.close", str(e))