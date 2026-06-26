package com.wildfirespot.server.adapter;

import com.wildfirespot.server.dto.StatusResponse;

public interface RobotStatusProvider {
    StatusResponse getStatus();
}
