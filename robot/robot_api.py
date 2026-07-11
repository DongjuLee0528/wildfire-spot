"""
Wildfire Spot Robot API.

Exposes Robot Core data and control interfaces to the Spring RobotGatewayClient.
All endpoints fail gracefully when hardware managers are unavailable.

Run with:
    uvicorn robot.robot_api:app --host 0.0.0.0 --port 8000
"""

import asyncio
import dataclasses
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_state_machine = None
_collector = None
_manual_control_manager = None
_mode_control_manager = None
_patrol_zone_manager = None
_camera_control_manager = None
_camera_vision = None

_CAMERA_COMMANDS = {
    "CAMERA_LEFT",
    "CAMERA_RIGHT",
    "CAMERA_STOP",
    "CAMERA_UP",
    "CAMERA_DOWN",
    "CAMERA_CENTER",
}

_PAN_STATE_MAP = {
    "left": "LEFT",
    "right": "RIGHT",
    "stopped": "STOP",
}


# Sentinel that distinguishes "caller did not pass this argument" from None,
# so configure() can be called multiple times with a partial set of subsystems.
_UNSET = object()


def configure(
    state_machine=_UNSET,
    collector=_UNSET,
    manual_control_manager=_UNSET,
    mode_control_manager=_UNSET,
    patrol_zone_manager=_UNSET,
    camera_control_manager=_UNSET,
    camera_vision=_UNSET,
):
    """
    Inject runtime dependencies into the API module.

    Called once from main.py after all subsystems are initialised.
    Only keyword arguments explicitly passed by the caller are updated;
    omitted arguments leave the corresponding global unchanged.

    Args:
        state_machine: StateMachine instance for robot state queries.
        collector: RobotCoreDataCollector for reading sensor/GPS/fire data.
        manual_control_manager: ManualControlManager for movement commands.
        mode_control_manager: ModeControlManager for AUTO/MANUAL switching.
        patrol_zone_manager: PatrolZoneManager for GPS waypoint management.
        camera_control_manager: CameraControlManager for pan-tilt control.
        camera_vision: CameraVision instance for live video streaming.
    """
    global _state_machine, _collector, _manual_control_manager
    global _mode_control_manager, _patrol_zone_manager, _camera_control_manager, _camera_vision
    if state_machine is not _UNSET:
        _state_machine = state_machine
    if collector is not _UNSET:
        _collector = collector
    if manual_control_manager is not _UNSET:
        _manual_control_manager = manual_control_manager
    if mode_control_manager is not _UNSET:
        _mode_control_manager = mode_control_manager
    if patrol_zone_manager is not _UNSET:
        _patrol_zone_manager = patrol_zone_manager
    if camera_control_manager is not _UNSET:
        _camera_control_manager = camera_control_manager
    if camera_vision is not _UNSET:
        _camera_vision = camera_vision


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("Wildfire Spot Robot API starting")
    yield
    logger.info("Wildfire Spot Robot API stopped")


app = FastAPI(title="Wildfire Spot Robot API", version="0.2.0", lifespan=_lifespan)


class ControlRequest(BaseModel):
    command: str


class ModeRequest(BaseModel):
    mode: str


class ZonePointRequest(BaseModel):
    latitude: float
    longitude: float


