package com.wildfirespot.server.device;

import com.wildfirespot.server.dto.HeartbeatRequest;
import com.wildfirespot.server.dto.HeartbeatResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DeviceHeartbeatService {

    private final DeviceRepository deviceRepository;
    private final DeviceStatusRepository deviceStatusRepository;

    public DeviceHeartbeatService(
            DeviceRepository deviceRepository,
            DeviceStatusRepository deviceStatusRepository
    ) {
        this.deviceRepository = deviceRepository;
        this.deviceStatusRepository = deviceStatusRepository;
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
        return deviceStatusRepository.findTopByDeviceOrderByUpdatedAtDesc(device).orElse(null);
    }

    public boolean isOnline(DeviceStatus status) {
        return status != null && status.isOnline();
    }
}
