package com.wildfirespot.server.dto;

public record SensorResponse(
        double temperature,
        double humidity,
        int mq2Gas,
        FlameStatus flame,
        String lidarStatus
) {
    public record FlameStatus(
            boolean frontLeft,
            boolean frontRight,
            boolean left,
            boolean right
    ) {}
}
