package com.wildfirespot.server.dto;

import java.time.LocalDateTime;

public record GpsResponse(
        double latitude,
        double longitude,
        boolean fix,
        LocalDateTime updatedAt
) {}
