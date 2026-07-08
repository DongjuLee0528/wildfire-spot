package com.wildfirespot.server.mission;

import com.wildfirespot.server.auth.User;
import com.wildfirespot.server.device.Device;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface MissionRepository extends JpaRepository<Mission, String> {
    List<Mission> findAllByOwnerOrderByCreatedAtDesc(User owner);
    Optional<Mission> findTopByDeviceAndStatusOrderByStartedAtDesc(Device device, MissionStatus status);
    Optional<Mission> findTopByOwnerAndStatusOrderByStartedAtDesc(User owner, MissionStatus status);
}
