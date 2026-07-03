package com.wildfirespot.server.dto;

/**
 * Sensor data snapshot returned by {@code GET /api/sensors}.
 *
 * <p>{@code lidarStatus} is a string tag such as {@code "SCANNING"} or {@code "UNAVAILABLE"}.
 */
public record SensorResponse(
        double temperature,
        double humidity,
        int mq2Gas,
        FlameStatus flame,
        String lidarStatus
) {
    /** Per-direction flame detection readings from the four KY-026 IR sensors. */
    public record FlameStatus(
            boolean frontLeft,
            boolean frontRight,
            boolean left,
            boolean right
    ) {}
}
