package com.wildfirespot.server.dto;

public record HealthResponse(
        boolean robot,
        boolean camera,
        boolean gps,
        boolean lidar,
        boolean sensor
) {}
