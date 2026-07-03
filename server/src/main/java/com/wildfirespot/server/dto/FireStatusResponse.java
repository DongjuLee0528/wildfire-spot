package com.wildfirespot.server.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public record FireStatusResponse(
        String state,
        boolean suspected,
        boolean verified,
        boolean cameraDetected,
        boolean sensorDetected,
        Map<String, Object> latestAlertEvent,
        Map<String, Object> latestReportEvent
) {}
