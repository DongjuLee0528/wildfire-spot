package com.wildfirespot.server.dto;

public record FireStatusResponse(
        boolean hardwareConfirmed,
        boolean cameraDetected,
        boolean finalConfirmedFire
) {}
