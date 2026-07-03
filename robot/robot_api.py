"""
Wildfire Spot Robot API.

Exposes Robot Core data and control interfaces to the Spring RobotGatewayClient.
All endpoints fail gracefully when hardware managers are unavailable.

Run with:
    uvicorn robot.robot_api:app --host 0.0.0.0 --port 8000
"""

import dataclasses
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_state_machine = None
_collector = None
_manual_control_manager = None
_mode_control_manager = None
_patrol_zone_manager = None


def configure(
    state_machine=None,
    collector=None,
    manual_control_manager=None,
    mode_control_manager=None,
    patrol_zone_manager=None,
):
    global _state_machine, _collector, _manual_control_manager
    global _mode_control_manager, _patrol_zone_manager
    _state_machine = state_machine
    _collector = collector
    _manual_control_manager = manual_control_manager
    _mode_control_manager = mode_control_manager
    _patrol_zone_manager = patrol_zone_manager


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
    try:
        if _collector is None:
            return {
                "temperature": None,
                "humidity": None,
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
