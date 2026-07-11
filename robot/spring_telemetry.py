"""
Periodic telemetry uploader for the Wildfire Spot Robot Core.

Runs as a background daemon thread, uploading heartbeat, GPS, sensor,
and fire-event data to the Spring backend at a configurable interval.
All upload failures are logged and silently swallowed so that a broken
network connection never crashes the robot core.

Usage:
    client = SpringApiClient(serial_number=..., device_key=...)
    telemetry = SpringTelemetry(client, data_collector)
    telemetry.start()          # non-blocking
    ...
    telemetry.stop()           # graceful shutdown
"""

import logging
import threading
import time
from typing import Optional

from robot.spring_api_client import SpringApiClient
from utils.config import DEVICE_TELEMETRY_INTERVAL_SECONDS, _env_float

_FIRE_EVENT_FORCE_INTERVAL_SECONDS = _env_float("FIRE_EVENT_FORCE_INTERVAL_SECONDS", 60.0)

logger = logging.getLogger(__name__)


class SpringTelemetry:
    """
    Background telemetry thread that periodically uploads robot data
    to the Spring API via SpringApiClient.

    The data_collector parameter is optional: when None the uploader
    only sends heartbeats with fixed defaults so the device stays online.
    """

    def __init__(
        self,
        client: SpringApiClient,
        data_collector=None,
        interval: float = DEVICE_TELEMETRY_INTERVAL_SECONDS,
    ):
        """
        Initialise the telemetry uploader.

        Args:
            client: Authenticated SpringApiClient used for all uploads.
            data_collector: RobotCoreDataCollector providing live sensor/GPS/fire data.
                            When None only heartbeats with default values are sent.
            interval: Upload cycle period in seconds (minimum 1.0).
        """
        self._client = client
        self._collector = data_collector
        self._interval = max(1.0, interval)  # Enforce a minimum interval to avoid flooding
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_fire_detected: Optional[bool] = None   # Tracks last uploaded fire state
        self._last_fire_upload_time: float = 0.0          # monotonic timestamp of last fire upload

    def start(self) -> None:
        """Start the background telemetry thread (non-blocking)."""
        if self._thread and self._thread.is_alive():
            logger.warning("SpringTelemetry: already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="spring-telemetry", daemon=True
        )
        self._thread.start()
        logger.info(
            "SpringTelemetry: started (interval=%.1fs)", self._interval
        )

    def stop(self, timeout: float = 10.0) -> None:
        """Signal the telemetry thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            logger.info("SpringTelemetry: stopped")

    def _loop(self) -> None:
        """Background thread body: repeatedly run an upload cycle until stop is requested."""
        while not self._stop_event.is_set():
            try:
                self._upload_cycle()
            except Exception as e:
                logger.error("SpringTelemetry: unexpected error in upload cycle: %s", e)
            # Use Event.wait() instead of sleep so stop() can wake the thread immediately
            self._stop_event.wait(self._interval)

    def _upload_cycle(self) -> None:
        """Execute one full telemetry upload cycle (heartbeat → GPS → sensors → fire event)."""
        self._upload_heartbeat()
        self._upload_gps()
        self._upload_sensors()
        self._upload_fire_event()

    def _upload_heartbeat(self) -> None:
        """
        Upload a heartbeat to keep the device marked as online.

        Reads mode and robot_state from the data collector when available.
        battery_level is always None for now (no battery sensor implemented).
        """
        try:
            mode = None
            robot_state = None
            battery_level = None
            if self._collector is not None:
                try:
                    status = self._collector.get_status()
                    mode = getattr(status, "mode", None)
                    robot_state = getattr(status, "state", None)
                except Exception as e:
                    logger.debug("SpringTelemetry: could not read status for heartbeat: %s", e)
            self._client.send_heartbeat(
                mode=mode, battery_level=battery_level, robot_state=robot_state
            )
        except Exception as e:
            logger.error("SpringTelemetry: heartbeat upload error: %s", e)

    def _upload_gps(self) -> None:
        """
        Upload the latest GPS fix to the Spring backend.

        Skipped if collector is None, GPS is unavailable, or no satellite fix.
        """
        if self._collector is None:
            return
        try:
            gps = self._collector.get_gps()
        except Exception as e:
            logger.error("SpringTelemetry: GPS read error: %s", e)
            return
        if gps is None:
            logger.debug("SpringTelemetry: GPS unavailable, skipping upload")
            return
        try:
            if not getattr(gps, "fix", False):
                logger.debug("SpringTelemetry: GPS no fix, skipping upload")
                return
            lat = getattr(gps, "latitude", None)
            lon = getattr(gps, "longitude", None)
            if lat is None or lon is None:
                return
            self._client.send_gps(latitude=lat, longitude=lon)
        except Exception as e:
            logger.error("SpringTelemetry: GPS upload error: %s", e)

    def _upload_sensors(self) -> None:
        """
        Upload the latest sensor snapshot (temperature, humidity, smoke, flame).

        Skipped if collector is None or sensor data is unavailable.
        KY026 flame sensors are OR-reduced to a single boolean flag before upload.
        """
        if self._collector is None:
            return
        try:
            sensors = self._collector.get_sensors()
        except Exception as e:
            logger.error("SpringTelemetry: sensor read error: %s", e)
            return
        if sensors is None:
            logger.debug("SpringTelemetry: sensors unavailable, skipping upload")
            return
        try:
            temperature = getattr(sensors, "temperature", None)
            humidity = getattr(sensors, "humidity", None)
            smoke_level = getattr(sensors, "mq2_gas", None)
            flame_obj = getattr(sensors, "flame", None)
            flame_detected = None
            if flame_obj is not None:
                fl = getattr(flame_obj, "front_left", False)
                fr = getattr(flame_obj, "front_right", False)
                l = getattr(flame_obj, "left", False)
                r = getattr(flame_obj, "right", False)
                flame_detected = any([fl, fr, l, r])
            self._client.send_sensors(
                temperature=temperature,
                humidity=humidity,
                smoke_level=float(smoke_level) if smoke_level is not None else None,
                flame_detected=flame_detected,
            )
        except Exception as e:
            logger.error("SpringTelemetry: sensor upload error: %s", e)

    def _upload_fire_event(self) -> None:
        """
        Upload a fire event to the Spring backend when state changes or periodically.

        Upload is suppressed when:
        - fire_detected is False and no prior state has been recorded (initial NORMAL).
        - State has not changed since the last upload AND the force interval has not elapsed.

        Confidence values: 0.9 for VERIFIED_FIRE, 0.5 for SUSPECTED_FIRE.
        GPS coordinates are attached when a fix is available.
        """
        if self._collector is None:
            return
        try:
            fire_status = self._collector.get_fire_status()
        except Exception as e:
            logger.debug("SpringTelemetry: could not read fire status: %s", e)
            return
        if fire_status is None:
            logger.debug("SpringTelemetry: fire detection unavailable, skipping upload")
            return

        try:
            verified = getattr(fire_status, "verified", False)
            suspected = getattr(fire_status, "suspected", False)
            fire_detected = verified or suspected
            confidence = 0.9 if verified else (0.5 if suspected else None)
            source = "ROBOT_CORE"

            now = time.monotonic()
            state_changed = fire_detected != self._last_fire_detected

            # First cycle: skip upload if fire is not detected to avoid sending
            # a "no fire" event on every fresh startup before any detection occurs.
            if self._last_fire_detected is None:
                if not fire_detected:
                    self._last_fire_detected = False
                    return
                state_changed = True

            # Periodically re-upload to confirm current state even without a change
            force_due = (now - self._last_fire_upload_time) >= _FIRE_EVENT_FORCE_INTERVAL_SECONDS

            if not state_changed and not force_due:
                return

            latitude = None
            longitude = None
            try:
                gps = self._collector.get_gps()
                if gps is not None and getattr(gps, "fix", False):
                    latitude = getattr(gps, "latitude", None)
                    longitude = getattr(gps, "longitude", None)
            except Exception:
                pass

            ok = self._client.send_fire_event(
                fire_detected=fire_detected,
                confidence=confidence,
                source=source,
                latitude=latitude,
                longitude=longitude,
            )
            if ok:
                self._last_fire_detected = fire_detected
                self._last_fire_upload_time = now
                if state_changed:
                    logger.info(
                        "SpringTelemetry: fire state changed → detected=%s confidence=%s",
                        fire_detected, confidence,
                    )
        except Exception as e:
            logger.error("SpringTelemetry: fire event upload error: %s", e)
