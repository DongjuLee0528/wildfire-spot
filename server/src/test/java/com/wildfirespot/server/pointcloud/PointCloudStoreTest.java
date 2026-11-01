package com.wildfirespot.server.pointcloud;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wildfirespot.server.auth.JwtProvider;
import com.wildfirespot.server.device.DeviceRepository;
import jakarta.servlet.AsyncContext;
import jakarta.servlet.ServletOutputStream;
import jakarta.servlet.WriteListener;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import java.io.ByteArrayOutputStream;
import java.util.HexFormat;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PointCloudStoreTest {
    static byte[] fixture() throws Exception {
        JsonNode fixtures = new ObjectMapper().readTree(PointCloudStoreTest.class.getResourceAsStream("/point_cloud_v1.json"));
        return HexFormat.of().parseHex(fixtures.get(0).get("hex").asText());
    }
    @Test void commonWireFixtures() throws Exception {
        JsonNode cases = new ObjectMapper().readTree(getClass().getResourceAsStream("/point_cloud_v1.json"));
        for (JsonNode c : cases) {
            byte[] data = HexFormat.of().parseHex(c.get("hex").asText());
            if (c.get("valid").asBoolean()) assertThatCode(() -> PointCloudFrame.validate(data)).as(c.get("name").asText()).doesNotThrowAnyException();
            else assertThatThrownBy(() -> PointCloudFrame.validate(data)).as(c.get("name").asText()).isInstanceOf(IllegalArgumentException.class);
        }
    }
    @Test void latestOnlyRateFreshnessMetadataAndOwnershipQuotas() throws Exception {
        DeviceRepository repo = mock(DeviceRepository.class);
        when(repo.findOwnerIdByDeviceId(anyString())).thenAnswer(call -> Optional.of(call.getArgument(0).toString().startsWith("other") ? "owner2" : "owner1"));
        AtomicLong clock = new AtomicLong(TimeUnit.SECONDS.toNanos(10));
        PointCloudStore store = new PointCloudStore(repo, clock::get);
        byte[] data = fixture(); store.accept("d1", data); data[0] = 0;
        assertThat(store.latest("d1").data()[0]).isEqualTo((byte)'L');
        assertThatThrownBy(() -> store.accept("d1", fixture())).isInstanceOf(PointCloudProblem.class)
                .extracting("status").isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
        clock.addAndGet(TimeUnit.MILLISECONDS.toNanos(50)); store.accept("d1", fixture());
        verify(repo, times(1)).findOwnerIdByDeviceId("d1");
        for (int i = 2; i <= 4; i++) store.accept("d"+i, fixture());
        assertThatThrownBy(() -> store.accept("d5", fixture())).isInstanceOf(PointCloudProblem.class)
                .extracting("status").isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
        assertThatCode(() -> store.accept("other", fixture())).doesNotThrowAnyException();
        clock.addAndGet(TimeUnit.SECONDS.toNanos(3)); assertThat(store.latest("d1")).isNull();
        clock.addAndGet(TimeUnit.SECONDS.toNanos(3)); store.prune(); store.accept("d1", fixture());
        verify(repo, times(2)).findOwnerIdByDeviceId("d1");
    }
    @Test void globalCacheBoundAndReclamation() throws Exception {
        DeviceRepository repo = mock(DeviceRepository.class);
        when(repo.findOwnerIdByDeviceId(anyString())).thenAnswer(call -> Optional.of("owner" + Integer.parseInt(call.getArgument(0)) / 4));
        AtomicLong clock = new AtomicLong(TimeUnit.SECONDS.toNanos(10));
        PointCloudStore store = new PointCloudStore(repo, clock::get);
        for (int i = 0; i < 64; i++) store.accept(""+i, fixture());
        assertThatThrownBy(() -> store.accept("64", fixture())).isInstanceOf(PointCloudProblem.class)
                .extracting("status").isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        clock.addAndGet(TimeUnit.SECONDS.toNanos(6)); store.prune();
        assertThatCode(() -> store.accept("64", fixture())).doesNotThrowAnyException();
    }

    @Test void globalStreamLimitAndCompletionFailureAreBounded() throws Exception {
        DeviceRepository repo = mock(DeviceRepository.class); when(repo.findOwnerIdByDeviceId("d")).thenReturn(Optional.of("owner"));
        AtomicLong clock = new AtomicLong(TimeUnit.SECONDS.toNanos(10));
        PointCloudStore store = new PointCloudStore(repo, clock::get); store.accept("d", fixture());
        JwtProvider jwt = mock(JwtProvider.class); when(jwt.validate(anyString())).thenReturn(true); when(jwt.isUserToken(anyString())).thenReturn(true);
        PointCloudStreams streams = new PointCloudStreams(store, jwt, 60000);
        try {
            Opened first = open(streams, "u0");
            for (int i=1;i<8;i++) open(streams, "u"+(i/2));
            assertThat(streams.activeCount()).isEqualTo(8);
            assertThatThrownBy(() -> open(streams, "ninth")).isInstanceOf(PointCloudProblem.class);
            doThrow(new IllegalStateException("already closed")).when(first.context).complete();
            assertThatCode(() -> first.output.listener.onError(new java.io.IOException("injected"))).doesNotThrowAnyException();
            assertThatCode(() -> open(streams, "ninth")).doesNotThrowAnyException();
        } finally { streams.close(); }
        assertThat(streams.activeCount()).isZero();
    }

    @Test void ownerLookupIsSingleFlightOutsideCacheLock() throws Exception {
        DeviceRepository repo = mock(DeviceRepository.class);
        java.util.concurrent.CountDownLatch entered = new java.util.concurrent.CountDownLatch(1), release = new java.util.concurrent.CountDownLatch(1);
        when(repo.findOwnerIdByDeviceId("d")).thenAnswer(call -> {
            entered.countDown(); release.await(2, java.util.concurrent.TimeUnit.SECONDS); return Optional.of("owner");
        });
        PointCloudStore store = new PointCloudStore(repo, () -> TimeUnit.SECONDS.toNanos(10));
        var executor = java.util.concurrent.Executors.newFixedThreadPool(2);
        try {
            byte[] bytes = fixture();
            java.util.concurrent.Callable<Boolean> accept = () -> {
                try { store.accept("d", bytes); return true; }
                catch (PointCloudProblem error) { assertThat(error.status).isEqualTo(HttpStatus.TOO_MANY_REQUESTS); return false; }
            };
            var first = executor.submit(accept);
            assertThat(entered.await(1, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
            var second = executor.submit(accept);
            assertThat(store.latest("d")).isNull();
            Thread.sleep(40); release.countDown();
            assertThat(first.get(2, java.util.concurrent.TimeUnit.SECONDS) ^ second.get(2, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
            verify(repo, times(1)).findOwnerIdByDeviceId("d");
        } finally { release.countDown(); executor.shutdownNow(); }
    }

    static final class Output extends ServletOutputStream {
        boolean ready = true, fail;
        int pauseAfter = Integer.MAX_VALUE;
        WriteListener listener;
        Runnable onByte = () -> {};
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        @Override public boolean isReady() { return ready; }
        @Override public void setWriteListener(WriteListener value) { listener = value; }
        @Override public void write(int value) throws java.io.IOException {
            if (fail) throw new java.io.IOException("injected");
            bytes.write(value); onByte.run();
            if (bytes.size() >= pauseAfter) ready = false;
        }
    }
    record Opened(Output output, AsyncContext context) {}
    Opened open(PointCloudStreams streams, String user) throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        HttpServletResponse response = mock(HttpServletResponse.class);
        AsyncContext context = mock(AsyncContext.class);
        Output output = new Output();
        when(request.startAsync(request, response)).thenReturn(context);
        when(response.getOutputStream()).thenReturn(output);
        streams.open(user, "d", "test-token", request, response);
        return new Opened(output, context);
    }
    @Test void streamQuotasReadinessGateSlowClientAndImmediateSlotRelease() throws Exception {
        DeviceRepository repo = mock(DeviceRepository.class);
        when(repo.findOwnerIdByDeviceId("d")).thenReturn(Optional.of("owner"));
        AtomicLong clock = new AtomicLong(TimeUnit.SECONDS.toNanos(10));
        PointCloudStore store = new PointCloudStore(repo, clock::get); store.accept("d", fixture());
        JwtProvider jwt = mock(JwtProvider.class); when(jwt.validate(anyString())).thenReturn(true); when(jwt.isUserToken(anyString())).thenReturn(true);
        PointCloudStreams streams = new PointCloudStreams(store, jwt, 60000);
        try {
            Opened one = open(streams, "one"), two = open(streams, "one");
            assertThatThrownBy(() -> open(streams, "one")).isInstanceOf(PointCloudProblem.class);
            Opened other = open(streams, "other");
            streams.tick(); assertThat(one.output.bytes.size()).isZero();
            one.output.listener.onWritePossible(); assertThat(one.output.bytes.toByteArray()).isEqualTo(fixture());
            one.output.ready = false;
            streams.tick();
            clock.addAndGet(TimeUnit.SECONDS.toNanos(1)); store.accept("d", fixture()); streams.tick();
            clock.addAndGet(TimeUnit.SECONDS.toNanos(1)); store.accept("d", fixture()); streams.tick();
            verify(one.context, never()).complete();
            clock.incrementAndGet(); streams.tick();
            verify(one.context).complete();
            assertThat(streams.activeCount()).isEqualTo(2);
            assertThatCode(() -> open(streams, "one")).doesNotThrowAnyException();
            other.output.listener.onError(new java.io.IOException("injected"));
            other.output.listener.onError(new java.io.IOException("again"));
            verify(other.context, times(1)).complete();
        } finally { streams.close(); }
        assertThat(streams.activeCount()).isZero();
    }
    @Test void plannedCloseCompletesOnlyPendingFrameWithinExactGrace() throws Exception {
        for (boolean resume : new boolean[]{true, false}) {
            DeviceRepository repo = mock(DeviceRepository.class); when(repo.findOwnerIdByDeviceId("d")).thenReturn(Optional.of("owner"));
            AtomicLong clock = new AtomicLong(TimeUnit.SECONDS.toNanos(10));
            PointCloudStore store = new PointCloudStore(repo, clock::get);
            java.nio.ByteBuffer buffer = java.nio.ByteBuffer.allocate(12032).order(java.nio.ByteOrder.LITTLE_ENDIAN);
            buffer.put(new byte[]{'L','2','P','C'}).putInt(1).putInt(12000).putInt(1000).putDouble(1).putInt(1).putInt(18);
            for (int i=0;i<1000;i++) buffer.putFloat(1).putFloat(2).putFloat(3);
            byte[] original = buffer.array(); store.accept("d", original);
            JwtProvider jwt = mock(JwtProvider.class); when(jwt.validate(anyString())).thenReturn(true); when(jwt.isUserToken(anyString())).thenReturn(true);
            PointCloudStreams streams = new PointCloudStreams(store, jwt, 60000);
            try {
                Opened opened = open(streams, "one"); opened.output.pauseAfter = 4096;
                opened.output.listener.onWritePossible(); assertThat(opened.output.bytes.size()).isEqualTo(4096);
                clock.addAndGet(TimeUnit.MILLISECONDS.toNanos(100));
                byte[] next = original.clone(); java.nio.ByteBuffer.wrap(next).order(java.nio.ByteOrder.LITTLE_ENDIAN).putInt(24, 2);
                store.accept("d", next); when(jwt.validate(anyString())).thenReturn(false); streams.tick();
                clock.set(TimeUnit.MILLISECONDS.toNanos(11100));
                opened.output.pauseAfter = 8192; opened.output.ready = true; opened.output.listener.onWritePossible();
                clock.set(TimeUnit.MILLISECONDS.toNanos(12100)); streams.tick();
                assertThat(streams.activeCount()).isEqualTo(1); verify(opened.context, never()).complete();
                if (resume) {
                    opened.output.pauseAfter = Integer.MAX_VALUE; opened.output.ready = true;
                    opened.output.listener.onWritePossible();
                    assertThat(opened.output.bytes.toByteArray()).isEqualTo(original);
                } else {
                    clock.incrementAndGet(); streams.tick(); assertThat(opened.output.bytes.size()).isEqualTo(8192);
                }
                assertThat(streams.activeCount()).isZero(); verify(opened.context, times(1)).complete();
            } finally { streams.close(); }
        }
    }

    @Test void progressingFrameCanExceedTwoSecondsButStallAndAbsoluteAgeStayBounded() throws Exception {
        for (boolean progress : new boolean[]{true, false}) {
            DeviceRepository repo = mock(DeviceRepository.class); when(repo.findOwnerIdByDeviceId("d")).thenReturn(Optional.of("owner"));
            AtomicLong clock = new AtomicLong(TimeUnit.SECONDS.toNanos(10));
            PointCloudStore store = new PointCloudStore(repo, clock::get);
            java.nio.ByteBuffer data = java.nio.ByteBuffer.allocate(60032).order(java.nio.ByteOrder.LITTLE_ENDIAN);
            data.put(new byte[]{'L','2','P','C'}).putInt(1).putInt(60000).putInt(5000).putDouble(1).putInt(1).putInt(18);
            for (int i=0;i<5000;i++) data.putFloat(1).putFloat(2).putFloat(3);
            store.accept("d", data.array());
            JwtProvider jwt = mock(JwtProvider.class); when(jwt.validate(anyString())).thenReturn(true); when(jwt.isUserToken(anyString())).thenReturn(true);
            PointCloudStreams streams = new PointCloudStreams(store, jwt, 60000);
            try {
                Opened opened = open(streams, "one"); opened.output.pauseAfter = 4096;
                opened.output.listener.onWritePossible();
                for (int i=1;i<=4;i++) {
                    clock.set(TimeUnit.SECONDS.toNanos(10+i)); store.accept("d", data.array());
                    if (progress) {
                        opened.output.pauseAfter = opened.output.bytes.size() + 4096; opened.output.ready = true;
                        opened.output.listener.onWritePossible();
                    } else streams.tick();
                    if (progress || i<=2) assertThat(streams.activeCount()).isEqualTo(1);
                    else assertThat(streams.activeCount()).isZero();
                }
                clock.incrementAndGet(); streams.tick();
                assertThat(streams.activeCount()).isZero(); verify(opened.context, times(1)).complete();
                assertThat(opened.output.bytes.size()).isLessThan(data.array().length);
            } finally { streams.close(); }
        }
    }

    @Test void selectionPacingIgnoresWriteDurationAndHandlesJitterWithoutBurst() throws Exception {
        DeviceRepository repo = mock(DeviceRepository.class); when(repo.findOwnerIdByDeviceId("d")).thenReturn(Optional.of("owner"));
        AtomicLong clock = new AtomicLong(TimeUnit.SECONDS.toNanos(10));
        PointCloudStore store = new PointCloudStore(repo, clock::get); store.accept("d", fixture());
        JwtProvider jwt = mock(JwtProvider.class); when(jwt.validate(anyString())).thenReturn(true); when(jwt.isUserToken(anyString())).thenReturn(true);
        PointCloudStreams streams = new PointCloudStreams(store, jwt, 60000);
        try {
            Opened opened = open(streams, "one");
            opened.output.onByte = () -> clock.incrementAndGet();
            opened.output.listener.onWritePossible();
            int size = fixture().length;
            for (int i=1;i<10;i++) {
                clock.set(TimeUnit.SECONDS.toNanos(10) + TimeUnit.MILLISECONDS.toNanos(i*100));
                store.accept("d", fixture()); streams.tick();
                assertThat(opened.output.bytes.size()).isEqualTo((i+1)*size);
                streams.tick(); assertThat(opened.output.bytes.size()).isEqualTo((i+1)*size);
            }
            long previous = clock.get();
            for (int i=0;i<6;i++) {
                long next = previous + TimeUnit.MILLISECONDS.toNanos(97);
                clock.set(next); store.accept("d", fixture()); streams.tick();
                int before = opened.output.bytes.size();
                clock.set(next + TimeUnit.MILLISECONDS.toNanos(20)); streams.tick();
                assertThat(opened.output.bytes.size()).isEqualTo(before + size);
                previous = clock.get();
            }
        } finally { streams.close(); }
    }

    @Test void lifetimeExpiryAndSetupFailureReleaseSlotsAndTickSurvivesErrors() throws Exception {
        DeviceRepository repo = mock(DeviceRepository.class); when(repo.findOwnerIdByDeviceId("d")).thenReturn(Optional.of("owner"));
        AtomicLong clock = new AtomicLong(TimeUnit.SECONDS.toNanos(10));
        PointCloudStore store = new PointCloudStore(repo, clock::get); store.accept("d", fixture());
        JwtProvider jwt = mock(JwtProvider.class); when(jwt.validate(anyString())).thenReturn(true); when(jwt.isUserToken(anyString())).thenReturn(true);
        PointCloudStreams streams = new PointCloudStreams(store, jwt, 100);
        try {
            HttpServletRequest req = mock(HttpServletRequest.class); HttpServletResponse res = mock(HttpServletResponse.class);
            AsyncContext ctx = mock(AsyncContext.class); when(req.startAsync(req, res)).thenReturn(ctx);
            when(res.getOutputStream()).thenThrow(new java.io.IOException("injected"));
            assertThatThrownBy(() -> streams.open("one", "d", "token", req, res)).isInstanceOf(java.io.IOException.class);
            verify(ctx).complete(); assertThat(streams.activeCount()).isZero();
            Opened active = open(streams, "one"); active.output.listener.onWritePossible();
            clock.addAndGet(TimeUnit.MILLISECONDS.toNanos(110)); streams.tick();
            verify(active.context).complete(); assertThat(streams.activeCount()).isZero();
            Opened next = open(streams, "one"); next.output.fail = true;
            assertThatThrownBy(next.output.listener::onWritePossible).isInstanceOf(java.io.IOException.class);
            assertThat(streams.activeCount()).isZero();
            Opened healthy = open(streams, "other"); healthy.output.listener.onWritePossible();
            assertThat(healthy.output.bytes.toByteArray()).isEqualTo(fixture());
            when(jwt.validate(anyString())).thenReturn(false); streams.tick();
            verify(healthy.context).complete();
        } finally { streams.close(); }
    }
}
