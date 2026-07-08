package com.wildfirespot.server.controller;

import com.wildfirespot.server.dto.MissionResponse;
import com.wildfirespot.server.dto.MissionStartRequest;
import com.wildfirespot.server.mission.MissionService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/missions")
public class MissionController {

    private final MissionService missionService;

    public MissionController(MissionService missionService) {
        this.missionService = missionService;
    }

    @PostMapping("/start")
    public ResponseEntity<MissionResponse> start(
            @AuthenticationPrincipal String username,
            @Valid @RequestBody MissionStartRequest request
    ) {
        return ResponseEntity.status(HttpStatus.CREATED).body(missionService.start(username, request));
    }

    @PostMapping("/{missionId}/finish")
    public ResponseEntity<MissionResponse> finish(
            @AuthenticationPrincipal String username,
            @PathVariable String missionId
    ) {
        return ResponseEntity.ok(missionService.finish(username, missionId));
    }

    @PostMapping("/{missionId}/cancel")
    public ResponseEntity<MissionResponse> cancel(
            @AuthenticationPrincipal String username,
            @PathVariable String missionId
    ) {
        return ResponseEntity.ok(missionService.cancel(username, missionId));
    }

    @GetMapping
    public ResponseEntity<List<MissionResponse>> list(@AuthenticationPrincipal String username) {
        return ResponseEntity.ok(missionService.listOwned(username));
    }

    @GetMapping("/active")
    public ResponseEntity<MissionResponse> getActive(@AuthenticationPrincipal String username) {
        return missionService.getActive(username)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }
}
