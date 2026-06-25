package com.wildfirespot.server.gateway;

import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.*;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

@Service
public class MockRobotGatewayClient implements RobotGatewayClient {

    @Override
    public StatusResponse getStatus() {
        return new StatusResponse(
                "PATROL",
                "AUTO",
                true,
                LocalDateTime.now()
        );
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
        return new GpsResponse(
                37.5665,
                126.9780,
                true,
                LocalDateTime.now()
        );
    }

    @Override
    public SensorResponse getSensors() {
        SensorResponse.FlameStatus flame = new SensorResponse.FlameStatus(
                false,
                false,
                true,
                false
        );
        return new SensorResponse(
                31.5,
                42.0,
                128,
                flame,
                "SCANNING"
        );
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
                new LogResponse.LogEntry("INFO",  "SYSTEM INITIALIZED SUCCESSFULLY",       base),
                new LogResponse.LogEntry("INFO",  "AUTO MODE ENABLED",                     base.plusSeconds(3)),
                new LogResponse.LogEntry("INFO",  "GPS FIX ACQUIRED - 3D FIX",             base.plusSeconds(4)),
                new LogResponse.LogEntry("INFO",  "SENSOR DATA UPDATED (NOMINAL)",          base.plusSeconds(6)),
                new LogResponse.LogEntry("WARN",  "HARDWARE FIRE CHECK ACTIVE",             base.plusSeconds(10)),
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
