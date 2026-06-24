package com.wildfirespot.server.service;

import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.*;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

/**
 * DashboardService - Phase 2 Mock Implementation
 *
 * Current flow:  Controller → DashboardService → Mock Data
 * Future flow:   Controller → DashboardService → Robot Gateway Client → Python Robot Core
 *
 * All methods in this service are placeholders returning static mock data.
 * Replace each method body with a Robot Gateway client call in Phase 3.
 */
@Service
public class DashboardService {

    public StatusResponse getStatus() {
        return new StatusResponse(
                "PATROL",
                "AUTO",
                true,
                LocalDateTime.now()
        );
    }

    public HealthResponse getHealth() {
        return new HealthResponse(
                true,   // robotCore
                false,  // camera  (stream not yet available)
                true,   // gps
                true,   // lidar
                true    // sensors
        );
    }

    public GpsResponse getGps() {
        return new GpsResponse(
                37.5665,
                126.9780,
                true,
                LocalDateTime.now()
        );
    }

    public SensorResponse getSensors() {
        SensorResponse.FlameStatus flame = new SensorResponse.FlameStatus(
                false,  // frontLeft
                false,  // frontRight
                true,   // left  (detected in mock)
                false   // right
        );
        return new SensorResponse(
                31.5,
                42.0,
                128,
                flame,
                "SCANNING"
        );
    }

    public FireStatusResponse getFireStatus() {
        return new FireStatusResponse(
                true,   // hardwareConfirmed
                false,  // cameraDetected
                false   // finalConfirmedFire
        );
    }

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

    public ControlResponse processControl(ControlCommand command) {
        // Phase 3: forward to Robot Gateway Client
        return new ControlResponse(true, command.name());
    }

    public ModeResponse processMode(RobotMode mode) {
        // Phase 3: forward to Robot Gateway Client
        return new ModeResponse(true, mode.name());
    }
}
