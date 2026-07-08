package com.wildfirespot.server.fire;

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
@Table(name = "fire_events")
public class FireEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "device_id", nullable = false)
    private Device device;

    @Column(nullable = false)
    private boolean fireDetected;

    private Double confidence;

    private String severity;

    private String source;

    private Double latitude;

    private Double longitude;

    private String imagePath;

    @Column(nullable = false)
    private LocalDateTime detectedAt;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    protected FireEvent() {}

    public FireEvent(Device device, boolean fireDetected, Double confidence, String severity,
                     String source, Double latitude, Double longitude, String imagePath,
                     LocalDateTime detectedAt) {
        this.device = device;
        this.fireDetected = fireDetected;
        this.confidence = confidence;
        this.severity = severity;
        this.source = source;
        this.latitude = latitude;
        this.longitude = longitude;
        this.imagePath = imagePath;
        this.detectedAt = detectedAt;
        this.createdAt = LocalDateTime.now();
    }

    public String getId() { return id; }
    public Device getDevice() { return device; }
    public boolean isFireDetected() { return fireDetected; }
    public Double getConfidence() { return confidence; }
    public String getSeverity() { return severity; }
    public String getSource() { return source; }
    public Double getLatitude() { return latitude; }
    public Double getLongitude() { return longitude; }
    public String getImagePath() { return imagePath; }
    public LocalDateTime getDetectedAt() { return detectedAt; }
    public LocalDateTime getCreatedAt() { return createdAt; }
}
