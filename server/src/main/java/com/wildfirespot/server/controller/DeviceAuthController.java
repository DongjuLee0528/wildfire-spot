package com.wildfirespot.server.controller;

import com.wildfirespot.server.auth.DeviceTokenProvider;
import com.wildfirespot.server.device.Device;
import com.wildfirespot.server.device.DeviceRepository;
import com.wildfirespot.server.dto.DeviceAuthRequest;
import com.wildfirespot.server.dto.DeviceAuthResponse;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/device-auth")
public class DeviceAuthController {

    private final DeviceRepository deviceRepository;
    private final DeviceTokenProvider deviceTokenProvider;
    private final PasswordEncoder passwordEncoder;

    public DeviceAuthController(DeviceRepository deviceRepository,
                                DeviceTokenProvider deviceTokenProvider,
                                PasswordEncoder passwordEncoder) {
        this.deviceRepository = deviceRepository;
        this.deviceTokenProvider = deviceTokenProvider;
        this.passwordEncoder = passwordEncoder;
    }

    @PostMapping("/login")
    public ResponseEntity<DeviceAuthResponse> login(@Valid @RequestBody DeviceAuthRequest request) {
        Device device = deviceRepository.findBySerialNumber(request.serialNumber())
                .filter(d -> deviceKeyMatches(request.deviceKey(), d.getDeviceKey()))
                .orElseThrow(() -> new InvalidDeviceCredentialsException("Invalid serial number or device key"));

        String token = deviceTokenProvider.generate(device.getId(), device.getSerialNumber());
        return ResponseEntity.ok(new DeviceAuthResponse(token));
    }

    public static class InvalidDeviceCredentialsException extends RuntimeException {
        public InvalidDeviceCredentialsException(String message) {
            super(message);
        }
    }

    private boolean deviceKeyMatches(String rawDeviceKey, String storedDeviceKey) {
        if (rawDeviceKey == null || storedDeviceKey == null) {
            return false;
        }
        return passwordEncoder.matches(rawDeviceKey, storedDeviceKey)
                || rawDeviceKey.equals(storedDeviceKey);
    }
}
