package com.wildfirespot.server.device;

import com.wildfirespot.server.dto.DevicePatchRequest;
import com.wildfirespot.server.dto.DeviceRequest;
import com.wildfirespot.server.dto.DeviceResponse;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class DeviceService {

    private final DeviceRepository deviceRepository;

    public DeviceService(DeviceRepository deviceRepository) {
        this.deviceRepository = deviceRepository;
    }

    public DeviceResponse register(String ownerUsername, DeviceRequest request) {
        if (deviceRepository.existsBySerialNumber(request.serialNumber())) {
            throw new DeviceConflictException("Serial number already registered: " + request.serialNumber());
        }
        if (deviceRepository.existsByDeviceKey(request.deviceKey())) {
            throw new DeviceConflictException("Device key already registered: " + request.deviceKey());
        }
        Device device = deviceRepository.save(
                ownerUsername, request.name(), request.serialNumber(), request.deviceKey(), request.description()
        );
        return DeviceResponse.from(device);
    }

    public List<DeviceResponse> listOwned(String ownerUsername) {
        return deviceRepository.findAllByOwner(ownerUsername).stream()
                .map(DeviceResponse::from)
                .toList();
    }

    public DeviceResponse getOwned(String ownerUsername, String deviceId) {
        Device device = findAndVerifyOwnership(ownerUsername, deviceId);
        return DeviceResponse.from(device);
    }

    public DeviceResponse patch(String ownerUsername, String deviceId, DevicePatchRequest request) {
        Device device = findAndVerifyOwnership(ownerUsername, deviceId);
        if (request.name() != null && !request.name().isBlank()) {
            device.setName(request.name());
        }
        if (request.description() != null) {
            device.setDescription(request.description());
        }
        device.touch();
        return DeviceResponse.from(device);
    }

    public void delete(String ownerUsername, String deviceId) {
        findAndVerifyOwnership(ownerUsername, deviceId);
        deviceRepository.delete(deviceId);
    }

    private Device findAndVerifyOwnership(String ownerUsername, String deviceId) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceNotFoundException("Device not found: " + deviceId));
        if (!device.getOwnerUsername().equals(ownerUsername)) {
            throw new DeviceNotFoundException("Device not found: " + deviceId);
        }
        return device;
    }

    public static class DeviceNotFoundException extends RuntimeException {
        public DeviceNotFoundException(String message) { super(message); }
    }

    public static class DeviceConflictException extends RuntimeException {
        public DeviceConflictException(String message) { super(message); }
    }
}
