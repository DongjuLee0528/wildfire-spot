package com.wildfirespot.server.adapter;

import com.wildfirespot.server.dto.GpsResponse;
import com.wildfirespot.server.dto.SensorResponse;
import com.wildfirespot.server.dto.StatusResponse;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;

@Component
public class MockRobotDataAdapter implements RobotStatusProvider, RobotGpsProvider, RobotSensorProvider {

    @Override
    public StatusResponse getStatus() {
        return new StatusResponse(
                "PATROL",
                "AUTO",
                true,
                LocalDateTime.now()
        );
    }

    @Override
    public GpsResponse getGps() {
        return new GpsResponse(
                37.5665,
                126.9780,
                true,
                LocalDateTime.now()
        );
    }

    @Override
    public SensorResponse getSensors() {
        SensorResponse.FlameStatus flame = new SensorResponse.FlameStatus(
                false,
                false,
                true,
                false
        );
        return new SensorResponse(
                31.5,
                42.0,
                128,
                flame,
                "SCANNING"
        );
    }
}
