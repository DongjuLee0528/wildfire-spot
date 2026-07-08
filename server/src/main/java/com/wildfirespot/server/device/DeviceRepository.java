package com.wildfirespot.server.device;

import com.wildfirespot.server.auth.User;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface DeviceRepository extends JpaRepository<Device, String> {

    boolean existsBySerialNumber(String serialNumber);

    List<Device> findAllByOwner(User owner);

    Optional<Device> findBySerialNumber(String serialNumber);
}
