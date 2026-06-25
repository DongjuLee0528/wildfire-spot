package com.wildfirespot.server.gateway;

import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.*;

public interface RobotGatewayClient {
    StatusResponse getStatus();

    HealthResponse getHealth();

    GpsResponse getGps();

    SensorResponse getSensors();

    FireStatusResponse getFireStatus();

    LogResponse getLogs();

    ControlResponse sendControlCommand(ControlCommand command);

    ModeResponse changeMode(RobotMode mode);
}
