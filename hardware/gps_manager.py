from utils.config import GPS_UART_PORT, GPS_BAUDRATE, GPS_READ_MAX_ATTEMPTS
from utils.logger import WildfireLogger
import serial
import pynmea2
import time

class GPSManager:

    def __init__(self):
        self.logger = WildfireLogger("GPSManager")
        try:
            self._serial = serial.Serial(GPS_UART_PORT, GPS_BAUDRATE, timeout=1)
            self._available = True
        except (OSError, serial.SerialException) as e:
            self.logger.log_error("GPSManager.__init__", str(e))
            self._serial = None
            self._available = False

    def get_location(self):
        if not self._available or self._serial is None:
            return None

        try:
            line = self._serial.readline().decode('ascii', errors='replace')
            if line.startswith('$GPRMC'):
                msg = pynmea2.parse(line)
                if msg.status == 'A' and msg.latitude is not None and msg.longitude is not None:
                    location = (float(msg.latitude), float(msg.longitude))
                    self.logger.log_gps_location(location)
                    return location
        except (serial.SerialException, UnicodeDecodeError, pynmea2.ParseError, ValueError) as e:
            self.logger.log_error("GPSManager.get_location", str(e))

        return None

    def get_location_string(self):
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
        return self._available

    def get_coordinates(self):
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
                    time.sleep(0.01)
        except (serial.SerialException, UnicodeDecodeError, pynmea2.ParseError, ValueError) as e:
            self.logger.log_error("GPSManager.get_current_coordinates", str(e))

        return None

    def close(self):
        if self._serial is not None:
            try:
                self._serial.close()
                self._available = False
            except (OSError, serial.SerialException) as e:
                self.logger.log_error("GPSManager.close", str(e))