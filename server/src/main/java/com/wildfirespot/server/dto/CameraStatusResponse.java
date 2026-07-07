package com.wildfirespot.server.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Response body for {@code GET /api/camera/status}. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CameraStatusResponse(boolean available, String pan, Double tilt) {}
