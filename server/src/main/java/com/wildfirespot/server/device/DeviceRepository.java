package com.wildfirespot.server.device;

import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Repository
public class DeviceRepository {

    private final Map<String, Device> store = new ConcurrentHashMap<>();

    public boolean existsBySerialNumber(String serialNumber) {
        return store.values().stream()
                .anyMatch(d -> d.getSerialNumber().equals(serialNumber));
    }

    public boolean existsByDeviceKey(String deviceKey) {
        return store.values().stream()
                .anyMatch(d -> d.getDeviceKey().equals(deviceKey));
    }

    public Device save(String ownerUsername, String name, String serialNumber, String deviceKey, String description) {
        String id = UUID.randomUUID().toString();
        Device device = new Device(id, ownerUsername, name, serialNumber, deviceKey, description);
        store.put(id, device);
        return device;
    }

    public List<Device> findAllByOwner(String ownerUsername) {
        return store.values().stream()
                .filter(d -> d.getOwnerUsername().equals(ownerUsername))
                .toList();
    }

    public Optional<Device> findById(String id) {
        return Optional.ofNullable(store.get(id));
    }

    public void delete(String id) {
        store.remove(id);
    }
}
