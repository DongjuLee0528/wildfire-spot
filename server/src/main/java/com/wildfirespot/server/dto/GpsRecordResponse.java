package com.wildfirespot.server.dto;

import com.wildfirespot.server.gps.GpsRecord;

import java.time.LocalDateTime;

public record GpsRecordResponse(
        String id,
        String deviceId,
        Double latitude,
        Double longitude,
        Double altitude,
        Double speed,
        Double heading,
        LocalDateTime recordedAt,
        LocalDateTime createdAt
) {
    public static GpsRecordResponse from(GpsRecord record) {
        return new GpsRecordResponse(
                record.getId(),
                record.getDevice().getId(),
                record.getLatitude(),
                record.getLongitude(),
                record.getAltitude(),
                record.getSpeed(),
                record.getHeading(),
                record.getRecordedAt(),
                record.getCreatedAt()
        );
    }
}
