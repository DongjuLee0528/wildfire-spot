package com.wildfirespot.server;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
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
                .andExpect(jsonPath("$.robotCore").value(true));
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
    void getFireStatus_returns200() throws Exception {
        mockMvc.perform(get("/api/fire/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.hardwareConfirmed").value(true))
                .andExpect(jsonPath("$.finalConfirmedFire").value(false));
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
}
