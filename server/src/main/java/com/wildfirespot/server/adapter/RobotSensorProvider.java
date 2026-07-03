package com.wildfirespot.server.adapter;

import com.wildfirespot.server.dto.SensorResponse;

/** Provides a snapshot of all environmental sensor readings. */
public interface RobotSensorProvider {
    SensorResponse getSensors();
}
