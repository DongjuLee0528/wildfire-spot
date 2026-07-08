package com.wildfirespot.server.controller;

import com.wildfirespot.server.dto.FireEventResponse;
import com.wildfirespot.server.dto.FireEventUploadRequest;
import com.wildfirespot.server.fire.FireEventService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/device")
public class DeviceFireEventController {

    private final FireEventService fireEventService;

    public DeviceFireEventController(FireEventService fireEventService) {
        this.fireEventService = fireEventService;
    }

    @PostMapping("/fire-events")
    public ResponseEntity<FireEventResponse> uploadFireEvent(
            @AuthenticationPrincipal String deviceId,
            @Valid @RequestBody FireEventUploadRequest request
    ) {
        FireEventResponse response = fireEventService.upload(deviceId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
