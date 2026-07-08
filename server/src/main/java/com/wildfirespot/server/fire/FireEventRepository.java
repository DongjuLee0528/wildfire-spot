package com.wildfirespot.server.fire;

import com.wildfirespot.server.device.Device;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface FireEventRepository extends JpaRepository<FireEvent, String> {

    Optional<FireEvent> findTopByDeviceOrderByDetectedAtDesc(Device device);

    List<FireEvent> findAllByDeviceOrderByDetectedAtDesc(Device device);

    List<FireEvent> findAllByDeviceAndFireDetectedTrueOrderByDetectedAtDesc(Device device);
}
