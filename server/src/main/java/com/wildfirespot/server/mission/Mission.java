package com.wildfirespot.server.mission;

import com.wildfirespot.server.auth.User;
import com.wildfirespot.server.device.Device;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "missions")
public class Mission {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "owner_id", nullable = false)
    private User owner;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "device_id", nullable = false)
    private Device device;

    @Column(nullable = false)
    private String missionName;

    @Column(nullable = false)
    private String missionType;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private MissionStatus status;

    @Column(nullable = false, updatable = false)
    private LocalDateTime startedAt;

    private LocalDateTime finishedAt;

    private Long durationSeconds;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(nullable = false)
    private LocalDateTime updatedAt;

    protected Mission() {}

    public Mission(User owner, Device device, String missionName, String missionType) {
        this.owner = owner;
        this.device = device;
        this.missionName = missionName;
        this.missionType = missionType;
        this.status = MissionStatus.RUNNING;
        this.startedAt = LocalDateTime.now();
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    public void finish() {
        this.status = MissionStatus.COMPLETED;
        this.finishedAt = LocalDateTime.now();
        this.durationSeconds = java.time.Duration.between(startedAt, finishedAt).getSeconds();
        this.updatedAt = LocalDateTime.now();
    }

    public void cancel() {
        this.status = MissionStatus.CANCELLED;
        this.finishedAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    public String getId() { return id; }
    public User getOwner() { return owner; }
    public Device getDevice() { return device; }
    public String getMissionName() { return missionName; }
    public String getMissionType() { return missionType; }
    public MissionStatus getStatus() { return status; }
    public LocalDateTime getStartedAt() { return startedAt; }
    public LocalDateTime getFinishedAt() { return finishedAt; }
    public Long getDurationSeconds() { return durationSeconds; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
}
