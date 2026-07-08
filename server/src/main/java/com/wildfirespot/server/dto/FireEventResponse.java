package com.wildfirespot.server.dto;

import com.wildfirespot.server.fire.FireEvent;

import java.time.LocalDateTime;

public record FireEventResponse(
        String id,
        String deviceId,
        boolean fireDetected,
        Double confidence,
        String severity,
        String source,
        Double latitude,
        Double longitude,
        String imagePath,
        LocalDateTime detectedAt,
        LocalDateTime createdAt
) {
    public static FireEventResponse from(FireEvent event) {
        return new FireEventResponse(
                event.getId(),
                event.getDevice().getId(),
                event.isFireDetected(),
                event.getConfidence(),
                event.getSeverity(),
                event.getSource(),
                event.getLatitude(),
                event.getLongitude(),
                event.getImagePath(),
                event.getDetectedAt(),
                event.getCreatedAt()
        );
    }
}
