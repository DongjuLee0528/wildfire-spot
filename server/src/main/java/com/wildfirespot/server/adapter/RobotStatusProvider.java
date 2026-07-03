package com.wildfirespot.server.adapter;

import com.wildfirespot.server.dto.StatusResponse;

/** Provides the current robot operational state and mode. */
public interface RobotStatusProvider {
    StatusResponse getStatus();
}
