package com.wildfirespot.server.adapter;

import com.wildfirespot.server.dto.GpsResponse;

/** Provides the latest GPS coordinates and fix status. */
public interface RobotGpsProvider {
    GpsResponse getGps();
}
