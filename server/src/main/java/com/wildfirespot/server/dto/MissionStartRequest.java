package com.wildfirespot.server.dto;

import jakarta.validation.constraints.NotBlank;

public record MissionStartRequest(
        @NotBlank String deviceId,
        @NotBlank String missionName,
        @NotBlank String missionType
) {}
