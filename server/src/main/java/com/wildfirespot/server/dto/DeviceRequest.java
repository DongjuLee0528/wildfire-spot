package com.wildfirespot.server.dto;

import jakarta.validation.constraints.NotBlank;

public record DeviceRequest(
        @NotBlank String name,
        @NotBlank String serialNumber,
        @NotBlank String deviceKey,
        String description
) {}
