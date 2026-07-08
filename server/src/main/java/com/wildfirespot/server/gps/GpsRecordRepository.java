package com.wildfirespot.server.gps;

import com.wildfirespot.server.device.Device;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface GpsRecordRepository extends JpaRepository<GpsRecord, String> {

    Optional<GpsRecord> findTopByDeviceOrderByRecordedAtDesc(Device device);

    List<GpsRecord> findAllByDeviceOrderByRecordedAtDesc(Device device);
}
