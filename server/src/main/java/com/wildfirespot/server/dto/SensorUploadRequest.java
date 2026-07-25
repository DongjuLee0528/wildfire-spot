package com.wildfirespot.server.dto;

import java.time.LocalDateTime;

public record SensorUploadRequest(
        Double temperature,
        Double humidity,
        Boolean flameDetected,
        LocalDateTime recordedAt
) {}
