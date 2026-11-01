package com.wildfirespot.server.pointcloud;

import com.wildfirespot.server.auth.*;
import com.wildfirespot.server.device.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.mock.mockito.SpyBean;
import org.springframework.dao.DataAccessResourceFailureException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.UUID;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "server.address=127.0.0.1", "point-cloud.stream-lifetime-ms=500", "robot.gateway.mode=mock",
        "spring.datasource.url=jdbc:h2:mem:pointcloud;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"})
class PointCloudHttpTest {
    @LocalServerPort int port;
    @Autowired UserRepository users;
    @SpyBean DeviceRepository devices;
    @Autowired JwtProvider jwt;
    @Autowired DeviceTokenProvider tokens;
    @Autowired PointCloudStreams streams;
    @SpyBean DeviceService deviceService;
    final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    User owner, other;
    Device device;
    String ownerToken, otherToken, deviceToken;

    User user() {
        String name = "cloud-" + UUID.randomUUID();
        return users.save(new User(name, name+"@example.invalid", name, "unused-test-hash", "USER"));
    }
    Device device(User user) {
        return devices.save(new Device(user, "fixture", UUID.randomUUID().toString(), UUID.randomUUID().toString(), "test fixture"));
    }
    @BeforeEach void setup() {
        owner = user(); other = user(); device = device(owner);
        ownerToken = jwt.generate(owner.username(), "USER"); otherToken = jwt.generate(other.username(), "USER");
        deviceToken = tokens.generate(device.getId(), device.getSerialNumber());
    }
    HttpRequest.Builder request(String path, String token) {
        HttpRequest.Builder request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+path)).timeout(Duration.ofSeconds(4));
        if (token != null) request.header("Authorization", "Bearer "+token);
        return request;
    }
    int upload(String token, byte[] bytes, String type) throws Exception {
        return client.send(request("/api/device/point-cloud", token).header("Content-Type", type)
                .POST(HttpRequest.BodyPublishers.ofByteArray(bytes)).build(), HttpResponse.BodyHandlers.discarding()).statusCode();
    }
    HttpResponse<InputStream> stream(String token, String id) throws Exception {
        return client.send(request("/api/devices/"+id+"/point-cloud/stream", token).GET().build(), HttpResponse.BodyHandlers.ofInputStream());
    }
    @AfterEach void awaitCleanup() throws Exception {
        long end = System.nanoTime()+Duration.ofSeconds(3).toNanos();
        while (streams.activeCount() != 0 && System.nanoTime() < end) Thread.sleep(20);
        assertThat(streams.activeCount()).isZero();
    }
    @Test void exactBinarySmallFrameFlushAndCleanRotationAtQuota() throws Exception {
        byte[] bytes = PointCloudStoreTest.fixture(); assertThat(upload(deviceToken, bytes, "application/octet-stream")).isEqualTo(204);
        HttpResponse<InputStream> one = stream(ownerToken, device.getId()), two = stream(ownerToken, device.getId());
        try (InputStream first = one.body(); InputStream second = two.body()) {
            assertThat(one.statusCode()).isEqualTo(200);
            assertThat(one.headers().firstValue("Cache-Control")).contains("no-store");
            assertThat(first.readNBytes(bytes.length)).isEqualTo(bytes);
            assertThat(second.readNBytes(bytes.length)).isEqualTo(bytes);
            assertThat(first.read()).isEqualTo(-1);
            try (InputStream again = stream(ownerToken, device.getId()).body()) { assertThat(again.readNBytes(bytes.length)).isEqualTo(bytes); }
        }
    }
    @Test void ownerAndTokenTypeIsolationAndStatusPreservation() throws Exception {
        byte[] bytes = PointCloudStoreTest.fixture();
        assertThat(upload(null, bytes, "application/octet-stream")).isEqualTo(403);
        assertThat(upload(ownerToken, bytes, "application/octet-stream")).isEqualTo(403);
        assertThat(upload(deviceToken, bytes, "application/octet-stream")).isEqualTo(204);
        HttpResponse<InputStream> forbidden = stream(otherToken, device.getId());
        assertThat(forbidden.statusCode()).isEqualTo(404); forbidden.body().close();
        HttpResponse<InputStream> wrongType = stream(deviceToken, device.getId());
        assertThat(wrongType.statusCode()).isEqualTo(403); wrongType.body().close();
        assertThat(client.send(request("/error", null).GET().build(), HttpResponse.BodyHandlers.discarding()).statusCode()).isEqualTo(403);
        assertThat(upload(deviceToken, bytes, "application/json")).isEqualTo(415);
    }
    @Test void malformedOversizedAndRepositoryOutageHaveRealStatuses() throws Exception {
        assertThat(upload(deviceToken, new byte[32], "application/octet-stream")).isEqualTo(400);
        assertThat(upload(deviceToken, new byte[144033], "application/octet-stream")).isEqualTo(413);
        doThrow(new DataAccessResourceFailureException("injected test outage")).when(devices).findOwnerIdByDeviceId(device.getId());
        assertThat(upload(deviceToken, PointCloudStoreTest.fixture(), "application/octet-stream")).isEqualTo(503);
    }
    @Test void oneOwnersDeviceQuotaDoesNotBlockAnotherOwner() throws Exception {
        byte[] bytes = PointCloudStoreTest.fixture();
        for (int i=0;i<4;i++) {
            Device d = device(owner); assertThat(upload(tokens.generate(d.getId(), d.getSerialNumber()), bytes, "application/octet-stream")).isEqualTo(204);
        }
        assertThat(upload(deviceToken, bytes, "application/octet-stream")).isEqualTo(429);
        Device independent = device(other);
        assertThat(upload(tokens.generate(independent.getId(), independent.getSerialNumber()), bytes, "application/octet-stream")).isEqualTo(204);
        try (InputStream body = stream(otherToken, independent.getId()).body()) { assertThat(body.readNBytes(bytes.length)).isEqualTo(bytes); }
    }
    @Test void transactionSetupOutageOnStreamReturns503() throws Exception {
        doThrow(new org.springframework.transaction.CannotCreateTransactionException("injected transaction failure"))
                .when(deviceService).getOwned(owner.username(), device.getId());
        HttpResponse<InputStream> response = stream(ownerToken, device.getId());
        assertThat(response.statusCode()).isEqualTo(503); response.body().close();
    }
    @Test void absentFrameReturns503WithoutStartingAsync() throws Exception {
        HttpResponse<InputStream> response = stream(ownerToken, device.getId());
        assertThat(response.statusCode()).isEqualTo(503); response.body().close();
    }
}
