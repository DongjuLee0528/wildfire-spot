package com.wildfirespot.server.fire;

import com.wildfirespot.server.device.Device;
import com.wildfirespot.server.device.DeviceRepository;
import com.wildfirespot.server.device.DeviceService;
import com.wildfirespot.server.dto.FireEventResponse;
import com.wildfirespot.server.dto.FireEventUploadRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Service
public class FireEventService {

    private final DeviceRepository deviceRepository;
    private final FireEventRepository fireEventRepository;

    public FireEventService(DeviceRepository deviceRepository,
                            FireEventRepository fireEventRepository) {
        this.deviceRepository = deviceRepository;
        this.fireEventRepository = fireEventRepository;
    }

    @Transactional
    public FireEventResponse upload(String deviceId, FireEventUploadRequest request) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceService.DeviceNotFoundException("Device not found: " + deviceId));

        LocalDateTime detectedAt = request.detectedAt() != null
                ? request.detectedAt()
                : LocalDateTime.now();

        FireEvent event = fireEventRepository.save(new FireEvent(
                device,
                request.fireDetected(),
                request.confidence(),
                request.severity(),
                request.source(),
                request.latitude(),
                request.longitude(),
                request.imagePath(),
                detectedAt
        ));
        return FireEventResponse.from(event);
    }

    @Transactional(readOnly = true)
    public Optional<FireEventResponse> getLatestForOwner(String username, String deviceId) {
        Device device = resolveOwnedDevice(username, deviceId);
        return fireEventRepository.findTopByDeviceOrderByDetectedAtDesc(device)
                .map(FireEventResponse::from);
    }

    @Transactional(readOnly = true)
    public List<FireEventResponse> getHistoryForOwner(String username, String deviceId) {
        Device device = resolveOwnedDevice(username, deviceId);
        return fireEventRepository.findAllByDeviceOrderByDetectedAtDesc(device).stream()
                .map(FireEventResponse::from)
                .toList();
    }

    private Device resolveOwnedDevice(String username, String deviceId) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceService.DeviceNotFoundException("Device not found: " + deviceId));
        if (!device.getOwner().username().equals(username)) {
            throw new DeviceService.DeviceNotFoundException("Device not found: " + deviceId);
        }
        return device;
    }
}
