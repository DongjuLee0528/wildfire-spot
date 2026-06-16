from utils.config import GPS_UART_PORT, GPS_BAUDRATE, GPS_READ_MAX_ATTEMPTS
import serial
import pynmea2

class GPSManager:

    def __init__(self):
        try:
            self._serial = serial.Serial(GPS_UART_PORT, GPS_BAUDRATE, timeout=1)
            self._available = True
        except (OSError, serial.SerialException):
            self._serial = None
            self._available = False

    def get_location(self):
        if not self._available or self._serial is None:
            return (None, None)

        try:
            line = self._serial.readline().decode('ascii', errors='replace')
            if line.startswith('$GPRMC'):
                msg = pynmea2.parse(line)
                if msg.status == 'A':
                    return (msg.latitude, msg.longitude)
        except (serial.SerialException, UnicodeDecodeError, pynmea2.ParseError):
            pass

        return (None, None)

    def get_location_string(self):
        lat, lon = self.get_location()
        if lat is not None and lon is not None:
            return f"{lat},{lon}"
        return "N/A"

    def is_available(self):
        return self._available

    def get_coordinates(self):
        return self.get_location()

    def get_current_coordinates(self):
        if not self._available or self._serial is None:
            return None

        try:
            for attempt in range(GPS_READ_MAX_ATTEMPTS):
                if self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('ascii', errors='replace')
                    if line.startswith('$GPRMC'):
                        msg = pynmea2.parse(line)
                        if msg.status == 'A' and msg.latitude and msg.longitude:
                            return (float(msg.latitude), float(msg.longitude))
        except (serial.SerialException, UnicodeDecodeError, pynmea2.ParseError, ValueError):
            pass

        return None

    def close(self):
        if self._serial is not None:
            self._serial.close()
            self._available = False