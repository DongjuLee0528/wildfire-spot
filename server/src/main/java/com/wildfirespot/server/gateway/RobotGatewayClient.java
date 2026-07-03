package com.wildfirespot.server.gateway;

import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.*;

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
}
