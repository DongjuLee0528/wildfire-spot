package com.wildfirespot.server.dto;

public record HealthResponse(
        boolean robotCore,
        boolean camera,
        boolean gps,
        boolean lidar,
        boolean sensors
) {}
