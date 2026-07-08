package com.wildfirespot.server.device;

import com.wildfirespot.server.auth.User;
import com.wildfirespot.server.auth.UserRepository;
import com.wildfirespot.server.dto.DevicePatchRequest;
import com.wildfirespot.server.dto.DeviceRequest;
import com.wildfirespot.server.dto.DeviceResponse;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class DeviceService {

    private final DeviceRepository deviceRepository;
    private final UserRepository userRepository;
    private final DeviceHeartbeatService heartbeatService;
    private final PasswordEncoder passwordEncoder;

    public DeviceService(DeviceRepository deviceRepository,
                         UserRepository userRepository,
                         DeviceHeartbeatService heartbeatService,
                         PasswordEncoder passwordEncoder) {
        this.deviceRepository = deviceRepository;
        this.userRepository = userRepository;
        this.heartbeatService = heartbeatService;
        this.passwordEncoder = passwordEncoder;
    }

    @Transactional
    public DeviceResponse register(String username, DeviceRequest request) {
        User owner = resolveUser(username);
        if (deviceRepository.existsBySerialNumber(request.serialNumber())) {
            throw new DeviceConflictException("Serial number already registered: " + request.serialNumber());
        }
        if (deviceKeyAlreadyRegistered(request.deviceKey())) {
            throw new DeviceConflictException("Device key already registered");
        }
        Device device = deviceRepository.save(
                new Device(owner, request.name(), request.serialNumber(), passwordEncoder.encode(request.deviceKey()), request.description())
        );
        return toResponse(device);
    }

    @Transactional(readOnly = true)
    public List<DeviceResponse> listOwned(String username) {
        User owner = resolveUser(username);
        return deviceRepository.findAllByOwner(owner).stream()
                .map(this::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public DeviceResponse getOwned(String username, String deviceId) {
        Device device = findAndVerifyOwnership(username, deviceId);
        return toResponse(device);
    }

    @Transactional
    public DeviceResponse patch(String username, String deviceId, DevicePatchRequest request) {
        Device device = findAndVerifyOwnership(username, deviceId);
        if (request.name() != null && !request.name().isBlank()) {
            device.setName(request.name());
        }
        if (request.description() != null) {
            device.setDescription(request.description());
        }
        device.touch();
        return toResponse(deviceRepository.save(device));
    }

    @Transactional
    public void delete(String username, String deviceId) {
        findAndVerifyOwnership(username, deviceId);
        deviceRepository.deleteById(deviceId);
    }

    private DeviceResponse toResponse(Device device) {
        DeviceStatus status = heartbeatService.getStatus(device);
        boolean online = heartbeatService.isOnline(status);
        return DeviceResponse.from(device, status, online);
    }

    private User resolveUser(String username) {
        return userRepository.findByUsername(username)
                .orElseThrow(() -> new DeviceNotFoundException("User not found: " + username));
    }

    private boolean deviceKeyAlreadyRegistered(String rawDeviceKey) {
        return deviceRepository.findAll().stream()
                .anyMatch(device -> deviceKeyMatches(rawDeviceKey, device.getDeviceKey()));
    }

    private boolean deviceKeyMatches(String rawDeviceKey, String storedDeviceKey) {
        if (rawDeviceKey == null || storedDeviceKey == null) {
            return false;
        }
        return passwordEncoder.matches(rawDeviceKey, storedDeviceKey)
                || rawDeviceKey.equals(storedDeviceKey);
    }

    private Device findAndVerifyOwnership(String username, String deviceId) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceNotFoundException("Device not found: " + deviceId));
        if (!device.getOwner().username().equals(username)) {
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
