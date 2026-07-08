package com.wildfirespot.server.dto;

import com.wildfirespot.server.mission.Mission;
import com.wildfirespot.server.mission.MissionStatus;

import java.time.LocalDateTime;

public record MissionResponse(
        String id,
        String deviceId,
        String ownerUsername,
        String missionName,
        String missionType,
        MissionStatus status,
        LocalDateTime startedAt,
        LocalDateTime finishedAt,
        Long durationSeconds,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    public static MissionResponse from(Mission mission) {
        return new MissionResponse(
                mission.getId(),
                mission.getDevice().getId(),
                mission.getOwner().username(),
                mission.getMissionName(),
                mission.getMissionType(),
                mission.getStatus(),
                mission.getStartedAt(),
                mission.getFinishedAt(),
                mission.getDurationSeconds(),
                mission.getCreatedAt(),
                mission.getUpdatedAt()
        );
    }
}
