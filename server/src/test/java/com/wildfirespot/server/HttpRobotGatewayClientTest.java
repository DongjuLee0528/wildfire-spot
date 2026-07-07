package com.wildfirespot.server;

import com.wildfirespot.server.common.CameraCommand;
import com.wildfirespot.server.common.ControlCommand;
import com.wildfirespot.server.common.RobotMode;
import com.wildfirespot.server.dto.CameraControlResponse;
import com.wildfirespot.server.dto.CameraStatusResponse;
import com.wildfirespot.server.dto.ControlResponse;
import com.wildfirespot.server.dto.FireStatusResponse;
import com.wildfirespot.server.dto.GpsResponse;
import com.wildfirespot.server.dto.MissionPointResponse;
import com.wildfirespot.server.dto.MissionZoneResetResponse;
import com.wildfirespot.server.dto.MissionZoneResponse;
import com.wildfirespot.server.dto.ModeResponse;
import com.wildfirespot.server.gateway.HttpRobotGatewayClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.io.ByteArrayOutputStream;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class HttpRobotGatewayClientTest {

    private MockRestServiceServer mockServer;
    private HttpRobotGatewayClient client;

    @BeforeEach
    void setUp() {
        org.springframework.web.client.RestTemplate restTemplate =
                new org.springframework.web.client.RestTemplate();
        mockServer = MockRestServiceServer.createServer(restTemplate);
        RestClient restClient = RestClient.create(restTemplate);
        client = new HttpRobotGatewayClient(restClient);
    }

    @Test
    void sendControlCommand_forwardsToRobotControlEndpoint() {
        mockServer.expect(requestTo("/robot/control"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("\"command\":\"FORWARD\"")))
                .andRespond(withSuccess(
                        "{\"accepted\":true,\"command\":\"FORWARD\"}",
                        MediaType.APPLICATION_JSON
                ));

        ControlResponse result = client.sendControlCommand(ControlCommand.FORWARD);

        assertThat(result.accepted()).isTrue();
        assertThat(result.command()).isEqualTo("FORWARD");
        mockServer.verify();
    }

    @Test
    void changeMode_forwardsToRobotModeEndpoint() {
        mockServer.expect(requestTo("/robot/mode"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("\"mode\":\"MANUAL\"")))
                .andRespond(withSuccess(
                        "{\"accepted\":true,\"mode\":\"MANUAL\"}",
                        MediaType.APPLICATION_JSON
                ));

        ModeResponse result = client.changeMode(RobotMode.MANUAL);

        assertThat(result.accepted()).isTrue();
        assertThat(result.mode()).isEqualTo("MANUAL");
        mockServer.verify();
    }

    @Test
    void sendControlCommand_pythonUnavailable_returnsFallback() {
        mockServer.expect(requestTo("/robot/control"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withServerError());

        ControlResponse result = client.sendControlCommand(ControlCommand.STOP);

        assertThat(result.accepted()).isFalse();
        assertThat(result.command()).isEqualTo("STOP");
    }

    @Test
    void changeMode_pythonUnavailable_returnsFallback() {
        mockServer.expect(requestTo("/robot/mode"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withServerError());

        ModeResponse result = client.changeMode(RobotMode.AUTO);

        assertThat(result.accepted()).isFalse();
        assertThat(result.mode()).isEqualTo("AUTO");
    }

    @Test
    void getGps_nullCoordinates_returnedSafely() {
        mockServer.expect(requestTo("/robot/gps"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"latitude\":null,\"longitude\":null,\"fix\":false,\"updatedAt\":\"2026-07-03T20:00:00\"}",
                        MediaType.APPLICATION_JSON
                ));

        GpsResponse result = client.getGps();

        assertThat(result.fix()).isFalse();
        assertThat(result.latitude()).isNull();
        assertThat(result.longitude()).isNull();
    }

    @Test
    void getGps_pythonUnavailable_returnsFallbackWithNullCoordinates() {
        mockServer.expect(requestTo("/robot/gps"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withServerError());

        GpsResponse result = client.getGps();

        assertThat(result.fix()).isFalse();
        assertThat(result.latitude()).isNull();
        assertThat(result.longitude()).isNull();
    }

    @Test
    void getFireStatus_pythonUnavailable_returnsFallbackNormal() {
        mockServer.expect(requestTo("/robot/fire/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withServerError());

        FireStatusResponse result = client.getFireStatus();

        assertThat(result.state()).isEqualTo("NORMAL");
        assertThat(result.suspected()).isFalse();
        assertThat(result.verified()).isFalse();
        assertThat(result.latestAlertEvent()).isNull();
        assertThat(result.latestReportEvent()).isNull();
    }

    @Test
    void getFireStatus_allContractFieldsDeserialized() {
        mockServer.expect(requestTo("/robot/fire/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"state\":\"SUSPECTED_FIRE\",\"suspected\":true,\"verified\":false,"
                        + "\"cameraDetected\":true,\"sensorDetected\":false,"
                        + "\"latestAlertEvent\":null,\"latestReportEvent\":null}",
                        MediaType.APPLICATION_JSON
                ));

        FireStatusResponse result = client.getFireStatus();

        assertThat(result.state()).isEqualTo("SUSPECTED_FIRE");
        assertThat(result.suspected()).isTrue();
        assertThat(result.verified()).isFalse();
        assertThat(result.cameraDetected()).isTrue();
        assertThat(result.sensorDetected()).isFalse();
        assertThat(result.latestAlertEvent()).isNull();
        assertThat(result.latestReportEvent()).isNull();
    }

    @Test
    void getFireStatus_alertEvent_payloadDeserializedIntoMap() {
        mockServer.expect(requestTo("/robot/fire/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"state\":\"SUSPECTED_FIRE\",\"suspected\":true,\"verified\":false,"
                        + "\"cameraDetected\":true,\"sensorDetected\":false,"
                        + "\"latestAlertEvent\":{"
                        + "\"state\":\"DetectionState.SUSPECTED_FIRE\","
                        + "\"timestamp\":1234567890.123,"
                        + "\"latitude\":37.1,"
                        + "\"longitude\":127.1,"
                        + "\"smoke\":450.0,"
                        + "\"temperature\":35.0,"
                        + "\"humidity\":30.0,"
                        + "\"flame\":{\"front_left\":true,\"front_right\":false,\"left\":false,\"right\":false},"
                        + "\"camera_detected\":true,"
                        + "\"camera_result\":{\"detected\":true,\"confidence\":0.91},"
                        + "\"verification_reason\":\"camera+mq2\","
                        + "\"image_path\":\"/tmp/img.jpg\""
                        + "},"
                        + "\"latestReportEvent\":null}",
                        MediaType.APPLICATION_JSON
                ));

        FireStatusResponse result = client.getFireStatus();

        assertThat(result.latestAlertEvent()).isNotNull();
        assertThat(result.latestAlertEvent()).containsKey("state");
        assertThat(result.latestAlertEvent()).containsKey("timestamp");
        assertThat(result.latestAlertEvent()).containsKey("latitude");
        assertThat(result.latestAlertEvent()).containsKey("longitude");
        assertThat(result.latestAlertEvent()).containsKey("smoke");
        assertThat(result.latestAlertEvent()).containsKey("temperature");
        assertThat(result.latestAlertEvent()).containsKey("humidity");
        assertThat(result.latestAlertEvent()).containsKey("flame");
        assertThat(result.latestAlertEvent()).containsKey("camera_detected");
        assertThat(result.latestAlertEvent()).containsKey("camera_result");
        assertThat(result.latestAlertEvent()).containsKey("verification_reason");
        assertThat(result.latestAlertEvent()).containsKey("image_path");
        assertThat(result.latestAlertEvent().get("verification_reason")).isEqualTo("camera+mq2");
        assertThat(result.latestAlertEvent().get("camera_detected")).isEqualTo(true);
        assertThat(result.latestAlertEvent().get("image_path")).isEqualTo("/tmp/img.jpg");

        @SuppressWarnings("unchecked")
        Map<String, Object> cameraResult = (Map<String, Object>) result.latestAlertEvent().get("camera_result");
        assertThat(cameraResult).isNotNull();
        assertThat(cameraResult.get("detected")).isEqualTo(true);
        assertThat(cameraResult.get("confidence")).isEqualTo(0.91);

        @SuppressWarnings("unchecked")
        Map<String, Object> flame = (Map<String, Object>) result.latestAlertEvent().get("flame");
        assertThat(flame).isNotNull();
        assertThat(flame.get("front_left")).isEqualTo(true);
        assertThat(flame.get("front_right")).isEqualTo(false);
        assertThat(flame.get("left")).isEqualTo(false);
        assertThat(flame.get("right")).isEqualTo(false);

        assertThat(result.latestReportEvent()).isNull();
    }

    @Test
    void getFireStatus_reportEvent_payloadDeserializedIntoMap() {
        mockServer.expect(requestTo("/robot/fire/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"state\":\"VERIFIED_FIRE\",\"suspected\":true,\"verified\":true,"
                        + "\"cameraDetected\":true,\"sensorDetected\":true,"
                        + "\"latestAlertEvent\":null,"
                        + "\"latestReportEvent\":{"
                        + "\"state\":\"DetectionState.VERIFIED_FIRE\","
                        + "\"timestamp\":1234567890.123,"
                        + "\"report_timestamp\":1234567900.0,"
                        + "\"latitude\":37.1,"
                        + "\"longitude\":127.1,"
                        + "\"smoke\":500.0,"
                        + "\"temperature\":38.0,"
                        + "\"humidity\":25.0,"
                        + "\"flame\":{\"front_left\":true},"
                        + "\"camera_detected\":true,"
                        + "\"camera_result\":{\"detected\":true,\"confidence\":0.95},"
                        + "\"verification_reason\":\"camera+mq2+ky026\","
                        + "\"image_path\":null"
                        + "}}",
                        MediaType.APPLICATION_JSON
                ));

        FireStatusResponse result = client.getFireStatus();

        assertThat(result.latestReportEvent()).isNotNull();
        assertThat(result.latestReportEvent()).containsKey("state");
        assertThat(result.latestReportEvent()).containsKey("timestamp");
        assertThat(result.latestReportEvent()).containsKey("report_timestamp");
        assertThat(result.latestReportEvent()).containsKey("latitude");
        assertThat(result.latestReportEvent()).containsKey("longitude");
        assertThat(result.latestReportEvent()).containsKey("verification_reason");
        assertThat(result.latestReportEvent()).containsKey("image_path");
        assertThat(result.latestReportEvent().get("verification_reason")).isEqualTo("camera+mq2+ky026");
        assertThat(result.latestReportEvent().get("report_timestamp")).isEqualTo(1234567900.0);
        assertThat(result.latestReportEvent().get("image_path")).isNull();

        @SuppressWarnings("unchecked")
        Map<String, Object> reportCameraResult = (Map<String, Object>) result.latestReportEvent().get("camera_result");
        assertThat(reportCameraResult).isNotNull();
        assertThat(reportCameraResult.get("detected")).isEqualTo(true);
        assertThat(reportCameraResult.get("confidence")).isEqualTo(0.95);

        @SuppressWarnings("unchecked")
        Map<String, Object> reportFlame = (Map<String, Object>) result.latestReportEvent().get("flame");
        assertThat(reportFlame).isNotNull();
        assertThat(reportFlame.get("front_left")).isEqualTo(true);

        assertThat(result.latestAlertEvent()).isNull();
    }

    @Test
    void getFireStatus_alertEvent_nullableFieldsHandledSafely() {
        mockServer.expect(requestTo("/robot/fire/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"state\":\"SUSPECTED_FIRE\",\"suspected\":true,\"verified\":false,"
                        + "\"cameraDetected\":false,\"sensorDetected\":true,"
                        + "\"latestAlertEvent\":{"
                        + "\"state\":\"DetectionState.SUSPECTED_FIRE\","
                        + "\"timestamp\":1234567890.0,"
                        + "\"latitude\":null,"
                        + "\"longitude\":null,"
                        + "\"smoke\":460.0,"
                        + "\"temperature\":33.0,"
                        + "\"humidity\":28.0,"
                        + "\"flame\":{},"
                        + "\"camera_detected\":false,"
                        + "\"camera_result\":null,"
                        + "\"verification_reason\":\"mq2\","
                        + "\"image_path\":null"
                        + "},"
                        + "\"latestReportEvent\":null}",
                        MediaType.APPLICATION_JSON
                ));

        FireStatusResponse result = client.getFireStatus();

        assertThat(result.latestAlertEvent()).isNotNull();
        assertThat(result.latestAlertEvent().get("latitude")).isNull();
        assertThat(result.latestAlertEvent().get("longitude")).isNull();
        assertThat(result.latestAlertEvent().get("camera_result")).isNull();
        assertThat(result.latestAlertEvent().get("image_path")).isNull();
        assertThat(result.latestAlertEvent().get("verification_reason")).isEqualTo("mq2");
    }

    @Test
    void getFireStatus_alertEvent_missingOptionalFields_deserializationSucceeds() {
        mockServer.expect(requestTo("/robot/fire/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"state\":\"SUSPECTED_FIRE\",\"suspected\":true,\"verified\":false,"
                        + "\"cameraDetected\":true,\"sensorDetected\":false,"
                        + "\"latestAlertEvent\":{"
                        + "\"timestamp\":1234567890.0,"
                        + "\"reason\":\"camera_detected\""
                        + "},"
                        + "\"latestReportEvent\":null}",
                        MediaType.APPLICATION_JSON
                ));

        FireStatusResponse result = client.getFireStatus();

        assertThat(result.latestAlertEvent()).isNotNull();
        assertThat(result.latestAlertEvent().get("timestamp")).isEqualTo(1234567890.0);
        assertThat(result.latestAlertEvent().get("reason")).isEqualTo("camera_detected");
        assertThat(result.latestAlertEvent().containsKey("latitude")).isFalse();
        assertThat(result.latestAlertEvent().containsKey("longitude")).isFalse();
        assertThat(result.latestAlertEvent().containsKey("camera_result")).isFalse();
        assertThat(result.latestAlertEvent().containsKey("flame")).isFalse();
        assertThat(result.latestReportEvent()).isNull();
    }

    @Test
    void getFireStatus_reportEvent_missingOptionalFields_deserializationSucceeds() {
        mockServer.expect(requestTo("/robot/fire/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"state\":\"VERIFIED_FIRE\",\"suspected\":true,\"verified\":true,"
                        + "\"cameraDetected\":false,\"sensorDetected\":true,"
                        + "\"latestAlertEvent\":null,"
                        + "\"latestReportEvent\":{"
                        + "\"timestamp\":1234567890.0,"
                        + "\"report_timestamp\":1234567900.0"
                        + "}}",
                        MediaType.APPLICATION_JSON
                ));

        FireStatusResponse result = client.getFireStatus();

        assertThat(result.latestReportEvent()).isNotNull();
        assertThat(result.latestReportEvent().get("timestamp")).isEqualTo(1234567890.0);
        assertThat(result.latestReportEvent().get("report_timestamp")).isEqualTo(1234567900.0);
        assertThat(result.latestReportEvent().containsKey("latitude")).isFalse();
        assertThat(result.latestReportEvent().containsKey("camera_result")).isFalse();
        assertThat(result.latestReportEvent().containsKey("flame")).isFalse();
        assertThat(result.latestAlertEvent()).isNull();
    }

    @Test
    void getFireStatus_unknownExtraFields_doNotBreakDeserialization() {
        mockServer.expect(requestTo("/robot/fire/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"state\":\"SUSPECTED_FIRE\",\"suspected\":true,\"verified\":false,"
                        + "\"cameraDetected\":true,\"sensorDetected\":false,"
                        + "\"unknownTopLevelField\":\"should_be_ignored\","
                        + "\"latestAlertEvent\":{"
                        + "\"state\":\"DetectionState.SUSPECTED_FIRE\","
                        + "\"timestamp\":1234567890.0,"
                        + "\"latitude\":37.1,"
                        + "\"longitude\":127.1,"
                        + "\"smoke\":400.0,"
                        + "\"temperature\":32.0,"
                        + "\"humidity\":35.0,"
                        + "\"flame\":{},"
                        + "\"camera_detected\":true,"
                        + "\"camera_result\":null,"
                        + "\"verification_reason\":\"camera\","
                        + "\"image_path\":null,"
                        + "\"future_unknown_field\":\"ignored\""
                        + "},"
                        + "\"latestReportEvent\":null}",
                        MediaType.APPLICATION_JSON
                ));

        FireStatusResponse result = client.getFireStatus();

        assertThat(result.state()).isEqualTo("SUSPECTED_FIRE");
        assertThat(result.latestAlertEvent()).isNotNull();
        assertThat(result.latestAlertEvent().get("verification_reason")).isEqualTo("camera");
    }

    @Test
    void getMissionZone_pythonUnavailable_returnsFallbackEmptyList() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withServerError());

        MissionZoneResponse result = client.getMissionZone();

        assertThat(result.points()).isEmpty();
        assertThat(result.pointCount()).isEqualTo(0);
    }

    @Test
    void getMissionZone_pointsDeserializedCorrectly() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"points\":[{\"latitude\":37.1,\"longitude\":127.1},{\"latitude\":37.2,\"longitude\":127.2}],\"ready\":true}",
                        MediaType.APPLICATION_JSON
                ));

        MissionZoneResponse result = client.getMissionZone();

        assertThat(result.points()).hasSize(2);
        assertThat(result.pointCount()).isEqualTo(2);
        assertThat(result.points().get(0).latitude()).isEqualTo(37.1);
        assertThat(result.points().get(0).longitude()).isEqualTo(127.1);
        assertThat(result.points().get(1).latitude()).isEqualTo(37.2);
        assertThat(result.points().get(1).longitude()).isEqualTo(127.2);
    }

    @Test
    void getMissionZone_emptyPoints_returnedCorrectly() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"points\":[],\"ready\":false}",
                        MediaType.APPLICATION_JSON
                ));

        MissionZoneResponse result = client.getMissionZone();

        assertThat(result.points()).isEmpty();
        assertThat(result.pointCount()).isEqualTo(0);
    }

    @Test
    void addMissionZonePoint_forwardsToRobotEndpoint() {
        mockServer.expect(requestTo("/robot/mission/zone/points"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("\"latitude\"")))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("\"longitude\"")))
                .andRespond(withSuccess(
                        "{\"accepted\":true,\"latitude\":37.5,\"longitude\":127.0}",
                        MediaType.APPLICATION_JSON
                ));

        MissionPointResponse result = client.addMissionZonePoint(37.5, 127.0);

        assertThat(result.accepted()).isTrue();
        assertThat(result.latitude()).isEqualTo(37.5);
        assertThat(result.longitude()).isEqualTo(127.0);
        mockServer.verify();
    }

    @Test
    void addMissionZonePoint_pythonUnavailable_returnsFallback() {
        mockServer.expect(requestTo("/robot/mission/zone/points"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withServerError());

        MissionPointResponse result = client.addMissionZonePoint(37.5, 127.0);

        assertThat(result.accepted()).isFalse();
        assertThat(result.latitude()).isEqualTo(37.5);
        assertThat(result.longitude()).isEqualTo(127.0);
    }

    @Test
    void resetMissionZone_forwardsToRobotEndpoint() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.DELETE))
                .andRespond(withSuccess(
                        "{\"accepted\":true}",
                        MediaType.APPLICATION_JSON
                ));

        MissionZoneResetResponse result = client.resetMissionZone();

        assertThat(result.accepted()).isTrue();
        mockServer.verify();
    }

    @Test
    void resetMissionZone_pythonUnavailable_returnsFallback() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.DELETE))
                .andRespond(withServerError());

        MissionZoneResetResponse result = client.resetMissionZone();

        assertThat(result.accepted()).isFalse();
    }

    @Test
    void getMissionZone_pointsContainsNullElement_skipsNullReturnsValidOnly() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"points\":[{\"latitude\":37.1,\"longitude\":127.1},null,{\"latitude\":37.2,\"longitude\":127.2}],\"ready\":true}",
                        MediaType.APPLICATION_JSON
                ));

        MissionZoneResponse result = client.getMissionZone();

        assertThat(result.points()).hasSize(2);
        assertThat(result.pointCount()).isEqualTo(2);
        assertThat(result.points().get(0).latitude()).isEqualTo(37.1);
        assertThat(result.points().get(1).latitude()).isEqualTo(37.2);
    }

    @Test
    void getMissionZone_pointHasNullLatitude_skipsInvalidPoint() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"points\":[{\"latitude\":null,\"longitude\":127.1},{\"latitude\":37.2,\"longitude\":127.2}],\"ready\":true}",
                        MediaType.APPLICATION_JSON
                ));

        MissionZoneResponse result = client.getMissionZone();

        assertThat(result.points()).hasSize(1);
        assertThat(result.pointCount()).isEqualTo(1);
        assertThat(result.points().get(0).latitude()).isEqualTo(37.2);
    }

    @Test
    void getMissionZone_pointHasNullLongitude_skipsInvalidPoint() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"points\":[{\"latitude\":37.1,\"longitude\":null},{\"latitude\":37.2,\"longitude\":127.2}],\"ready\":true}",
                        MediaType.APPLICATION_JSON
                ));

        MissionZoneResponse result = client.getMissionZone();

        assertThat(result.points()).hasSize(1);
        assertThat(result.pointCount()).isEqualTo(1);
        assertThat(result.points().get(0).longitude()).isEqualTo(127.2);
    }

    @Test
    void getMissionZone_allPointsInvalid_returnsEmptyZone() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"points\":[{\"latitude\":null,\"longitude\":null},{\"latitude\":null,\"longitude\":127.1}],\"ready\":false}",
                        MediaType.APPLICATION_JSON
                ));

        MissionZoneResponse result = client.getMissionZone();

        assertThat(result.points()).isEmpty();
        assertThat(result.pointCount()).isEqualTo(0);
    }

    @Test
    void getMissionZone_pointCountMatchesSanitizedValidPoints() {
        mockServer.expect(requestTo("/robot/mission/zone"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"points\":[{\"latitude\":37.1,\"longitude\":127.1},null,{\"latitude\":null,\"longitude\":127.2},{\"latitude\":37.3,\"longitude\":127.3}],\"ready\":true}",
                        MediaType.APPLICATION_JSON
                ));

        MissionZoneResponse result = client.getMissionZone();

        assertThat(result.points()).hasSize(2);
        assertThat(result.pointCount()).isEqualTo(result.points().size());
    }

    @Test
    void sendCameraCommand_forwardsToRobotCameraControlEndpoint() {
        mockServer.expect(requestTo("/robot/camera/control"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("\"command\":\"CAMERA_LEFT\"")))
                .andRespond(withSuccess(
                        "{\"accepted\":true,\"command\":\"CAMERA_LEFT\",\"reason\":\"ok\",\"position\":{\"pan\":\"LEFT\",\"tilt\":90.0}}",
                        MediaType.APPLICATION_JSON
                ));

        CameraControlResponse result = client.sendCameraCommand(CameraCommand.CAMERA_LEFT);

        assertThat(result.accepted()).isTrue();
        assertThat(result.command()).isEqualTo("CAMERA_LEFT");
        assertThat(result.reason()).isEqualTo("ok");
        assertThat(result.position()).isNotNull();
        assertThat(result.position().pan()).isEqualTo("LEFT");
        assertThat(result.position().tilt()).isEqualTo(90.0);
        mockServer.verify();
    }

    @Test
    void sendCameraCommand_pythonUnavailable_returnsFallback() {
        mockServer.expect(requestTo("/robot/camera/control"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withServerError());

        CameraControlResponse result = client.sendCameraCommand(CameraCommand.CAMERA_STOP);

        assertThat(result.accepted()).isFalse();
        assertThat(result.command()).isEqualTo("CAMERA_STOP");
        assertThat(result.reason()).isEqualTo("robot_api_unavailable");
        assertThat(result.position()).isNotNull();
        assertThat(result.position().pan()).isEqualTo("STOP");
        assertThat(result.position().tilt()).isNull();
    }

    @Test
    void getCameraStatus_forwardsToRobotCameraStatusEndpoint() {
        mockServer.expect(requestTo("/robot/camera/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"available\":true,\"pan\":\"STOP\",\"tilt\":90.0}",
                        MediaType.APPLICATION_JSON
                ));

        CameraStatusResponse result = client.getCameraStatus();

        assertThat(result.available()).isTrue();
        assertThat(result.pan()).isEqualTo("STOP");
        assertThat(result.tilt()).isEqualTo(90.0);
        mockServer.verify();
    }

    @Test
    void getCameraStatus_pythonUnavailable_returnsFallback() {
        mockServer.expect(requestTo("/robot/camera/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withServerError());

        CameraStatusResponse result = client.getCameraStatus();

        assertThat(result.available()).isFalse();
        assertThat(result.pan()).isEqualTo("STOP");
        assertThat(result.tilt()).isNull();
    }

    @Test
    void getCameraStatus_tiltNullable_returnedSafely() {
        mockServer.expect(requestTo("/robot/camera/status"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"available\":false,\"pan\":\"STOP\",\"tilt\":null}",
                        MediaType.APPLICATION_JSON
                ));

        CameraStatusResponse result = client.getCameraStatus();

        assertThat(result.available()).isFalse();
        assertThat(result.pan()).isEqualTo("STOP");
        assertThat(result.tilt()).isNull();
    }

    @Test
    void isCameraStreamAvailable_python2xx_returnsTrue() {
        mockServer.expect(requestTo("/robot/camera/stream"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "--frame\r\nContent-Type: image/jpeg\r\n\r\nDATA\r\n",
                        MediaType.parseMediaType("multipart/x-mixed-replace; boundary=frame")
                ));

        assertThat(client.isCameraStreamAvailable()).isTrue();
        mockServer.verify();
    }

    @Test
    void isCameraStreamAvailable_python503_returnsFalse() {
        mockServer.expect(requestTo("/robot/camera/stream"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE)
                        .body("{\"error\":\"stream_unavailable\"}")
                        .contentType(MediaType.APPLICATION_JSON));

        assertThat(client.isCameraStreamAvailable()).isFalse();
        mockServer.verify();
    }

    @Test
    void isCameraStreamAvailable_pythonUnavailable_returnsFalse() {
        mockServer.expect(requestTo("/robot/camera/stream"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withServerError());

        assertThat(client.isCameraStreamAvailable()).isFalse();
        mockServer.verify();
    }

    @Test
    void streamCamera_pythonAvailable_bytesActuallyReadable() throws Exception {
        String mjpegData = "--frame\r\nContent-Type: image/jpeg\r\n\r\nFAKE_JPEG_DATA\r\n";
        mockServer.expect(requestTo("/robot/camera/stream"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        mjpegData,
                        MediaType.parseMediaType("multipart/x-mixed-replace; boundary=frame")
                ));

        org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody body = client.streamCamera();
        assertThat(body).isNotNull();

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        body.writeTo(out);

        assertThat(out.toByteArray()).isNotEmpty();
        assertThat(out.toString()).contains("FAKE_JPEG_DATA");
        mockServer.verify();
    }

    @Test
    void streamCamera_pythonUnavailable_bodyThrowsIOException() {
        mockServer.expect(requestTo("/robot/camera/stream"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withServerError());

        org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody body = client.streamCamera();
        assertThat(body).isNotNull();

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        org.assertj.core.api.ThrowableAssert.ThrowingCallable call = () -> body.writeTo(out);
        org.assertj.core.api.Assertions.assertThatThrownBy(call)
                .isInstanceOf(java.io.IOException.class);
    }

    @Test
    void streamCamera_python503_bodyThrowsIOException() throws Exception {
        mockServer.expect(requestTo("/robot/camera/stream"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE)
                        .body("{\"error\":\"stream_unavailable\"}")
                        .contentType(MediaType.APPLICATION_JSON));

        org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody body = client.streamCamera();
        assertThat(body).isNotNull();

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        org.assertj.core.api.ThrowableAssert.ThrowingCallable call = () -> body.writeTo(out);
        org.assertj.core.api.Assertions.assertThatThrownBy(call)
                .isInstanceOf(java.io.IOException.class)
                .hasMessageContaining("503");
    }
}
