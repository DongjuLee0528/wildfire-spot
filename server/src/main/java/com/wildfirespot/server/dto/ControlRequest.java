package com.wildfirespot.server.dto;

import com.wildfirespot.server.common.ControlCommand;
import jakarta.validation.constraints.NotNull;

/** Request body for {@code POST /api/control}. {@code command} must be a valid {@link ControlCommand}. */
public record ControlRequest(@NotNull ControlCommand command) {}
