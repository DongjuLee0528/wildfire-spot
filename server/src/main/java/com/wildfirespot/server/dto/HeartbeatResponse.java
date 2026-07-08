package com.wildfirespot.server.dto;

import com.wildfirespot.server.device.DeviceStatus;

import java.time.LocalDateTime;

public record HeartbeatResponse(
        String deviceId,
        boolean online,
        LocalDateTime lastSeenAt,
        String mode,
        Double batteryLevel,
        String robotState
) {
    public static HeartbeatResponse from(DeviceStatus status) {
        return new HeartbeatResponse(
                status.getDevice().getId(),
                status.isOnline(),
                status.getLastSeenAt(),
                status.getMode(),
                status.getBatteryLevel(),
                status.getRobotState()
        );
    }
}
