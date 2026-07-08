package com.wildfirespot.server.gps;

import com.wildfirespot.server.auth.UserRepository;
import com.wildfirespot.server.device.Device;
import com.wildfirespot.server.device.DeviceRepository;
import com.wildfirespot.server.device.DeviceService;
import com.wildfirespot.server.dto.GpsRecordResponse;
import com.wildfirespot.server.dto.GpsUploadRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.Optional;

@Service
public class GpsService {

    private final DeviceRepository deviceRepository;
    private final UserRepository userRepository;
    private final GpsRecordRepository gpsRecordRepository;

    public GpsService(DeviceRepository deviceRepository,
                      UserRepository userRepository,
                      GpsRecordRepository gpsRecordRepository) {
        this.deviceRepository = deviceRepository;
        this.userRepository = userRepository;
        this.gpsRecordRepository = gpsRecordRepository;
    }

    @Transactional
    public GpsRecordResponse upload(String deviceId, GpsUploadRequest request) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceService.DeviceNotFoundException("Device not found: " + deviceId));

        LocalDateTime recordedAt = request.recordedAt() != null
                ? request.recordedAt()
                : LocalDateTime.now();

        GpsRecord record = gpsRecordRepository.save(new GpsRecord(
                device,
                request.latitude(),
                request.longitude(),
                request.altitude(),
                request.speed(),
                request.heading(),
                recordedAt
        ));
        return GpsRecordResponse.from(record);
    }

    @Transactional(readOnly = true)
    public Optional<GpsRecordResponse> getLatestForOwner(String username, String deviceId) {
        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() -> new DeviceService.DeviceNotFoundException("Device not found: " + deviceId));

        if (!device.getOwner().username().equals(username)) {
            throw new DeviceService.DeviceNotFoundException("Device not found: " + deviceId);
        }

        return gpsRecordRepository.findTopByDeviceOrderByRecordedAtDesc(device)
                .map(GpsRecordResponse::from);
    }
}
