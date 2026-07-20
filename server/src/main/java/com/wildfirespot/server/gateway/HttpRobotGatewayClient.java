package com.wildfirespot.server.gateway;

import com.wildfirespot.server.common.CameraCommand;
import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.io.InputStream;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * HTTP implementation of {@link RobotGatewayClient}.
 *
 * <p>Communicates with the Python FastAPI server ({@code robot.robot_api}) running on the
 * robot over HTTP using Spring's {@link RestClient}. All read and write operations are
 * forwarded to the corresponding Python endpoints:
 * <ul>
 *   <li>GET  /robot/status, /robot/health, /robot/gps, /robot/sensors,
 *       /robot/fire/status, /robot/logs</li>
 *   <li>POST /robot/control — forwarded by {@link #sendControlCommand}</li>
 *   <li>POST /robot/mode   — forwarded by {@link #changeMode}</li>
 * </ul>
 *
 * <p>Every method returns a safe fallback value when the Python API is unreachable,
 * times out, or returns an unexpected response, so the dashboard remains functional
 * during connectivity loss.
 */
public class HttpRobotGatewayClient implements RobotGatewayClient {

    private static final Logger log = LoggerFactory.getLogger(HttpRobotGatewayClient.class);

    private final RestClient restClient;

    public HttpRobotGatewayClient(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public StatusResponse getStatus() {
        try {
            StatusResponse response = restClient.get()
                    .uri("/robot/status")
                    .retrieve()
                    .body(StatusResponse.class);
            return response != null ? response : fallbackStatus();
        } catch (RestClientException e) {
            log.error("GET /robot/status failed: {}", e.getMessage());
            return fallbackStatus();
        }
    }

    @Override
    public HealthResponse getHealth() {
        try {
            HealthResponse response = restClient.get()
                    .uri("/robot/health")
                    .retrieve()
                    .body(HealthResponse.class);
            return response != null ? response : fallbackHealth();
        } catch (RestClientException e) {
            log.error("GET /robot/health failed: {}", e.getMessage());
            return fallbackHealth();
        }
    }

    @Override
    public GpsResponse getGps() {
        try {
            GpsResponse response = restClient.get()
                    .uri("/robot/gps")
                    .retrieve()
                    .body(GpsResponse.class);
            return response != null ? response : fallbackGps();
        } catch (RestClientException e) {
            log.error("GET /robot/gps failed: {}", e.getMessage());
            return fallbackGps();
        }
    }

    @Override
    public SensorResponse getSensors() {
        try {
            SensorResponse response = restClient.get()
                    .uri("/robot/sensors")
                    .retrieve()
                    .body(SensorResponse.class);
            return response != null ? response : fallbackSensors();
        } catch (RestClientException e) {
            log.error("GET /robot/sensors failed: {}", e.getMessage());
            return fallbackSensors();
        }
    }

    @Override
    public FireStatusResponse getFireStatus() {
        try {
            FireStatusResponse response = restClient.get()
                    .uri("/robot/fire/status")
                    .retrieve()
                    .body(FireStatusResponse.class);
            return response != null ? response : fallbackFireStatus();
        } catch (RestClientException e) {
            log.error("GET /robot/fire/status failed: {}", e.getMessage());
            return fallbackFireStatus();
        }
    }

    @Override
    public LogResponse getLogs() {
        try {
            LogResponse response = restClient.get()
                    .uri("/robot/logs")
                    .retrieve()
                    .body(LogResponse.class);
            return response != null ? response : fallbackLogs();
        } catch (RestClientException e) {
            log.error("GET /robot/logs failed: {}", e.getMessage());
            return fallbackLogs();
        }
    }

    @Override
    public ControlResponse sendControlCommand(ControlCommand command) {
        try {
            ControlResponse response = restClient.post()
                    .uri("/robot/control")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("command", command.name()))
                    .retrieve()
                    .body(ControlResponse.class);
            return response != null ? response : new ControlResponse(false, command.name());
        } catch (RestClientException e) {
            log.error("POST /robot/control failed: {}", e.getMessage());
            return new ControlResponse(false, command.name());
        }
    }

    @Override
    public ModeResponse changeMode(RobotMode mode) {
        try {
            ModeResponse response = restClient.post()
                    .uri("/robot/mode")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("mode", mode.name()))
                    .retrieve()
                    .body(ModeResponse.class);
            return response != null ? response : new ModeResponse(false, mode.name());
        } catch (RestClientException e) {
            log.error("POST /robot/mode failed: {}", e.getMessage());
            return new ModeResponse(false, mode.name());
        }
    }

    private StatusResponse fallbackStatus() {
        return new StatusResponse("UNKNOWN", "UNKNOWN", false, LocalDateTime.now());
    }

    private HealthResponse fallbackHealth() {
        return new HealthResponse(false, false, false, false, false);
    }


    private GpsResponse fallbackGps() {
        return new GpsResponse(null, null, false, LocalDateTime.now());
    }

    private SensorResponse fallbackSensors() {
        SensorResponse.FlameStatus flame = new SensorResponse.FlameStatus(false, false, false, false);
        return new SensorResponse(0.0, 0.0, flame, "UNAVAILABLE");
    }

    private FireStatusResponse fallbackFireStatus() {
        return new FireStatusResponse("NORMAL", false, false, false, false, null, null);
    }

    private LogResponse fallbackLogs() {
        return new LogResponse(List.of());
    }

    @Override
    public MissionZoneResponse getMissionZone() {
        try {
            PythonMissionZoneResponse response = restClient.get()
                    .uri("/robot/mission/zone")
                    .retrieve()
                    .body(PythonMissionZoneResponse.class);
            if (response == null || response.points() == null) {
                return fallbackMissionZone();
            }
            List<MissionZoneResponse.ZonePoint> validPoints = response.points().stream()
                    .filter(Objects::nonNull)
                    .filter(p -> p.latitude() != null && p.longitude() != null)
                    .map(p -> new MissionZoneResponse.ZonePoint(p.latitude(), p.longitude()))
                    .toList();
            return new MissionZoneResponse(validPoints, validPoints.size());
        } catch (RestClientException e) {
            log.error("GET /robot/mission/zone failed: {}", e.getMessage());
            return fallbackMissionZone();
        } catch (RuntimeException e) {
            log.error("GET /robot/mission/zone mapping failed: {}", e.getMessage());
            return fallbackMissionZone();
        }
    }

    @Override
    public MissionPointResponse addMissionZonePoint(double latitude, double longitude) {
        try {
            MissionPointResponse response = restClient.post()
                    .uri("/robot/mission/zone/points")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("latitude", latitude, "longitude", longitude))
                    .retrieve()
                    .body(MissionPointResponse.class);
            return response != null ? response : new MissionPointResponse(false, latitude, longitude);
        } catch (RestClientException e) {
            log.error("POST /robot/mission/zone/points failed: {}", e.getMessage());
            return new MissionPointResponse(false, latitude, longitude);
        }
    }

    @Override
    public MissionZoneResetResponse resetMissionZone() {
        try {
            MissionZoneResetResponse response = restClient.delete()
                    .uri("/robot/mission/zone")
                    .retrieve()
                    .body(MissionZoneResetResponse.class);
            return response != null ? response : new MissionZoneResetResponse(false);
        } catch (RestClientException e) {
            log.error("DELETE /robot/mission/zone failed: {}", e.getMessage());
            return new MissionZoneResetResponse(false);
        }
    }

    private MissionZoneResponse fallbackMissionZone() {
        return new MissionZoneResponse(List.of(), 0);
    }

    @Override
    public CameraControlResponse sendCameraCommand(CameraCommand command) {
        try {
            CameraControlResponse response = restClient.post()
                    .uri("/robot/camera/control")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("command", command.name()))
                    .retrieve()
                    .body(CameraControlResponse.class);
            return response != null ? response : fallbackCameraControl(command);
        } catch (RestClientException e) {
            log.error("POST /robot/camera/control failed: {}", e.getMessage());
            return fallbackCameraControl(command);
        }
    }

    @Override
    public CameraStatusResponse getCameraStatus() {
        try {
            CameraStatusResponse response = restClient.get()
                    .uri("/robot/camera/status")
                    .retrieve()
                    .body(CameraStatusResponse.class);
            return response != null ? response : fallbackCameraStatus();
        } catch (RestClientException e) {
            log.error("GET /robot/camera/status failed: {}", e.getMessage());
            return fallbackCameraStatus();
        }
    }

    private CameraControlResponse fallbackCameraControl(CameraCommand command) {
        return new CameraControlResponse(
                false,
                command.name(),
                "robot_api_unavailable",
                new CameraControlResponse.Position("STOP", null)
        );
    }

    private CameraStatusResponse fallbackCameraStatus() {
        return new CameraStatusResponse(false, "STOP", null);
    }

    @Override
    public boolean isCameraStreamAvailable() {
        try {
            return Boolean.TRUE.equals(
                    restClient.get()
                            .uri("/robot/camera/stream")
                            .exchange((request, response) -> {
                                boolean ok = response.getStatusCode().is2xxSuccessful();
                                response.getBody().close();
                                return ok;
                            })
            );
        } catch (RestClientException e) {
            log.warn("GET /robot/camera/stream preflight failed: {}", e.getMessage());
            return false;
        }
    }

    @Override
    public StreamingResponseBody streamCamera() {
        return outputStream -> {
            try {
                restClient.get()
                        .uri("/robot/camera/stream")
                        .exchange((request, response) -> {
                            if (!response.getStatusCode().is2xxSuccessful()) {
                                throw new CameraStreamUnavailableException(response.getStatusCode().value());
                            }
                            try (InputStream in = response.getBody()) {
                                byte[] buffer = new byte[4096];
                                int read;
                                while ((read = in.read(buffer)) != -1) {
                                    outputStream.write(buffer, 0, read);
                                    outputStream.flush();
                                }
                            }
                            return null;
                        });
            } catch (CameraStreamUnavailableException e) {
                log.warn("GET /robot/camera/stream upstream returned {}", e.statusCode);
                throw new java.io.IOException("upstream status " + e.statusCode, e);
            } catch (RestClientException e) {
                log.error("GET /robot/camera/stream failed: {}", e.getMessage());
                throw new java.io.IOException("upstream unavailable", e);
            }
        };
    }

    static final class CameraStreamUnavailableException extends RuntimeException {
        final int statusCode;
        CameraStreamUnavailableException(int statusCode) {
            super("upstream status " + statusCode);
            this.statusCode = statusCode;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private record PythonMissionZoneResponse(List<PythonZonePoint> points) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    private record PythonZonePoint(Double latitude, Double longitude) {}
}
