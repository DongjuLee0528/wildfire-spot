package com.wildfirespot.server.dto;

import com.wildfirespot.server.common.RobotMode;
import jakarta.validation.constraints.NotNull;

public record ModeRequest(@NotNull RobotMode mode) {}
