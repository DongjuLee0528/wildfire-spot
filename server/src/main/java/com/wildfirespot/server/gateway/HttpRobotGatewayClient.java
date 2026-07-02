package com.wildfirespot.server.gateway;

import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.time.LocalDateTime;
import java.util.List;

/**
 * HTTP implementation of {@link RobotGatewayClient}.
 *
 * <p>Communicates with the Python FastAPI server running on the robot over HTTP
 * using Spring's {@link RestClient}. Every read method returns a safe fallback
 * value when the robot is unreachable or returns an unexpected response, so the
 * dashboard remains functional during connectivity loss.
 *
 * <p>Write operations ({@link #sendControlCommand} and {@link #changeMode}) are
 * not yet wired to real robot endpoints; they return {@code accepted=false}.
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
        return new ControlResponse(false, command.name());
    }

    @Override
    public ModeResponse changeMode(RobotMode mode) {
        return new ModeResponse(false, mode.name());
    }

    private StatusResponse fallbackStatus() {
        return new StatusResponse("UNKNOWN", "UNKNOWN", false, LocalDateTime.now());
    }

    private HealthResponse fallbackHealth() {
        return new HealthResponse(false, false, false, false, false);
    }

    private GpsResponse fallbackGps() {
        return new GpsResponse(0.0, 0.0, false, LocalDateTime.now());
    }

    private SensorResponse fallbackSensors() {
        SensorResponse.FlameStatus flame = new SensorResponse.FlameStatus(false, false, false, false);
        return new SensorResponse(0.0, 0.0, 0, flame, "UNAVAILABLE");
    }

    private FireStatusResponse fallbackFireStatus() {
        return new FireStatusResponse(false, false, false);
    }

    private LogResponse fallbackLogs() {
        return new LogResponse(List.of());
    }
}
