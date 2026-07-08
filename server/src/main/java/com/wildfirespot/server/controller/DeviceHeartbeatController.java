package com.wildfirespot.server.controller;

import com.wildfirespot.server.device.DeviceHeartbeatService;
import com.wildfirespot.server.dto.HeartbeatRequest;
import com.wildfirespot.server.dto.HeartbeatResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/device")
public class DeviceHeartbeatController {

    private final DeviceHeartbeatService heartbeatService;

    public DeviceHeartbeatController(DeviceHeartbeatService heartbeatService) {
        this.heartbeatService = heartbeatService;
    }

    @PostMapping("/heartbeat")
    public ResponseEntity<HeartbeatResponse> heartbeat(
            @AuthenticationPrincipal String deviceId,
            @RequestBody(required = false) HeartbeatRequest request
    ) {
        HeartbeatResponse response = heartbeatService.recordHeartbeat(deviceId, request);
        return ResponseEntity.ok(response);
    }
}
