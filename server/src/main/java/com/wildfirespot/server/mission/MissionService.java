package com.wildfirespot.server.mission;

import com.wildfirespot.server.auth.User;
import com.wildfirespot.server.auth.UserRepository;
import com.wildfirespot.server.device.Device;
import com.wildfirespot.server.device.DeviceRepository;
import com.wildfirespot.server.device.DeviceService;
import com.wildfirespot.server.dto.MissionResponse;
import com.wildfirespot.server.dto.MissionStartRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

@Service
public class MissionService {

    private final MissionRepository missionRepository;
    private final UserRepository userRepository;
    private final DeviceRepository deviceRepository;

    public MissionService(MissionRepository missionRepository,
                          UserRepository userRepository,
                          DeviceRepository deviceRepository) {
        this.missionRepository = missionRepository;
        this.userRepository = userRepository;
        this.deviceRepository = deviceRepository;
    }

    @Transactional
    public MissionResponse start(String username, MissionStartRequest request) {
        User owner = resolveUser(username);
        Device device = resolveOwnedDevice(owner, request.deviceId());
        Mission mission = missionRepository.save(
                new Mission(owner, device, request.missionName(), request.missionType())
        );
        return MissionResponse.from(mission);
    }

    @Transactional
    public MissionResponse finish(String username, String missionId) {
        Mission mission = findAndVerifyOwnership(username, missionId);
        mission.finish();
        return MissionResponse.from(missionRepository.save(mission));
    }

    @Transactional
    public MissionResponse cancel(String username, String missionId) {
        Mission mission = findAndVerifyOwnership(username, missionId);
        mission.cancel();
        return MissionResponse.from(missionRepository.save(mission));
    }

    @Transactional(readOnly = true)
    public List<MissionResponse> listOwned(String username) {
        User owner = resolveUser(username);
        return missionRepository.findAllByOwnerOrderByCreatedAtDesc(owner).stream()
                .map(MissionResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public Optional<MissionResponse> getActive(String username) {
        User owner = resolveUser(username);
        return missionRepository.findTopByOwnerAndStatusOrderByStartedAtDesc(owner, MissionStatus.RUNNING)
                .map(MissionResponse::from);
    }

    private Mission findAndVerifyOwnership(String username, String missionId) {
        Mission mission = missionRepository.findById(missionId)
                .orElseThrow(() -> new MissionNotFoundException("Mission not found: " + missionId));
        if (!mission.getOwner().username().equals(username)) {
            throw new MissionNotFoundException("Mission not found: " + missionId);
        }
        return mission;
    }

    private User resolveUser(String username) {
        return userRepository.findByUsername(username)
                .orElseThrow(() -> new DeviceService.DeviceNotFoundException("User not found: " + username));
    }

    private Device resolveOwnedDevice(User owner, String deviceId) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceService.DeviceNotFoundException("Device not found: " + deviceId));
        if (!device.getOwner().username().equals(owner.username())) {
            throw new DeviceService.DeviceNotFoundException("Device not found: " + deviceId);
        }
        return device;
    }

    public static class MissionNotFoundException extends RuntimeException {
        public MissionNotFoundException(String message) { super(message); }
    }
}
