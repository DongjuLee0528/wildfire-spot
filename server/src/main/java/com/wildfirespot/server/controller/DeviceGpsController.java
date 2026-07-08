package com.wildfirespot.server.controller;

import com.wildfirespot.server.dto.GpsRecordResponse;
import com.wildfirespot.server.dto.GpsUploadRequest;
import com.wildfirespot.server.gps.GpsService;
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
public class DeviceGpsController {

    private final GpsService gpsService;

    public DeviceGpsController(GpsService gpsService) {
        this.gpsService = gpsService;
    }

    @PostMapping("/gps")
    public ResponseEntity<GpsRecordResponse> uploadGps(
            @AuthenticationPrincipal String deviceId,
            @Valid @RequestBody GpsUploadRequest request
    ) {
        GpsRecordResponse response = gpsService.upload(deviceId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
