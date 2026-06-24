package com.wildfirespot.server.dto;

import java.time.LocalDateTime;

public record StatusResponse(
        String state,
        String mode,
        boolean robotConnected,
        LocalDateTime lastUpdate
) {}
