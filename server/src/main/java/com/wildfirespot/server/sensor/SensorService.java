package com.wildfirespot.server.sensor;

import com.wildfirespot.server.device.Device;
import com.wildfirespot.server.device.DeviceRepository;
import com.wildfirespot.server.device.DeviceService;
import com.wildfirespot.server.dto.SensorRecordResponse;
import com.wildfirespot.server.dto.SensorUploadRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.Optional;

@Service
public class SensorService {

    private final DeviceRepository deviceRepository;
    private final SensorRecordRepository sensorRecordRepository;

    public SensorService(DeviceRepository deviceRepository,
                         SensorRecordRepository sensorRecordRepository) {
        this.deviceRepository = deviceRepository;
        this.sensorRecordRepository = sensorRecordRepository;
    }

    @Transactional
    public SensorRecordResponse upload(String deviceId, SensorUploadRequest request) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceService.DeviceNotFoundException("Device not found: " + deviceId));

        LocalDateTime recordedAt = request.recordedAt() != null
                ? request.recordedAt()
                : LocalDateTime.now();

        SensorRecord record = sensorRecordRepository.save(new SensorRecord(
                device,
                request.temperature(),
                request.humidity(),
                request.smokeLevel(),
                request.gasLevel(),
                request.flameDetected(),
                recordedAt
        ));
        return SensorRecordResponse.from(record);
    }

    @Transactional(readOnly = true)
    public Optional<SensorRecordResponse> getLatestForOwner(String username, String deviceId) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceService.DeviceNotFoundException("Device not found: " + deviceId));

        if (!device.getOwner().username().equals(username)) {
            throw new DeviceService.DeviceNotFoundException("Device not found: " + deviceId);
        }

        return sensorRecordRepository.findTopByDeviceOrderByRecordedAtDesc(device)
                .map(SensorRecordResponse::from);
    }
}
