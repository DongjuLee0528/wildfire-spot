package com.wildfirespot.server.adapter;

import com.wildfirespot.server.dto.SensorResponse;

public interface RobotSensorProvider {
    SensorResponse getSensors();
}
