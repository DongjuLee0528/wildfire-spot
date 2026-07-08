package com.wildfirespot.server.dto;

public record DeviceAuthResponse(String accessToken, String tokenType) {
    public DeviceAuthResponse(String accessToken) {
        this(accessToken, "DEVICE");
    }
}
