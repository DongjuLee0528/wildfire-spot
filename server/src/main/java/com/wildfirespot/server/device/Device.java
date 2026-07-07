package com.wildfirespot.server.device;

import java.time.LocalDateTime;

public class Device {

    private final String id;
    private final String ownerUsername;
    private String name;
    private String serialNumber;
    private String deviceKey;
    private String description;
    private final LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Device(String id, String ownerUsername, String name, String serialNumber, String deviceKey, String description) {
        this.id = id;
        this.ownerUsername = ownerUsername;
        this.name = name;
        this.serialNumber = serialNumber;
        this.deviceKey = deviceKey;
        this.description = description;
        this.createdAt = LocalDateTime.now();
        this.updatedAt = this.createdAt;
    }

    public String getId() { return id; }
    public String getOwnerUsername() { return ownerUsername; }
    public String getName() { return name; }
    public String getSerialNumber() { return serialNumber; }
    public String getDeviceKey() { return deviceKey; }
    public String getDescription() { return description; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }

    public void setName(String name) { this.name = name; }
    public void setDescription(String description) { this.description = description; }
    public void touch() { this.updatedAt = LocalDateTime.now(); }
}
