package com.wildfirespot.server.dto;

import java.util.List;

public record MissionZoneResponse(List<ZonePoint> points, int pointCount) {
    public record ZonePoint(double latitude, double longitude) {}
}
