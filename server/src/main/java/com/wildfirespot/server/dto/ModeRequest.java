package com.wildfirespot.server.dto;

import com.wildfirespot.server.common.RobotMode;
import jakarta.validation.constraints.NotNull;

/** Request body for {@code POST /api/mode}. {@code mode} must be a valid {@link RobotMode}. */
public record ModeRequest(@NotNull RobotMode mode) {}
