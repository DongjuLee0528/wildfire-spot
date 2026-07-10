package com.wildfirespot.server.device;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface DeviceStatusRepository extends JpaRepository<DeviceStatus, String> {

    Optional<DeviceStatus> findByDevice(Device device);

    Optional<DeviceStatus> findTopByDeviceOrderByUpdatedAtDesc(Device device);
}
