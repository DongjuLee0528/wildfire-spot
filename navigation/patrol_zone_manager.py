"""
GPS-based patrol zone management for autonomous robot patrol.

Maintains an in-memory list of GPS waypoints that define the patrol area.
Provides validation, reset, and query methods for use by higher-level
navigation or mission control components.
"""

from math import isfinite
from utils.config import PATROL_ZONE_MIN_POINTS
from utils.logger import WildfireLogger

# WGS-84 coordinate bounds used for input validation
_LAT_MIN = -90.0
_LAT_MAX = 90.0
_LON_MIN = -180.0
_LON_MAX = 180.0


def _is_valid_point(point):
    """
    Return True if point is a dict with finite lat/lon values within WGS-84 bounds.

    Used internally by validate_patrol_zone() to verify stored point integrity.
    Accepts only dicts with 'latitude' and 'longitude' float-convertible keys.
    """
    if not isinstance(point, dict):
        return False
    try:
        lat = float(point["latitude"])
        lon = float(point["longitude"])
    except (KeyError, TypeError, ValueError):
        return False
    if not isfinite(lat) or not isfinite(lon):
        return False
    return _LAT_MIN <= lat <= _LAT_MAX and _LON_MIN <= lon <= _LON_MAX


class PatrolZoneManager:
    """
    Manages the GPS waypoint list that defines the robot's patrol zone.

    All storage is in-memory. Points are validated on entry; invalid
    coordinates are rejected without raising. The zone is considered ready
    only when it contains at least PATROL_ZONE_MIN_POINTS valid points.
    """

    def __init__(self):
        """Initialise with an empty patrol zone."""
        self.logger = WildfireLogger("PatrolZoneManager")
        self._points = []  # Ordered list of {latitude, longitude} dicts

    def add_patrol_point(self, latitude, longitude):
        """
        Append a GPS coordinate to the patrol zone.

        Args:
            latitude: Decimal degrees, must be finite and in [-90, 90].
            longitude: Decimal degrees, must be finite and in [-180, 180].

        Returns:
            True if the point was accepted and added, False if rejected.
        """
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError) as e:
            self.logger.log_error("PatrolZoneManager.add_patrol_point", f"Invalid coordinate types: {e}")
            return False

        if not isfinite(lat) or not isfinite(lon):
            self.logger.log_error(
                "PatrolZoneManager.add_patrol_point",
                f"Non-finite coordinate rejected: lat={lat}, lon={lon}",
            )
            return False

        if not (_LAT_MIN <= lat <= _LAT_MAX):
            self.logger.log_error(
                "PatrolZoneManager.add_patrol_point",
                f"Latitude out of range: {lat}",
            )
            return False

        if not (_LON_MIN <= lon <= _LON_MAX):
            self.logger.log_error(
                "PatrolZoneManager.add_patrol_point",
                f"Longitude out of range: {lon}",
            )
            return False

        self._points.append({"latitude": lat, "longitude": lon})
        self.logger.info(f"PATROL_ZONE | Point added: ({lat}, {lon}) | Total: {len(self._points)}")
        return True

    def get_patrol_zone(self):
        """
        Return a defensive copy of the current patrol zone point list.

        Each dict is independently copied so external mutation cannot affect
        internal state. Callers may modify the returned list freely.

        Returns:
            List of dicts, each with keys 'latitude' and 'longitude'.
        """
        return [point.copy() for point in self._points]

    def reset_patrol_zone(self):
        """
        Clear all patrol zone points and log the reset event.

        After a reset the zone is no longer ready (is_patrol_zone_ready() → False)
        until new points are added via add_patrol_point().
        """
        count = len(self._points)
        self._points = []
        self.logger.info(f"PATROL_ZONE | Zone reset. {count} point(s) cleared.")

    def is_patrol_zone_ready(self):
        """
        Return True if the patrol zone contains at least PATROL_ZONE_MIN_POINTS points.

        Returns:
            bool
        """
        return len(self._points) >= PATROL_ZONE_MIN_POINTS

    def validate_patrol_zone(self):
        """
        Return a structured validation result for the current patrol zone.

        Checks both point count and coordinate integrity of every stored point.

        Returns:
            dict with keys:
            - valid (bool)
            - reason (str): 'ok', 'not_enough_points', or 'invalid_point'
            - point_count (int)
            - min_points (int)
        """
        count = len(self._points)
        if count < PATROL_ZONE_MIN_POINTS:
            self.logger.warning(
                f"PATROL_ZONE | Validation failed: {count} point(s), minimum {PATROL_ZONE_MIN_POINTS} required."
            )
            return {
                "valid": False,
                "reason": "not_enough_points",
                "point_count": count,
                "min_points": PATROL_ZONE_MIN_POINTS,
            }

        for i, point in enumerate(self._points):
            if not _is_valid_point(point):
                self.logger.log_error(
                    "PatrolZoneManager.validate_patrol_zone",
                    f"Invalid point at index {i}: {point}",
                )
                return {
                    "valid": False,
                    "reason": "invalid_point",
                    "point_count": count,
                    "min_points": PATROL_ZONE_MIN_POINTS,
                }

        return {
            "valid": True,
            "reason": "ok",
            "point_count": count,
            "min_points": PATROL_ZONE_MIN_POINTS,
        }
