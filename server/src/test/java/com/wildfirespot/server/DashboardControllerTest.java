package com.wildfirespot.server;

import com.wildfirespot.server.dto.GpsResponse;
import com.wildfirespot.server.gateway.RobotGatewayClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
@AutoConfigureMockMvc
@WithMockUser(roles = "ADMIN")
class DashboardControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void getStatus_returns200() throws Exception {
        mockMvc.perform(get("/api/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("PATROL"))
                .andExpect(jsonPath("$.mode").value("AUTO"))
                .andExpect(jsonPath("$.robotConnected").value(true));
    }

    @Test
    void getHealth_returns200() throws Exception {
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.robot").value(true));
    }

    @Test
    void getHealth_allFieldsPresent() throws Exception {
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.robot").isBoolean())
                .andExpect(jsonPath("$.camera").isBoolean())
                .andExpect(jsonPath("$.gps").isBoolean())
                .andExpect(jsonPath("$.lidar").isBoolean())
                .andExpect(jsonPath("$.sensor").isBoolean());
    }

    @Test
    void getGps_returns200() throws Exception {
        mockMvc.perform(get("/api/gps"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.latitude").value(37.5665))
                .andExpect(jsonPath("$.fix").value(true));
    }

    @Test
    void getSensors_returns200() throws Exception {
        mockMvc.perform(get("/api/sensors"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.temperature").value(31.5))
                .andExpect(jsonPath("$.flame.left").value(true));
    }

    @Test
    void getSensors_lidarStatusIsString() throws Exception {
        mockMvc.perform(get("/api/sensors"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.lidarStatus").isString());
    }

    @Test
    void getFireStatus_returns200() throws Exception {
        mockMvc.perform(get("/api/fire/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("SUSPECTED_FIRE"))
                .andExpect(jsonPath("$.suspected").value(true))
                .andExpect(jsonPath("$.verified").value(false));
    }

    @Test
    void getFireStatus_allContractFieldsPresent() throws Exception {
        mockMvc.perform(get("/api/fire/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").isString())
                .andExpect(jsonPath("$.suspected").isBoolean())
                .andExpect(jsonPath("$.verified").isBoolean())
                .andExpect(jsonPath("$.cameraDetected").isBoolean())
                .andExpect(jsonPath("$.sensorDetected").isBoolean())
                .andExpect(jsonPath("$.latestAlertEvent").isEmpty())
                .andExpect(jsonPath("$.latestReportEvent").isEmpty());
    }

    @Test
    void getLogs_returns200() throws Exception {
        mockMvc.perform(get("/api/logs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.logs").isArray());
    }

    @Test
    void postControl_validCommand_returns200() throws Exception {
        mockMvc.perform(post("/api/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"command\":\"FORWARD\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true))
                .andExpect(jsonPath("$.command").value("FORWARD"));
    }

    @Test
    void postControl_invalidCommand_returns400() throws Exception {
        mockMvc.perform(post("/api/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"command\":\"FLY\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void postMode_validMode_returns200() throws Exception {
        mockMvc.perform(post("/api/mode")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"mode\":\"MANUAL\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true))
                .andExpect(jsonPath("$.mode").value("MANUAL"));
    }

    @Test
    void postMode_invalidMode_returns400() throws Exception {
        mockMvc.perform(post("/api/mode")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"mode\":\"TURBO\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void getMissionZone_returns200() throws Exception {
        mockMvc.perform(get("/api/mission/zone"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.points").isArray())
                .andExpect(jsonPath("$.pointCount").isNumber());
    }

    @Test
    void postMissionZonePoint_validCoordinates_returns200() throws Exception {
        mockMvc.perform(post("/api/mission/zone/points")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"latitude\":37.5,\"longitude\":127.0}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true))
                .andExpect(jsonPath("$.latitude").value(37.5))
                .andExpect(jsonPath("$.longitude").value(127.0));
    }

    @Test
    void postMissionZonePoint_latitudeOutOfRange_returns400() throws Exception {
        mockMvc.perform(post("/api/mission/zone/points")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"latitude\":91.0,\"longitude\":127.0}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void postMissionZonePoint_longitudeOutOfRange_returns400() throws Exception {
        mockMvc.perform(post("/api/mission/zone/points")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"latitude\":37.5,\"longitude\":181.0}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void postMissionZonePoint_missingFields_returns400() throws Exception {
        mockMvc.perform(post("/api/mission/zone/points")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"latitude\":37.5}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void deleteMissionZone_returns200() throws Exception {
        mockMvc.perform(delete("/api/mission/zone"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }

    @Test
    void deleteMissionZone_calledTwice_noCrash() throws Exception {
        mockMvc.perform(delete("/api/mission/zone"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
        mockMvc.perform(delete("/api/mission/zone"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }

    @Test
    void postMissionZonePoint_boundaryLatitude_minus90_returns200() throws Exception {
        mockMvc.perform(post("/api/mission/zone/points")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"latitude\":-90.0,\"longitude\":0.0}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }

    @Test
    void postMissionZonePoint_boundaryLatitude_plus90_returns200() throws Exception {
        mockMvc.perform(post("/api/mission/zone/points")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"latitude\":90.0,\"longitude\":0.0}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }

    @Test
    void postMissionZonePoint_boundaryLongitude_minus180_returns200() throws Exception {
        mockMvc.perform(post("/api/mission/zone/points")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"latitude\":0.0,\"longitude\":-180.0}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }

    @Test
    void postMissionZonePoint_boundaryLongitude_plus180_returns200() throws Exception {
        mockMvc.perform(post("/api/mission/zone/points")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"latitude\":0.0,\"longitude\":180.0}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }

    @Test
    void postCameraControl_validCommand_returns200() throws Exception {
        mockMvc.perform(post("/api/camera/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"command\":\"CAMERA_LEFT\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true))
                .andExpect(jsonPath("$.command").value("CAMERA_LEFT"));
    }

    @Test
    void postCameraControl_allValidCommands_return200() throws Exception {
        for (String cmd : new String[]{"CAMERA_LEFT", "CAMERA_RIGHT", "CAMERA_STOP", "CAMERA_UP", "CAMERA_DOWN", "CAMERA_CENTER"}) {
            mockMvc.perform(post("/api/camera/control")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"command\":\"" + cmd + "\"}"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.accepted").value(true));
        }
    }

    @Test
    void postCameraControl_invalidCommand_returns400() throws Exception {
        mockMvc.perform(post("/api/camera/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"command\":\"FLY\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void getCameraStatus_returns200() throws Exception {
        mockMvc.perform(get("/api/camera/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.available").isBoolean())
                .andExpect(jsonPath("$.pan").isString());
    }

    @Test
    void getCameraStatus_allContractFieldsPresent() throws Exception {
        mockMvc.perform(get("/api/camera/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.available").value(true))
                .andExpect(jsonPath("$.pan").value("STOP"))
                .andExpect(jsonPath("$.tilt").value(90.0));
    }

    @Test
    void getCameraStream_mockMode_returns503() throws Exception {
        mockMvc.perform(get("/api/camera/stream"))
                .andExpect(status().isServiceUnavailable());
    }

    @SpringBootTest
    @AutoConfigureMockMvc
    @WithMockUser(roles = "ADMIN")
    static class CameraStreamTest {

        @Autowired
        private MockMvc mockMvc;

        @MockBean
        private RobotGatewayClient robotGatewayClient;

        @Test
        void getCameraStream_preflightSucceeds_returns200WithMjpegContentTypeAndBytes() throws Exception {
            byte[] fakeData = "--frame\r\nContent-Type: image/jpeg\r\n\r\nFAKE_JPEG\r\n".getBytes();
            when(robotGatewayClient.isCameraStreamAvailable()).thenReturn(true);
            when(robotGatewayClient.streamCamera()).thenReturn(outputStream -> outputStream.write(fakeData));

            byte[] body = mockMvc.perform(get("/api/camera/stream"))
                    .andExpect(status().isOk())
                    .andExpect(header().string("Content-Type", org.hamcrest.Matchers.containsString("multipart/x-mixed-replace")))
                    .andReturn()
                    .getResponse()
                    .getContentAsByteArray();

            assertThat(body).isNotEmpty();
            assertThat(new String(body)).contains("FAKE_JPEG");
        }

        @Test
        void getCameraStream_preflightFails_returns503() throws Exception {
            when(robotGatewayClient.isCameraStreamAvailable()).thenReturn(false);

            mockMvc.perform(get("/api/camera/stream"))
                    .andExpect(status().isServiceUnavailable());
        }

        @Test
        void getCameraStream_python503_preflight_returns503() throws Exception {
            when(robotGatewayClient.isCameraStreamAvailable()).thenReturn(false);

            mockMvc.perform(get("/api/camera/stream"))
                    .andExpect(status().isServiceUnavailable());
        }
    }

    @SpringBootTest
    @AutoConfigureMockMvc
    @WithMockUser(roles = "ADMIN")
    static class GpsNullableTest {

        @Autowired
        private MockMvc mockMvc;

        @MockBean
        private RobotGatewayClient robotGatewayClient;

        @Test
        void getGps_nullableCoordinates_returnedSafely() throws Exception {
            when(robotGatewayClient.getGps()).thenReturn(
                    new GpsResponse(null, null, false, LocalDateTime.now())
            );

            mockMvc.perform(get("/api/gps"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.fix").value(false))
                    .andExpect(jsonPath("$.latitude").doesNotExist())
                    .andExpect(jsonPath("$.longitude").doesNotExist());
        }
    }
}
