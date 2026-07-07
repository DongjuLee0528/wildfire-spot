package com.wildfirespot.server.gateway;

import com.wildfirespot.server.common.CameraCommand;
import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.*;

import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/**
 * Gateway interface for all robot data and command operations.
 *
 * <p>Implementations abstract the transport layer (HTTP or mock) so that
 * {@link com.wildfirespot.server.service.DashboardService} is decoupled from
 * the actual communication protocol. The active implementation is selected at
 * startup via {@code robot.gateway.mode} in application properties.
 */
public interface RobotGatewayClient {

    /** Fetch the current robot operational state and mode. */
    StatusResponse getStatus();

    /** Fetch availability flags for each hardware subsystem. */
    HealthResponse getHealth();

    /** Fetch the latest GPS coordinates and fix validity. */
    GpsResponse getGps();

    /** Fetch a snapshot of all environmental sensor readings. */
    SensorResponse getSensors();

    /** Fetch the aggregated fire detection result from hardware and camera channels. */
    FireStatusResponse getFireStatus();

    /** Fetch recent structured log entries from the robot. */
    LogResponse getLogs();

    /** Send a directional or control command to the robot. */
    ControlResponse sendControlCommand(ControlCommand command);

    /** Request an operational mode change (AUTO / MANUAL). */
    ModeResponse changeMode(RobotMode mode);

    /** Fetch the current patrol zone points. */
    MissionZoneResponse getMissionZone();

    /** Add a GPS point to the patrol zone. */
    MissionPointResponse addMissionZonePoint(double latitude, double longitude);

    /** Clear all patrol zone points. */
    MissionZoneResetResponse resetMissionZone();

    /** Send a camera gimbal command to the robot. */
    CameraControlResponse sendCameraCommand(CameraCommand command);

    /** Fetch the current camera pan/tilt status. */
    CameraStatusResponse getCameraStatus();

    /** Check whether the robot camera MJPEG stream endpoint is reachable and returns 2xx. */
    boolean isCameraStreamAvailable();

    /** Open an MJPEG stream from the robot camera. Returns null if unavailable. */
    StreamingResponseBody streamCamera();
}
