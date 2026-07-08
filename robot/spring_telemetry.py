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
        self._client = client
        self._collector = data_collector
        self._interval = max(1.0, interval)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_fire_detected: Optional[bool] = None
        self._last_fire_upload_time: float = 0.0

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
        while not self._stop_event.is_set():
            try:
                self._upload_cycle()
            except Exception as e:
                logger.error("SpringTelemetry: unexpected error in upload cycle: %s", e)
            self._stop_event.wait(self._interval)

    def _upload_cycle(self) -> None:
        self._upload_heartbeat()
        self._upload_gps()
        self._upload_sensors()
        self._upload_fire_event()

    def _upload_heartbeat(self) -> None:
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

            if self._last_fire_detected is None:
                if not fire_detected:
                    self._last_fire_detected = False
                    return
                state_changed = True

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
