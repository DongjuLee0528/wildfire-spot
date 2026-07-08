"""
Spring API client for Wildfire Spot Robot Core.

Authenticates the device against the Spring backend and provides
typed methods for each telemetry upload endpoint. All methods are
safe to call without crashing the robot core on failure.
"""

import logging
from datetime import datetime
from typing import Optional

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

from utils.config import SPRING_API_BASE_URL

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 8


def _fmt_dt(dt: datetime) -> str:
    return dt.astimezone(__import__('datetime').timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


class SpringApiClient:
    """
    Device-authenticated HTTP client for the Spring backend.

    Usage:
        client = SpringApiClient(serial_number="SN-001", device_key="secret")
        if client.login():
            client.send_heartbeat(mode="PATROL", battery_level=87.5, robot_state="WALKING")
    """

    def __init__(
        self,
        serial_number: str,
        device_key: str,
        base_url: str = SPRING_API_BASE_URL,
        timeout: int = _DEFAULT_TIMEOUT,
    ):
        if not _REQUESTS_AVAILABLE:
            raise ImportError(
                "The 'requests' package is required. Install it with: pip install requests"
            )
        self._serial_number = serial_number
        self._device_key = device_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._token: Optional[str] = None

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def login(self) -> bool:
        """
        Authenticate device against POST /api/device-auth/login.
        Stores the returned deviceToken in memory.
        Returns True on success, False on any failure.
        """
        try:
            resp = requests.post(
                self._url("/api/device-auth/login"),
                json={"serialNumber": self._serial_number, "deviceKey": self._device_key},
                timeout=self._timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("accessToken") or data.get("deviceToken") or data.get("token")
                if token:
                    self._token = token
                    logger.info("SpringApiClient: device login successful")
                    return True
                logger.error("SpringApiClient: login response missing token field: %s", data)
                return False
            logger.error(
                "SpringApiClient: login failed HTTP %d: %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        except requests.exceptions.ConnectionError:
            logger.error(
                "SpringApiClient: connection refused at %s — is the Spring server running?",
                self._base_url,
            )
            return False
        except requests.exceptions.Timeout:
            logger.error("SpringApiClient: login request timed out after %ds", self._timeout)
            return False
        except Exception as e:
            logger.error("SpringApiClient: login unexpected error: %s", e)
            return False

    def _post(self, path: str, payload: dict, *, retry_login: bool = True) -> bool:
        """
        Internal POST helper with one automatic re-login on 401/403.
        Returns True if the server responded 2xx, False otherwise.
        """
        try:
            resp = requests.post(
                self._url(path),
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
            if resp.status_code in (401, 403):
                if retry_login:
                    logger.warning(
                        "SpringApiClient: %s returned %d — re-authenticating",
                        path,
                        resp.status_code,
                    )
                    if self.login():
                        return self._post(path, payload, retry_login=False)
                logger.error("SpringApiClient: %s unauthorized after re-login", path)
                return False
            if resp.ok:
                return True
            logger.error(
                "SpringApiClient: %s returned HTTP %d: %s",
                path,
                resp.status_code,
                resp.text[:200],
            )
            return False
        except requests.exceptions.ConnectionError:
            logger.error(
                "SpringApiClient: connection refused at %s%s", self._base_url, path
            )
            return False
        except requests.exceptions.Timeout:
            logger.error(
                "SpringApiClient: %s timed out after %ds", path, self._timeout
            )
            return False
        except Exception as e:
            logger.error("SpringApiClient: %s unexpected error: %s", path, e)
            return False

    def send_heartbeat(
        self,
        mode: Optional[str] = None,
        battery_level: Optional[float] = None,
        robot_state: Optional[str] = None,
    ) -> bool:
        """Upload heartbeat to POST /api/device/heartbeat."""
        payload: dict = {}
        if mode is not None:
            payload["mode"] = mode
        if battery_level is not None:
            payload["batteryLevel"] = battery_level
        if robot_state is not None:
            payload["robotState"] = robot_state
        ok = self._post("/api/device/heartbeat", payload)
        if ok:
            logger.debug("SpringApiClient: heartbeat sent")
        return ok

    def send_gps(
        self,
        latitude: float,
        longitude: float,
        altitude: Optional[float] = None,
        speed: Optional[float] = None,
        heading: Optional[float] = None,
        recorded_at: Optional[datetime] = None,
    ) -> bool:
        """Upload GPS record to POST /api/device/gps."""
        payload: dict = {"latitude": latitude, "longitude": longitude}
        if altitude is not None:
            payload["altitude"] = altitude
        if speed is not None:
            payload["speed"] = speed
        if heading is not None:
            payload["heading"] = heading
        if recorded_at is not None:
            payload["recordedAt"] = _fmt_dt(recorded_at)
        ok = self._post("/api/device/gps", payload)
        if ok:
            logger.debug("SpringApiClient: GPS sent (%.6f, %.6f)", latitude, longitude)
        return ok

    def send_sensors(
        self,
        temperature: Optional[float] = None,
        humidity: Optional[float] = None,
        smoke_level: Optional[float] = None,
        gas_level: Optional[float] = None,
        flame_detected: Optional[bool] = None,
        recorded_at: Optional[datetime] = None,
    ) -> bool:
        """Upload sensor reading to POST /api/device/sensors."""
        payload: dict = {}
        if temperature is not None:
            payload["temperature"] = temperature
        if humidity is not None:
            payload["humidity"] = humidity
        if smoke_level is not None:
            payload["smokeLevel"] = smoke_level
        if gas_level is not None:
            payload["gasLevel"] = gas_level
        if flame_detected is not None:
            payload["flameDetected"] = flame_detected
        if recorded_at is not None:
            payload["recordedAt"] = _fmt_dt(recorded_at)
        ok = self._post("/api/device/sensors", payload)
        if ok:
            logger.debug("SpringApiClient: sensors sent")
        return ok

    def send_fire_event(
        self,
        fire_detected: bool,
        confidence: Optional[float] = None,
        severity: Optional[str] = None,
        source: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        image_path: Optional[str] = None,
        detected_at: Optional[datetime] = None,
    ) -> bool:
        """Upload fire event to POST /api/device/fire-events."""
        payload: dict = {"fireDetected": fire_detected}
        if confidence is not None:
            payload["confidence"] = confidence
        if severity is not None:
            payload["severity"] = severity
        if source is not None:
            payload["source"] = source
        if latitude is not None:
            payload["latitude"] = latitude
        if longitude is not None:
            payload["longitude"] = longitude
        if image_path is not None:
            payload["imagePath"] = image_path
        if detected_at is not None:
            payload["detectedAt"] = _fmt_dt(detected_at)
        ok = self._post("/api/device/fire-events", payload)
        if ok:
            logger.debug("SpringApiClient: fire event sent (detected=%s)", fire_detected)
        return ok

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None
