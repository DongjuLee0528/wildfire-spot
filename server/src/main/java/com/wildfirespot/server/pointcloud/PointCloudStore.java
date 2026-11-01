package com.wildfirespot.server.pointcloud;

import com.wildfirespot.server.device.DeviceRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

@Service
public class PointCloudStore {
    static final long FRESH_NS = TimeUnit.SECONDS.toNanos(2);
    private static final long TTL_NS = TimeUnit.SECONDS.toNanos(5);
    record Frame(byte[] data, String ownerId, long receivedAt, long verifiedAt) {}
    private final Map<String, Frame> frames = new HashMap<>();
    private final ConcurrentHashMap<String, CompletableFuture<String>> lookups = new ConcurrentHashMap<>();
    private final Semaphore lookupSlots = new Semaphore(16);
    private final DeviceRepository devices;
    final LongSupplier clock;

    @Autowired
    public PointCloudStore(DeviceRepository devices) { this(devices, System::nanoTime); }
    PointCloudStore(DeviceRepository devices, LongSupplier clock) { this.devices = devices; this.clock = clock; }

    private String resolveOwner(String deviceId) {
        CompletableFuture<String> lookup = new CompletableFuture<>();
        CompletableFuture<String> existing = lookups.putIfAbsent(deviceId, lookup);
        if (existing != null) {
            try { return existing.get(1, TimeUnit.SECONDS); }
            catch (Exception error) {
                if (error instanceof InterruptedException) Thread.currentThread().interrupt();
                throw new PointCloudProblem(HttpStatus.SERVICE_UNAVAILABLE);
            }
        }
        if (!lookupSlots.tryAcquire()) {
            lookups.remove(deviceId, lookup);
            lookup.completeExceptionally(new PointCloudProblem(HttpStatus.SERVICE_UNAVAILABLE));
            throw new PointCloudProblem(HttpStatus.SERVICE_UNAVAILABLE);
        }
        try {
            String owner = devices.findOwnerIdByDeviceId(deviceId)
                    .orElseThrow(() -> new PointCloudProblem(HttpStatus.NOT_FOUND));
            lookup.complete(owner);
            return owner;
        } catch (RuntimeException error) {
            lookup.completeExceptionally(error);
            throw error;
        } finally {
            lookups.remove(deviceId, lookup);
            lookupSlots.release();
        }
    }

    public void accept(String deviceId, byte[] data) {
        PointCloudFrame.validate(data);
        long now = clock.getAsLong();
        Frame previous;
        synchronized (this) { previous = frames.get(deviceId); }
        String owner;
        long verified;
        if (previous != null && now - previous.verifiedAt < TTL_NS) {
            owner = previous.ownerId;
            verified = previous.verifiedAt;
        } else {
            owner = resolveOwner(deviceId);
            verified = clock.getAsLong();
        }
        synchronized (this) {
            now = clock.getAsLong();
            prune();
            Frame current = frames.get(deviceId);
            if (current != null && now - current.receivedAt < TimeUnit.MILLISECONDS.toNanos(50))
                throw new PointCloudProblem(HttpStatus.TOO_MANY_REQUESTS);
            if ((current == null || !current.ownerId.equals(owner)) && frames.values().stream().filter(f -> f.ownerId.equals(owner)).count() >= 4)
                throw new PointCloudProblem(HttpStatus.TOO_MANY_REQUESTS);
            if (current == null && frames.size() >= 64) throw new PointCloudProblem(HttpStatus.SERVICE_UNAVAILABLE);
            frames.put(deviceId, new Frame(data.clone(), owner, now, verified));
        }
    }

    synchronized Frame latest(String deviceId) {
        Frame frame = frames.get(deviceId);
        return frame != null && clock.getAsLong() - frame.receivedAt <= FRESH_NS ? frame : null;
    }

    synchronized void prune() {
        long now = clock.getAsLong();
        frames.values().removeIf(frame -> now - frame.receivedAt > TTL_NS);
    }
}
