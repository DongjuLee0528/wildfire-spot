package com.wildfirespot.server.dto;

import com.wildfirespot.server.sensor.SensorRecord;

import java.time.LocalDateTime;

public record SensorRecordResponse(
        String id,
        String deviceId,
        Double temperature,
        Double humidity,
        Double smokeLevel,
        Double gasLevel,
        Boolean flameDetected,
        LocalDateTime recordedAt,
        LocalDateTime createdAt
) {
    public static SensorRecordResponse from(SensorRecord record) {
        return new SensorRecordResponse(
                record.getId(),
                record.getDevice().getId(),
                record.getTemperature(),
                record.getHumidity(),
                record.getSmokeLevel(),
                record.getGasLevel(),
                record.getFlameDetected(),
                record.getRecordedAt(),
                record.getCreatedAt()
        );
    }
}
