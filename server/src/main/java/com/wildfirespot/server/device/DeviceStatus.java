package com.wildfirespot.server.device;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "device_status")
public class DeviceStatus {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "device_id", nullable = false, unique = true)
    private Device device;

    @Column(nullable = false)
    private boolean online;

    private LocalDateTime lastSeenAt;

    private String mode;

    private Double batteryLevel;

    private String robotState;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(nullable = false)
    private LocalDateTime updatedAt;

    protected DeviceStatus() {}

    public DeviceStatus(Device device) {
        this.device = device;
        this.online = false;
        this.createdAt = LocalDateTime.now();
        this.updatedAt = this.createdAt;
    }

    public String getId() { return id; }
    public Device getDevice() { return device; }
    public boolean isOnline() { return online; }
    public LocalDateTime getLastSeenAt() { return lastSeenAt; }
    public String getMode() { return mode; }
    public Double getBatteryLevel() { return batteryLevel; }
    public String getRobotState() { return robotState; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }

    public void recordHeartbeat(String mode, Double batteryLevel, String robotState) {
        this.online = true;
        this.lastSeenAt = LocalDateTime.now();
        if (mode != null) this.mode = mode;
        if (batteryLevel != null) this.batteryLevel = batteryLevel;
        if (robotState != null) this.robotState = robotState;
        this.updatedAt = LocalDateTime.now();
    }
}
