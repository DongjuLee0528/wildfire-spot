package com.wildfirespot.server.sensor;

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
@Table(name = "sensor_records")
public class SensorRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "device_id", nullable = false)
    private Device device;

    private Double temperature;

    private Double humidity;

    private Double smokeLevel;

    private Double gasLevel;

    private Boolean flameDetected;

    @Column(nullable = false)
    private LocalDateTime recordedAt;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    protected SensorRecord() {}

    public SensorRecord(Device device, Double temperature, Double humidity,
                        Double smokeLevel, Double gasLevel, Boolean flameDetected,
                        LocalDateTime recordedAt) {
        this.device = device;
        this.temperature = temperature;
        this.humidity = humidity;
        this.smokeLevel = smokeLevel;
        this.gasLevel = gasLevel;
        this.flameDetected = flameDetected;
        this.recordedAt = recordedAt;
        this.createdAt = LocalDateTime.now();
    }

    public String getId() { return id; }
    public Device getDevice() { return device; }
    public Double getTemperature() { return temperature; }
    public Double getHumidity() { return humidity; }
    public Double getSmokeLevel() { return smokeLevel; }
    public Double getGasLevel() { return gasLevel; }
    public Boolean getFlameDetected() { return flameDetected; }
    public LocalDateTime getRecordedAt() { return recordedAt; }
    public LocalDateTime getCreatedAt() { return createdAt; }
}
