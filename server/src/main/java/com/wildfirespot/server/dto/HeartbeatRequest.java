package com.wildfirespot.server.dto;

public record HeartbeatRequest(String mode, Double batteryLevel, String robotState) {}
