package com.wildfirespot.server.dto;

import java.time.LocalDateTime;
import java.util.List;

public record LogResponse(List<LogEntry> logs) {
    public record LogEntry(
            String level,
            String message,
            LocalDateTime timestamp
    ) {}
}
