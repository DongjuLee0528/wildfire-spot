package com.wildfirespot.server.dto;

import com.wildfirespot.server.device.Device;

import java.time.LocalDateTime;

public record DeviceResponse(
        String id,
        String name,
        String serialNumber,
        String deviceKey,
        String description,
        String ownerUsername,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    public static DeviceResponse from(Device device) {
        return new DeviceResponse(
                device.getId(),
                device.getName(),
                device.getSerialNumber(),
                device.getDeviceKey(),
                device.getDescription(),
                device.getOwnerUsername(),
                device.getCreatedAt(),
                device.getUpdatedAt()
        );
    }
}
