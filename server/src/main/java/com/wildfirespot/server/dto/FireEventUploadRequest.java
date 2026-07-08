package com.wildfirespot.server.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;

import java.time.LocalDateTime;

public record FireEventUploadRequest(
        boolean fireDetected,
        @DecimalMin("0.0") @DecimalMax("1.0") Double confidence,
        String severity,
        String source,
        @DecimalMin("-90.0") @DecimalMax("90.0") Double latitude,
        @DecimalMin("-180.0") @DecimalMax("180.0") Double longitude,
        String imagePath,
        LocalDateTime detectedAt
) {}
