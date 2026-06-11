"""
GPS Manager Module for Location Tracking

This module provides GPS functionality for obtaining current geographic coordinates
using NMEA 0183 protocol over serial communication. It parses GPS data from receivers
and provides convenient methods for location retrieval.

Classes:
    GPSManager: GPS receiver interface for location services

Features:
    - Real-time GPS coordinate parsing
    - GPRMC sentence processing
    - Error handling for GPS connectivity
    - Coordinate formatting utilities

Dependencies:
    - Serial communication for GPS data
    - PyNMEA2 for NMEA sentence parsing
"""

from utils.config import *
import serial
import pynmea2

class GPSManager:
    """
    GPS manager class for location tracking and coordinate retrieval.

    Provides interface to GPS receiver via serial communication, parsing NMEA
    sentences to extract latitude and longitude coordinates.

    Attributes:
        _serial: Serial connection to GPS receiver
        _available (bool): GPS availability status
    """

    def __init__(self):
        """
        Initialize GPS manager with serial connection.
        """
        try:
            # Establish serial connection to GPS receiver
            self._serial = serial.Serial(GPS_UART_PORT, GPS_BAUDRATE, timeout=1)
            self._available = True
        except:
            # Handle GPS connection failure gracefully
            self._serial = None
            self._available = False

    def get_location(self):
        """
        Get current GPS coordinates from receiver.

        Reads NMEA sentences from GPS receiver and parses GPRMC data
        to extract latitude and longitude coordinates.

        Returns:
            tuple: (latitude, longitude) as float values, or (None, None) if unavailable
        """
        if not self._available or self._serial is None:
            return (None, None)

        try:
            # Read NMEA sentence from GPS receiver
            line = self._serial.readline().decode('ascii', errors='replace')
            # Parse GPRMC (Recommended Minimum Specific GPS/Transit Data)
            if line.startswith('$GPRMC'):
                msg = pynmea2.parse(line)
                # Check if GPS fix is valid (status 'A' = active/valid)
                if msg.status == 'A':
                    return (msg.latitude, msg.longitude)
        except:
            pass

        return (None, None)

    def get_location_string(self):
        """
        Get location as formatted string.

        Returns:
            str: Comma-separated coordinates "lat,lon" or "N/A" if unavailable
        """
        lat, lon = self.get_location()
        if lat is not None and lon is not None:
            return f"{lat},{lon}"
        return "N/A"

    def is_available(self):
        """
        Check GPS receiver availability status.

        Returns:
            bool: True if GPS is available and connected, False otherwise
        """
        return self._available

    def get_coordinates(self):
        """
        Alias for get_location() method.

        Returns:
            tuple: (latitude, longitude) coordinates
        """
        return self.get_location()

    def close(self):
        """
        Close GPS serial connection and free resources.
        """
        if self._serial is not None:
            self._serial.close()
            self._available = False