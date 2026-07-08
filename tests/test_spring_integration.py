"""
Local integration test: Python Robot Core → Spring backend.

Requires:
  - Spring running at SPRING_API_BASE_URL (default http://localhost:8080)
  - A registered device in the DB (DEVICE_SERIAL_NUMBER + DEVICE_KEY set)

Run from the project root:
    DEVICE_SERIAL_NUMBER=<sn> DEVICE_KEY=<key> python3 -m tests.test_spring_integration

Or with all options:
    SPRING_TELEMETRY_ENABLED=true \
    SPRING_API_BASE_URL=http://localhost:8080 \
    DEVICE_SERIAL_NUMBER=<registered_serial_number> \
    DEVICE_KEY=<registered_device_key> \
    python3 -m tests.test_spring_integration

Or load from .env.robot:
    set -a && source .env.robot && set +a
    python3 -m tests.test_spring_integration

Does NOT start robot movement, require Jetson hardware, camera, or GPIO.
"""

import os
import sys
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.WARNING,
    format="[%(levelname)s] %(name)s: %(message)s",
)

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from robot.spring_api_client import SpringApiClient
except ImportError as e:
    print(f"FATAL: Cannot import SpringApiClient: {e}")
    sys.exit(1)

from utils.config import SPRING_API_BASE_URL, DEVICE_SERIAL_NUMBER, DEVICE_KEY


_PASS = "  PASS"
_FAIL = "  FAIL"


def _result(label: str, ok: bool, detail: str = "") -> bool:
    status = _PASS if ok else _FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"{status}  {label}{suffix}")
    return ok


def run() -> int:
    """
    Run all integration checks. Returns 0 if all pass, 1 if any fail.
    Does not auto-run on import.
    """
    serial_number = DEVICE_SERIAL_NUMBER
    device_key = DEVICE_KEY
    base_url = SPRING_API_BASE_URL

    print()
    print("=" * 60)
    print("  Wildfire Spot — Spring Integration Test")
    print("=" * 60)
    print(f"  Base URL      : {base_url}")
    print(f"  Serial Number : {serial_number or '(not set)'}")
    print(f"  Device Key    : {'***' if device_key else '(not set)'}")
    print("=" * 60)
    print()

    if not serial_number or not device_key:
        print("FATAL: DEVICE_SERIAL_NUMBER and DEVICE_KEY must be set.")
        print()
        if not serial_number:
            print("  FAIL  DEVICE_SERIAL_NUMBER is missing or empty")
        if not device_key:
            print("  FAIL  DEVICE_KEY is missing or empty")
        print()
        print("  Set them before running:")
        print("    DEVICE_SERIAL_NUMBER=<registered_serial_number> \\")
        print("    DEVICE_KEY=<registered_device_key> \\")
        print("    python3 -m tests.test_spring_integration")
        return 1

    try:
        import requests as _req
        _req.get(base_url, timeout=3)
    except Exception as conn_err:
        err_msg = str(conn_err)
        if "Connection refused" in err_msg or "ConnectionError" in err_msg or "Failed to establish" in err_msg:
            print(f"FATAL: Cannot reach Spring at {base_url}")
            print("  Make sure ./gradlew bootRun is running.")
            return 1

    client = SpringApiClient(
        serial_number=serial_number,
        device_key=device_key,
        base_url=base_url,
    )

    failures = 0

    print("1. Device Login")
    ok = client.login()
    if not _result("POST /api/device-auth/login", ok):
        failures += 1
        print()
        print("  Cannot continue without a valid device token.")
        print("  Check that the device is registered in the database.")
        return 1

    print()
    print("2. Heartbeat")
    ok = client.send_heartbeat(
        mode="PATROL",
        battery_level=92.5,
        robot_state="IDLE",
    )
    if not _result("POST /api/device/heartbeat", ok):
        failures += 1

    print()
    print("3. GPS")
    ok = client.send_gps(
        latitude=37.566535,
        longitude=126.977969,
        altitude=30.0,
        speed=0.5,
        heading=90.0,
        recorded_at=datetime.now(timezone.utc),
    )
    if not _result("POST /api/device/gps", ok):
        failures += 1

    print()
    print("4. Sensors")
    ok = client.send_sensors(
        temperature=28.4,
        humidity=55.1,
        smoke_level=42.0,
        gas_level=18.0,
        flame_detected=False,
        recorded_at=datetime.now(timezone.utc),
    )
    if not _result("POST /api/device/sensors", ok):
        failures += 1

    print()
    print("5. Fire Event (no fire)")
    ok = client.send_fire_event(
        fire_detected=False,
        confidence=0.05,
        severity="LOW",
        source="SENSOR",
        latitude=37.566535,
        longitude=126.977969,
        detected_at=datetime.now(timezone.utc),
    )
    if not _result("POST /api/device/fire-events (fire_detected=False)", ok):
        failures += 1

    print()
    print("6. Fire Event (fire detected)")
    ok = client.send_fire_event(
        fire_detected=True,
        confidence=0.91,
        severity="HIGH",
        source="CAMERA",
        latitude=37.566535,
        longitude=126.977969,
        detected_at=datetime.now(timezone.utc),
    )
    if not _result("POST /api/device/fire-events (fire_detected=True)", ok):
        failures += 1

    print()
    print("=" * 60)
    total = 6
    passed = total - failures
    print(f"  Result: {passed}/{total} passed")
    if failures == 0:
        print("  ALL PASS")
    else:
        print(f"  {failures} FAILED")
    print("=" * 60)
    print()

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
