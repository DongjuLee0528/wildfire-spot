package com.wildfirespot.server.dto;

import com.wildfirespot.server.common.ControlCommand;
import jakarta.validation.constraints.NotNull;

public record ControlRequest(@NotNull ControlCommand command) {}
