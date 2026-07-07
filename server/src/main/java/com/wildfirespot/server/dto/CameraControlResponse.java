package com.wildfirespot.server.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Response body for {@code POST /api/camera/control}. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CameraControlResponse(boolean accepted, String command, String reason, Position position) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Position(String pan, Double tilt) {}
}
