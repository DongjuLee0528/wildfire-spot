package com.wildfirespot.server.gps;

import com.wildfirespot.server.device.Device;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "gps_records")
public class GpsRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "device_id", nullable = false)
    private Device device;

    @Column(nullable = false)
    private Double latitude;

    @Column(nullable = false)
    private Double longitude;

    private Double altitude;

    private Double speed;

    private Double heading;

    @Column(nullable = false)
    private LocalDateTime recordedAt;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    protected GpsRecord() {}

    public GpsRecord(Device device, Double latitude, Double longitude,
                     Double altitude, Double speed, Double heading, LocalDateTime recordedAt) {
        this.device = device;
        this.latitude = latitude;
        this.longitude = longitude;
        this.altitude = altitude;
        this.speed = speed;
        this.heading = heading;
        this.recordedAt = recordedAt;
        this.createdAt = LocalDateTime.now();
    }

    public String getId() { return id; }
    public Device getDevice() { return device; }
    public Double getLatitude() { return latitude; }
    public Double getLongitude() { return longitude; }
    public Double getAltitude() { return altitude; }
    public Double getSpeed() { return speed; }
    public Double getHeading() { return heading; }
    public LocalDateTime getRecordedAt() { return recordedAt; }
    public LocalDateTime getCreatedAt() { return createdAt; }
}
