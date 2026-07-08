package com.wildfirespot.server.dto;

import jakarta.validation.constraints.NotBlank;

public record DeviceAuthRequest(
        @NotBlank String serialNumber,
        @NotBlank String deviceKey
) {}
