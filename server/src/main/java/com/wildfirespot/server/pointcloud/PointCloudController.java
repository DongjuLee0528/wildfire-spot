package com.wildfirespot.server.pointcloud;

import com.wildfirespot.server.device.DeviceService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.transaction.TransactionException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import java.io.IOException;

@RestController
public class PointCloudController {
    private static final Logger log = LoggerFactory.getLogger(PointCloudController.class);
    private final PointCloudStore store;
    private final PointCloudStreams streams;
    private final DeviceService devices;

    public PointCloudController(PointCloudStore store, PointCloudStreams streams, DeviceService devices) {
        this.store = store; this.streams = streams; this.devices = devices;
    }

    @PostMapping(value = "/api/device/point-cloud", consumes = "application/octet-stream")
    public ResponseEntity<Void> upload(@AuthenticationPrincipal String deviceId, HttpServletRequest request) throws IOException {
        if (deviceId == null || deviceId.isBlank()) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        if (request.getContentLengthLong() > PointCloudFrame.MAX_BYTES)
            return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE).build();
        byte[] data = request.getInputStream().readNBytes(PointCloudFrame.MAX_BYTES + 1);
        if (data.length > PointCloudFrame.MAX_BYTES) return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE).build();
        store.accept(deviceId, data);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/devices/{deviceId}/point-cloud/stream")
    public void stream(@AuthenticationPrincipal String username, @PathVariable String deviceId,
                       HttpServletRequest request, HttpServletResponse response) throws IOException {
        if (!request.getMethod().equals("GET")) { response.setStatus(405); return; }
        devices.getOwned(username, deviceId);
        if (store.latest(deviceId) == null) { response.setStatus(503); return; }
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) { response.setStatus(403); return; }
        streams.open(username, deviceId, header.substring(7), request, response);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Void> error(Exception error) {
        HttpStatus status;
        if (error instanceof DeviceService.DeviceNotFoundException) status = HttpStatus.NOT_FOUND;
        else if (error instanceof PointCloudProblem problem) status = problem.status;
        else if (error instanceof IllegalArgumentException) status = HttpStatus.BAD_REQUEST;
        else if (error instanceof DataAccessException || error instanceof TransactionException) status = HttpStatus.SERVICE_UNAVAILABLE;
        else status = HttpStatus.INTERNAL_SERVER_ERROR;
        if (status.is5xxServerError()) log.warn("Point-cloud request failed ({})", error.getClass().getSimpleName());
        return ResponseEntity.status(status).build();
    }
}
