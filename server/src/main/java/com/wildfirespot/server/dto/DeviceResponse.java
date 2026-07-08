package com.wildfirespot.server.dto;

import com.wildfirespot.server.device.Device;
import com.wildfirespot.server.device.DeviceStatus;

import java.time.LocalDateTime;

public record DeviceResponse(
        String id,
        String name,
        String serialNumber,
        String description,
        String ownerUsername,
        LocalDateTime createdAt,
        LocalDateTime updatedAt,
        boolean online,
        LocalDateTime lastSeenAt,
        String mode,
        Double batteryLevel,
        String robotState
) {
    public static DeviceResponse from(Device device, DeviceStatus status, boolean online) {
        return new DeviceResponse(
                device.getId(),
                device.getName(),
                device.getSerialNumber(),
                device.getDescription(),
                device.getOwner().username(),
                device.getCreatedAt(),
                device.getUpdatedAt(),
                online,
                status != null ? status.getLastSeenAt() : null,
                status != null ? status.getMode() : null,
                status != null ? status.getBatteryLevel() : null,
                status != null ? status.getRobotState() : null
        );
    }
}