@app.get("/robot/status")
def get_status():
    """Return current robot state, operating mode, and connection status."""
    try:
        if _collector is None:
            return JSONResponse(
                status_code=503,
                content={"state": "UNKNOWN", "mode": "UNKNOWN", "robotConnected": False, "lastUpdate": datetime.now().isoformat()},
            )
        data = _collector.get_status()
        return {
            "state": data.state,
            "mode": data.mode,
            "robotConnected": data.robot_connected,
            "lastUpdate": data.last_update.isoformat(),
        }
    except Exception as e:
        logger.error("GET /robot/status failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "status unavailable"})


@app.get("/robot/gps")
def get_gps():
    """Return the latest GPS fix data; latitude/longitude are None when no fix."""
    try:
        if _collector is None:
            return {"latitude": None, "longitude": None, "fix": False, "updatedAt": datetime.now().isoformat()}
        data = _collector.get_gps()
        return {
            "latitude": data.latitude if data.fix else None,
            "longitude": data.longitude if data.fix else None,
            "fix": data.fix,
            "updatedAt": data.updated_at.isoformat(),
        }
    except Exception as e:
        logger.error("GET /robot/gps failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "gps unavailable"})


@app.get("/robot/sensors")
def get_sensors():
    """Return latest readings from all onboard sensors (DHT11, MQ2, KY026)."""
    try:
        if _collector is None:
            return {
                "temperature": 0.0,
                "humidity": 0.0,
                "mq2Gas": 0,
                "flame": {"frontLeft": False, "frontRight": False, "left": False, "right": False},
                "lidarStatus": "UNAVAILABLE",
            }
        data = _collector.get_sensors()
        return {
            "temperature": data.temperature,
            "humidity": data.humidity,
            "mq2Gas": data.mq2_gas,
            "flame": {
                "frontLeft": data.flame.front_left,
                "frontRight": data.flame.front_right,
                "left": data.flame.left,
                "right": data.flame.right,
            },
            "lidarStatus": data.lidar_status,
        }
    except Exception as e:
        logger.error("GET /robot/sensors failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "sensors unavailable"})


@app.get("/robot/health")
def get_health():
    """Return availability flags for each hardware subsystem."""
    try:
        if _collector is None:
            return {"robot": False, "camera": False, "gps": False, "lidar": False, "sensor": False}
        data = _collector.get_health()
        return {
            "robot": data.robot_core,
            "camera": data.camera,
            "gps": data.gps,
            "lidar": data.lidar,
            "sensor": data.sensors,
        }
    except Exception as e:
        logger.error("GET /robot/health failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "health unavailable"})


@app.get("/robot/fire/status")
def get_fire_status():
    """Return the latest fire detection state, confidence level, and raw events."""
    try:
        if _collector is None:
            return {
                "state": "NORMAL",
                "suspected": False,
                "verified": False,
                "cameraDetected": False,
                "sensorDetected": False,
                "latestAlertEvent": None,
                "latestReportEvent": None,
            }
        data = _collector.get_fire_status()

        alert_event = None
        report_event = None
        if data.latest_alert_event is not None:
            try:
                alert_event = dataclasses.asdict(data.latest_alert_event) if dataclasses.is_dataclass(data.latest_alert_event) else vars(data.latest_alert_event)
            except Exception as inner:
                logger.error("GET /robot/fire/status alert serialization failed: %s", inner)
        if data.latest_report_event is not None:
            try:
                report_event = dataclasses.asdict(data.latest_report_event) if dataclasses.is_dataclass(data.latest_report_event) else vars(data.latest_report_event)
            except Exception as inner:
                logger.error("GET /robot/fire/status report serialization failed: %s", inner)

        return {
            "state": data.state,
            "suspected": data.suspected,
            "verified": data.verified,
            "cameraDetected": data.camera_detected,
            "sensorDetected": data.sensor_detected,
            "latestAlertEvent": alert_event,
            "latestReportEvent": report_event,
        }
    except Exception as e:
        logger.error("GET /robot/fire/status failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "fire status unavailable"})


@app.get("/robot/logs")
def get_logs():
    """Return in-memory log entries from WildfireLogger (level, message, timestamp)."""
    try:
        if _collector is None:
            return {"logs": []}
        data = _collector.get_logs()
        return {
            "logs": [
                {
                    "level": entry.level,
                    "message": entry.message,
                    "timestamp": entry.timestamp.isoformat(),
                }
                for entry in data.logs
            ]
        }
    except Exception as e:
        logger.error("GET /robot/logs failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "logs unavailable"})


@app.get("/robot/mission/zone")
def get_mission_zone():
    """Return current patrol zone waypoint list and whether it has enough points."""
    try:
        if _patrol_zone_manager is None:
            return {"points": [], "ready": False}
        return {
            "points": _patrol_zone_manager.get_patrol_zone(),
            "ready": _patrol_zone_manager.is_patrol_zone_ready(),
        }
    except Exception as e:
        logger.error("GET /robot/mission/zone failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "zone unavailable"})


@app.post("/robot/control")
def post_control(body: ControlRequest):
    """Send a directional movement command (FORWARD/BACKWARD/LEFT/RIGHT/STOP/RESET)."""
    try:
        if _manual_control_manager is None:
            return JSONResponse(
                status_code=503,
                content={"accepted": False, "command": body.command, "reason": "manager_unavailable"},
            )
        result = _manual_control_manager.send_command(body.command)
        status = 200 if result.get("accepted") else 400
        return JSONResponse(status_code=status, content=result)
    except Exception as e:
        logger.error("POST /robot/control failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "control unavailable"})


@app.post("/robot/mode")
def post_mode(body: ModeRequest):
    """Switch the operating mode between AUTO and MANUAL."""
    try:
        if _mode_control_manager is None:
            return JSONResponse(
                status_code=503,
                content={"accepted": False, "mode": body.mode, "reason": "manager_unavailable"},
            )
        result = _mode_control_manager.set_mode(body.mode)
        status = 200 if result.get("accepted") else 400
        return JSONResponse(status_code=status, content=result)
    except Exception as e:
        logger.error("POST /robot/mode failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "mode unavailable"})


@app.post("/robot/mission/zone/points")
def post_zone_point(body: ZonePointRequest):
    """Append a GPS waypoint to the patrol zone; rejects out-of-range coordinates."""
    try:
        if _patrol_zone_manager is None:
            return JSONResponse(
                status_code=503,
                content={"accepted": False, "reason": "manager_unavailable"},
            )
        accepted = _patrol_zone_manager.add_patrol_point(body.latitude, body.longitude)
        if accepted:
            return {"accepted": True, "latitude": body.latitude, "longitude": body.longitude}
        return JSONResponse(
            status_code=400,
            content={"accepted": False, "reason": "invalid_coordinates"},
        )
    except Exception as e:
        logger.error("POST /robot/mission/zone/points failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "zone unavailable"})


@app.delete("/robot/mission/zone")
def delete_mission_zone():
    """Clear all patrol zone waypoints and reset the zone to empty."""
    try:
        if _patrol_zone_manager is None:
            return JSONResponse(
                status_code=503,
                content={"accepted": False, "reason": "manager_unavailable"},
            )
        _patrol_zone_manager.reset_patrol_zone()
        return {"accepted": True}
    except Exception as e:
        logger.error("DELETE /robot/mission/zone failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "zone unavailable"})


@app.post("/robot/camera/control")
async def post_camera_control(request: Request):
    """
    Send a pan-tilt camera command.

    Accepted commands: CAMERA_LEFT, CAMERA_RIGHT, CAMERA_STOP,
    CAMERA_UP, CAMERA_DOWN, CAMERA_CENTER.
    """
    try:
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"accepted": False, "command": "", "reason": "malformed_json"},
            )
        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=400,
                content={"accepted": False, "command": "", "reason": "invalid_request"},
            )
        cmd = payload.get("command") or ""
        if not cmd:
            return JSONResponse(
                status_code=400,
                content={"accepted": False, "command": "", "reason": "missing_command"},
            )
        if cmd not in _CAMERA_COMMANDS:
            return JSONResponse(
                status_code=400,
                content={"accepted": False, "command": cmd, "reason": "invalid_command"},
            )
        if _camera_control_manager is None:
            return JSONResponse(
                status_code=503,
                content={"accepted": False, "command": cmd, "reason": "manager_unavailable"},
            )
        if cmd == "CAMERA_LEFT":
            result = _camera_control_manager.camera_left()
        elif cmd == "CAMERA_RIGHT":
            result = _camera_control_manager.camera_right()
        elif cmd == "CAMERA_STOP":
            result = _camera_control_manager.camera_pan_stop()
        elif cmd == "CAMERA_UP":
            result = _camera_control_manager.camera_up()
        elif cmd == "CAMERA_DOWN":
            result = _camera_control_manager.camera_down()
        else:
            result = _camera_control_manager.camera_center()
        result["command"] = cmd
        status = 200 if result.get("accepted") else 503
        return JSONResponse(status_code=status, content=result)
    except Exception as e:
        logger.error("POST /robot/camera/control failed: %s", e)
        return JSONResponse(status_code=503, content={"accepted": False, "command": "", "reason": "camera_unavailable"})


@app.get("/robot/camera/status")
def get_camera_status():
    """Return current camera availability and pan-tilt position."""
    try:
        if _camera_control_manager is None or not _camera_control_manager.is_available():
            return {"available": False, "pan": "STOP", "tilt": None}
        position = _camera_control_manager.get_camera_position().get("position", {})
        pan_raw = position.get("pan", "stopped")
        return {
            "available": True,
            "pan": _PAN_STATE_MAP.get(pan_raw, "STOP"),
            "tilt": position.get("tilt"),
        }
    except Exception as e:
        logger.error("GET /robot/camera/status failed: %s", e)
        return {"available": False, "pan": "STOP", "tilt": None}


@app.get("/robot/camera/stream")
async def get_camera_stream():
    """
    Stream MJPEG video from the onboard camera.

    Returns a multipart/x-mixed-replace response at ~30 fps.
    Stops automatically after 30 consecutive frame-read failures.
    """
    try:
        import cv2 as _cv2
    except ImportError:
        return JSONResponse(status_code=503, content={"error": "cv2_unavailable"})

    if _camera_vision is None or not _camera_vision.is_camera_available():
        return JSONResponse(status_code=503, content={"error": "stream_unavailable"})

    async def _generate():
        """Async generator that yields MJPEG boundary-delimited JPEG frames."""
        consecutive_failures = 0
        _MAX_FAILURES = 30
        while True:
            try:
                frame = _camera_vision.read_frame()
            except Exception as e:
                logger.warning("camera stream read_frame failed: %s", e)
                break
            if frame is not None:
                consecutive_failures = 0
                try:
                    ok, buf = _cv2.imencode(".jpg", frame)
                    if ok:
                        data = buf.tobytes()
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n"
                            + data
                            + b"\r\n"
                        )
                except Exception as e:
                    logger.warning("camera stream encode failed: %s", e)
            else:
                consecutive_failures += 1
                if consecutive_failures >= _MAX_FAILURES:
                    logger.warning("camera stream stopping: %d consecutive None frames", consecutive_failures)
                    break
            await asyncio.sleep(0.033)  # ~30 fps target frame rate

    return StreamingResponse(
        _generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
