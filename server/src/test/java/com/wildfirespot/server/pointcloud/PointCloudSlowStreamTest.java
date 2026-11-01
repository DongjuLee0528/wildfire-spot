package com.wildfirespot.server.pointcloud;

import com.wildfirespot.server.auth.*;
import com.wildfirespot.server.device.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import java.net.Socket;
import java.net.URI;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "server.address=127.0.0.1", "robot.gateway.mode=mock",
        "spring.datasource.url=jdbc:h2:mem:pointcloudslow;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"})
class PointCloudSlowStreamTest {
    @LocalServerPort int port;
    @Autowired UserRepository users;
    @Autowired DeviceRepository devices;
    @Autowired PointCloudStore store;
    @Autowired PointCloudStreams streams;
    @Autowired JwtProvider jwt;
    @org.springframework.beans.factory.annotation.Value("${jwt.secret}") String secret;

    final HttpClient streamClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    record Source(Device device, String token) {}
    Source source(long expirationMs) {
        String name = "expiry-"+UUID.randomUUID();
        User owner = users.save(new User(name, name+"@example.invalid", name, "unused-test-hash", "USER"));
        Device device = devices.save(new Device(owner, "fixture", UUID.randomUUID().toString(), UUID.randomUUID().toString(), "fixture"));
        return new Source(device, new JwtProvider(secret, expirationMs).generate(name, "USER"));
    }
    HttpResponse<java.io.InputStream> stream(Source source) throws Exception {
        return streamClient.send(HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:"+port+"/api/devices/"+source.device.getId()+"/point-cloud/stream"))
                .header("Authorization", "Bearer "+source.token).timeout(Duration.ofSeconds(3)).GET().build(), HttpResponse.BodyHandlers.ofInputStream());
    }
    int eofWithin(java.io.InputStream body, long milliseconds) throws Exception {
        return CompletableFuture.supplyAsync(() -> {
            try { return body.read(); }
            catch (java.io.IOException error) { throw new java.io.UncheckedIOException(error); }
        }).get(milliseconds, TimeUnit.MILLISECONDS);
    }

    @Test void actualJwtExpiryClosesAtFrameBoundaryBeforeUpstreamStaleness() throws Exception {
        Source source = source(2000); byte[] frame = PointCloudStoreTest.fixture(); store.accept(source.device.getId(), frame);
        var updater = java.util.concurrent.Executors.newSingleThreadScheduledExecutor();
        updater.scheduleWithFixedDelay(() -> store.accept(source.device.getId(), frame), 100, 100, TimeUnit.MILLISECONDS);
        try {
            HttpResponse<java.io.InputStream> response = stream(source);
            try (var body = response.body()) {
                assertThat(response.statusCode()).isEqualTo(200); assertThat(body.readNBytes(frame.length)).isEqualTo(frame);
                byte[] remaining = CompletableFuture.supplyAsync(() -> {
                    try { return body.readAllBytes(); }
                    catch (java.io.IOException error) { throw new java.io.UncheckedIOException(error); }
                }).get(4, TimeUnit.SECONDS);
                assertThat(remaining.length % frame.length).isZero();
                assertThat(store.latest(source.device.getId())).isNotNull();
                assertThat(streams.activeCount()).isZero();
            }
        } finally { updater.shutdownNow(); updater.awaitTermination(1, TimeUnit.SECONDS); }
    }

    @Test void upstreamStalenessClosesAndReleasesSlotWithoutLifetimeRotation() throws Exception {
        Source source = source(60000); byte[] frame = PointCloudStoreTest.fixture(); store.accept(source.device.getId(), frame);
        HttpResponse<java.io.InputStream> response = stream(source);
        try (var body = response.body()) {
            assertThat(response.statusCode()).isEqualTo(200); assertThat(body.readNBytes(frame.length)).isEqualTo(frame);
            Thread.sleep(1000); assertThat(streams.activeCount()).isEqualTo(1);
            assertThat(eofWithin(body, 3000)).isEqualTo(-1);
            assertThat(store.latest(source.device.getId())).isNull(); assertThat(streams.activeCount()).isZero();
        }
    }

    @Test void nonReadingClientReleasesSlotWhileHealthyClientReceivesFullFrame() throws Exception {
        String name = "slow-"+UUID.randomUUID();
        User owner = users.save(new User(name, name+"@example.invalid", name, "unused-test-hash", "USER"));
        Device device = devices.save(new Device(owner, "fixture", UUID.randomUUID().toString(), UUID.randomUUID().toString(), "fixture"));
        String token = jwt.generate(name, "USER");
        ByteBuffer buffer = ByteBuffer.allocate(144032).order(ByteOrder.LITTLE_ENDIAN);
        buffer.put(new byte[]{'L','2','P','C'}).putInt(1).putInt(144000).putInt(12000).putDouble(1).putInt(1).putInt(18);
        for (int i=0;i<12000;i++) buffer.putFloat(1).putFloat(2).putFloat(3);
        byte[] frame = buffer.array(); store.accept(device.getId(), frame);
        try (Socket slow = new Socket()) {
            slow.setReceiveBufferSize(1024); slow.setSoTimeout(3000);
            slow.connect(new java.net.InetSocketAddress("127.0.0.1", port), 2000);
            slow.getOutputStream().write(("GET /api/devices/"+device.getId()+"/point-cloud/stream HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer "+token+"\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
            int boundary=0;
            while (boundary != 0x0d0a0d0a) {
                int value=slow.getInputStream().read(); assertThat(value).isNotEqualTo(-1); boundary=(boundary<<8)|value;
            }
            HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
            HttpResponse<java.io.InputStream> healthy = client.send(HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"+port+"/api/devices/"+device.getId()+"/point-cloud/stream"))
                    .header("Authorization", "Bearer "+token).timeout(Duration.ofSeconds(3)).GET().build(), HttpResponse.BodyHandlers.ofInputStream());
            try (var body=healthy.body()) {
                assertThat(healthy.statusCode()).isEqualTo(200);
                byte[] received=CompletableFuture.supplyAsync(() -> {
                    try { return body.readNBytes(frame.length); }
                    catch (java.io.IOException error) { throw new java.io.UncheckedIOException(error); }
                }).get(4, TimeUnit.SECONDS);
                assertThat(received).isEqualTo(frame);
            }
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(12);
            while (streams.activeCount()>0 && System.nanoTime()<deadline) {
                Thread.sleep(60); store.accept(device.getId(), frame);
            }
            assertThat(streams.activeCount()).isZero();
            assertThat(store.latest(device.getId())).isNotNull();
        }
    }
}
