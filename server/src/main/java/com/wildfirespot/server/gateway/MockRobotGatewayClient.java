package com.wildfirespot.server.gateway;

import com.wildfirespot.server.adapter.RobotGpsProvider;
import com.wildfirespot.server.adapter.RobotSensorProvider;
import com.wildfirespot.server.adapter.RobotStatusProvider;
import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.*;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Mock implementation of {@link RobotGatewayClient} for local development and testing.
 *
 * <p>Returns hardcoded or provider-generated responses without requiring a live robot
 * connection. GPS, sensor, and status data are supplied by injected provider beans so
 * they can be customised per test scenario. Health, fire status, and logs return fixed
 * realistic values. Write operations always return {@code accepted=true}.
 */
@Component
public class MockRobotGatewayClient implements RobotGatewayClient {

    private final RobotStatusProvider statusProvider;
    private final RobotGpsProvider gpsProvider;
    private final RobotSensorProvider sensorProvider;

    public MockRobotGatewayClient(
            RobotStatusProvider statusProvider,
            RobotGpsProvider gpsProvider,
            RobotSensorProvider sensorProvider
    ) {
        this.statusProvider = statusProvider;
        this.gpsProvider = gpsProvider;
        this.sensorProvider = sensorProvider;
    }

    @Override
    public StatusResponse getStatus() {
        return statusProvider.getStatus();
    }

    @Override
    public HealthResponse getHealth() {
        return new HealthResponse(
                true,
                false,
                true,
                true,
                true
        );
    }

    @Override
    public GpsResponse getGps() {
        return gpsProvider.getGps();
    }

    @Override
    public SensorResponse getSensors() {
        return sensorProvider.getSensors();
    }

    @Override
    public FireStatusResponse getFireStatus() {
        return new FireStatusResponse(
                true,
                false,
                false
        );
    }

    @Override
    public LogResponse getLogs() {
        LocalDateTime base = LocalDateTime.of(2026, 6, 24, 21, 0, 0);
        List<LogResponse.LogEntry> entries = List.of(
                new LogResponse.LogEntry("INFO",  "SYSTEM INITIALIZED SUCCESSFULLY",          base),
                new LogResponse.LogEntry("INFO",  "AUTO MODE ENABLED",                        base.plusSeconds(3)),
                new LogResponse.LogEntry("INFO",  "GPS FIX ACQUIRED - 3D FIX",               base.plusSeconds(4)),
                new LogResponse.LogEntry("INFO",  "SENSOR DATA UPDATED (NOMINAL)",             base.plusSeconds(6)),
                new LogResponse.LogEntry("WARN",  "HARDWARE FIRE CHECK ACTIVE",               base.plusSeconds(10)),
                new LogResponse.LogEntry("WARN",  "CAMERA STREAM WAITING (FEED_UNAVAILABLE)", base.plusSeconds(13))
        );
        return new LogResponse(entries);
    }

    @Override
    public ControlResponse sendControlCommand(ControlCommand command) {
        return new ControlResponse(true, command.name());
    }

    @Override
    public ModeResponse changeMode(RobotMode mode) {
        return new ModeResponse(true, mode.name());
    }
}
