package com.wildfirespot.server.controller;

import com.wildfirespot.server.device.DeviceService;
import com.wildfirespot.server.dto.DevicePatchRequest;
import com.wildfirespot.server.dto.DeviceRequest;
import com.wildfirespot.server.dto.DeviceResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/devices")
public class DeviceController {

    private final DeviceService deviceService;

    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @PostMapping
    public ResponseEntity<DeviceResponse> register(
            @AuthenticationPrincipal String username,
            @Valid @RequestBody DeviceRequest request
    ) {
        DeviceResponse response = deviceService.register(username, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping
    public ResponseEntity<List<DeviceResponse>> list(@AuthenticationPrincipal String username) {
        return ResponseEntity.ok(deviceService.listOwned(username));
    }

    @GetMapping("/{deviceId}")
    public ResponseEntity<DeviceResponse> get(
            @AuthenticationPrincipal String username,
            @PathVariable String deviceId
    ) {
        return ResponseEntity.ok(deviceService.getOwned(username, deviceId));
    }

    @PatchMapping("/{deviceId}")
    public ResponseEntity<DeviceResponse> patch(
            @AuthenticationPrincipal String username,
            @PathVariable String deviceId,
            @RequestBody DevicePatchRequest request
    ) {
        return ResponseEntity.ok(deviceService.patch(username, deviceId, request));
    }

    @DeleteMapping("/{deviceId}")
    public ResponseEntity<Void> delete(
            @AuthenticationPrincipal String username,
            @PathVariable String deviceId
    ) {
        deviceService.delete(username, deviceId);
        return ResponseEntity.noContent().build();
    }
}
