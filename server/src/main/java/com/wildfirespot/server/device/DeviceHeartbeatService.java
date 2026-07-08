package com.wildfirespot.server.device;

import com.wildfirespot.server.dto.HeartbeatRequest;
import com.wildfirespot.server.dto.HeartbeatResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

@Service
public class DeviceHeartbeatService {

    private final DeviceRepository deviceRepository;
    private final DeviceStatusRepository deviceStatusRepository;
    private final long offlineThresholdSeconds;

    public DeviceHeartbeatService(
            DeviceRepository deviceRepository,
            DeviceStatusRepository deviceStatusRepository,
            @Value("${device.offline-threshold-seconds:30}") long offlineThresholdSeconds
    ) {
        this.deviceRepository = deviceRepository;
        this.deviceStatusRepository = deviceStatusRepository;
        this.offlineThresholdSeconds = offlineThresholdSeconds;
    }

    @Transactional
    public HeartbeatResponse recordHeartbeat(String deviceId, HeartbeatRequest request) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceService.DeviceNotFoundException("Device not found: " + deviceId));

        DeviceStatus status = deviceStatusRepository.findByDevice(device)
                .orElseGet(() -> new DeviceStatus(device));

        status.recordHeartbeat(
                request != null ? request.mode() : null,
                request != null ? request.batteryLevel() : null,
                request != null ? request.robotState() : null
        );

        deviceStatusRepository.save(status);
        return HeartbeatResponse.from(status);
    }

    @Transactional(readOnly = true)
    public DeviceStatus getStatus(Device device) {
        return deviceStatusRepository.findByDevice(device).orElse(null);
    }

    public boolean isOnline(DeviceStatus status) {
        if (status == null || status.getLastSeenAt() == null) return false;
        return status.getLastSeenAt().isAfter(
                LocalDateTime.now().minusSeconds(offlineThresholdSeconds)
        );
    }
}
