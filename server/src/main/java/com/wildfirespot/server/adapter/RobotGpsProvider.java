package com.wildfirespot.server.adapter;

import com.wildfirespot.server.dto.GpsResponse;

public interface RobotGpsProvider {
    GpsResponse getGps();
}
