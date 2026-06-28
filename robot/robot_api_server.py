"""
Read-only REST API server for Robot Core data.

Exposes robot state to Spring backend via HTTP.
Controllers only map data - no business logic here.

Endpoints:
    GET /robot/status   -> StateMachine
    GET /robot/gps      -> GPSManager
    GET /robot/sensors  -> SensorManager + LiDAR status
    GET /robot/health   -> manager availability
    GET /robot/fire/status -> Detection
    GET /robot/logs     -> Logger

Phase 4-3: Read-only. No write endpoints.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from robot.robot_data_collector import RobotDataCollector

logger = logging.getLogger(__name__)

_collector: RobotDataCollector | None = None


def create_app(collector: RobotDataCollector) -> FastAPI:
    """
    Factory function that wires the collector into the app.

    Args:
        collector: RobotDataCollector implementation to use as data source.

    Returns:
        Configured FastAPI application.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Robot API server starting")
        yield
        logger.info("Robot API server stopped")

    app = FastAPI(title="Wildfire Spot Robot API", version="0.1.0", lifespan=lifespan)

    @app.get("/robot/status")
    def get_status():
        try:
            data = collector.get_status()
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
            data = collector.get_gps()
            return {
                "latitude": data.latitude,
                "longitude": data.longitude,
                "fix": data.fix,
                "updatedAt": data.updated_at.isoformat(),
            }
        except Exception as e:
            logger.error("GET /robot/gps failed: %s", e)
            return JSONResponse(status_code=503, content={"error": "gps unavailable"})

    @app.get("/robot/sensors")
    def get_sensors():
        try:
            data = collector.get_sensors()
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
            data = collector.get_health()
            return {
                "robotCore": data.robot_core,
                "camera": data.camera,
                "gps": data.gps,
                "lidar": data.lidar,
                "sensors": data.sensors,
            }
        except Exception as e:
            logger.error("GET /robot/health failed: %s", e)
            return JSONResponse(status_code=503, content={"error": "health unavailable"})

    @app.get("/robot/fire/status")
    def get_fire_status():
        try:
            data = collector.get_fire_status()
            return {
                "hardwareConfirmed": data.hardware_confirmed,
                "cameraDetected": data.camera_detected,
                "finalConfirmedFire": data.final_confirmed_fire,
            }
        except Exception as e:
            logger.error("GET /robot/fire/status failed: %s", e)
            return JSONResponse(status_code=503, content={"error": "fire status unavailable"})

    @app.get("/robot/logs")
    def get_logs():
        try:
            data = collector.get_logs()
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

    return app
