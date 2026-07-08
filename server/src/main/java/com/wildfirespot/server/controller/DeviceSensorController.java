package com.wildfirespot.server.controller;

import com.wildfirespot.server.dto.SensorRecordResponse;
import com.wildfirespot.server.dto.SensorUploadRequest;
import com.wildfirespot.server.sensor.SensorService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/device")
public class DeviceSensorController {

    private final SensorService sensorService;

    public DeviceSensorController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @PostMapping("/sensors")
    public ResponseEntity<SensorRecordResponse> uploadSensors(
            @AuthenticationPrincipal String deviceId,
            @RequestBody SensorUploadRequest request
    ) {
        SensorRecordResponse response = sensorService.upload(deviceId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
