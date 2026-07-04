package com.wildfirespot.server.dto;

import java.time.LocalDateTime;

public record GpsResponse(
        Double latitude,
        Double longitude,
        boolean fix,
        LocalDateTime updatedAt
) {}
