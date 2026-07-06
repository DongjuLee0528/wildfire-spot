package com.wildfirespot.server.dto;

import com.wildfirespot.server.common.CameraCommand;
import jakarta.validation.constraints.NotNull;

/** Request body for {@code POST /api/camera/control}. */
public record CameraControlRequest(@NotNull CameraCommand command) {}
