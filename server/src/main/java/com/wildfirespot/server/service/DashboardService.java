package com.wildfirespot.server.service;

import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.*;
import com.wildfirespot.server.gateway.RobotGatewayClient;
import org.springframework.stereotype.Service;

/**
 * Application-layer service for the robot dashboard.
 *
 * <p>Acts as the single point of entry between {@code DashboardController} and
 * {@link RobotGatewayClient}. All data retrieval and command dispatch is
 * delegated to the active gateway implementation; no business logic lives here.
 */
@Service
public class DashboardService {

    private final RobotGatewayClient robotGatewayClient;

    public DashboardService(RobotGatewayClient robotGatewayClient) {
        this.robotGatewayClient = robotGatewayClient;
    }

    public StatusResponse getStatus() {
        return robotGatewayClient.getStatus();
    }

    public HealthResponse getHealth() {
        return robotGatewayClient.getHealth();
    }

    public GpsResponse getGps() {
        return robotGatewayClient.getGps();
    }

    public SensorResponse getSensors() {
        return robotGatewayClient.getSensors();
    }

    public FireStatusResponse getFireStatus() {
        return robotGatewayClient.getFireStatus();
    }

    public LogResponse getLogs() {
        return robotGatewayClient.getLogs();
    }

    public ControlResponse processControl(ControlCommand command) {
        return robotGatewayClient.sendControlCommand(command);
    }

    public ModeResponse processMode(RobotMode mode) {
        return robotGatewayClient.changeMode(mode);
    }

    public MissionZoneResponse getMissionZone() {
        return robotGatewayClient.getMissionZone();
    }

    public MissionPointResponse addMissionZonePoint(double latitude, double longitude) {
        return robotGatewayClient.addMissionZonePoint(latitude, longitude);
    }

    public MissionZoneResetResponse resetMissionZone() {
        return robotGatewayClient.resetMissionZone();
    }
}
