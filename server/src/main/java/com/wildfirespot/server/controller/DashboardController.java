package com.wildfirespot.server.controller;

import com.wildfirespot.server.common.CameraCommand;
import com.wildfirespot.server.dto.*;
import com.wildfirespot.server.service.DashboardService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;


/**
 * REST controller that exposes robot dashboard endpoints to the web frontend.
 *
 * <p>All routes are prefixed with {@code /api} and delegate directly to
 * {@link DashboardService}. Read endpoints ({@code GET}) surface live robot data;
 * write endpoints ({@code POST}) forward commands to the robot gateway.
 */
@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "*")
public class DashboardController {

    private final DashboardService dashboardService;

    public DashboardController(DashboardService dashboardService) {
        this.dashboardService = dashboardService;
    }

    @GetMapping("/status")
    public ResponseEntity<StatusResponse> getStatus() {
        return ResponseEntity.ok(dashboardService.getStatus());
    }

    @GetMapping("/health")
    public ResponseEntity<HealthResponse> getHealth() {
        return ResponseEntity.ok(dashboardService.getHealth());
    }

    @GetMapping("/gps")
    public ResponseEntity<GpsResponse> getGps() {
        return ResponseEntity.ok(dashboardService.getGps());
    }

    @GetMapping("/sensors")
    public ResponseEntity<SensorResponse> getSensors() {
        return ResponseEntity.ok(dashboardService.getSensors());
    }

    @GetMapping("/fire/status")
    public ResponseEntity<FireStatusResponse> getFireStatus() {
        return ResponseEntity.ok(dashboardService.getFireStatus());
    }

    @GetMapping("/logs")
    public ResponseEntity<LogResponse> getLogs() {
        return ResponseEntity.ok(dashboardService.getLogs());
    }

    @PostMapping("/control")
    public ResponseEntity<ControlResponse> postControl(@Valid @RequestBody ControlRequest request) {
        return ResponseEntity.ok(dashboardService.processControl(request.command()));
    }

    @PostMapping("/mode")
    public ResponseEntity<ModeResponse> postMode(@Valid @RequestBody ModeRequest request) {
        return ResponseEntity.ok(dashboardService.processMode(request.mode()));
    }

    @GetMapping("/mission/zone")
    public ResponseEntity<MissionZoneResponse> getMissionZone() {
        return ResponseEntity.ok(dashboardService.getMissionZone());
    }

    @PostMapping("/mission/zone/points")
    public ResponseEntity<MissionPointResponse> addMissionZonePoint(@Valid @RequestBody MissionPointRequest request) {
        return ResponseEntity.ok(dashboardService.addMissionZonePoint(request.latitude(), request.longitude()));
    }

    @DeleteMapping("/mission/zone")
    public ResponseEntity<MissionZoneResetResponse> resetMissionZone() {
        return ResponseEntity.ok(dashboardService.resetMissionZone());
    }

    @PostMapping("/camera/control")
    public ResponseEntity<CameraControlResponse> postCameraControl(@Valid @RequestBody CameraControlRequest request) {
        return ResponseEntity.ok(dashboardService.processCameraCommand(request.command()));
    }

    @GetMapping("/camera/status")
    public ResponseEntity<CameraStatusResponse> getCameraStatus() {
        return ResponseEntity.ok(dashboardService.getCameraStatus());
    }

    @GetMapping("/camera/stream")
    public ResponseEntity<StreamingResponseBody> getCameraStream() {
        if (!dashboardService.isCameraStreamAvailable()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("multipart/x-mixed-replace; boundary=frame"))
                .body(dashboardService.getCameraStream());
    }
}
