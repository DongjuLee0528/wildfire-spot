package com.wildfirespot.server.sensor;

import com.wildfirespot.server.device.Device;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface SensorRecordRepository extends JpaRepository<SensorRecord, String> {

    Optional<SensorRecord> findTopByDeviceOrderByRecordedAtDesc(Device device);

    List<SensorRecord> findAllByDeviceOrderByRecordedAtDesc(Device device);
}
