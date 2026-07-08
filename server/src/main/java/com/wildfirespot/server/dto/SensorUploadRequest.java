package com.wildfirespot.server.dto;

import java.time.LocalDateTime;

public record SensorUploadRequest(
        Double temperature,
        Double humidity,
        Double smokeLevel,
        Double gasLevel,
        Boolean flameDetected,
        LocalDateTime recordedAt
) {}
