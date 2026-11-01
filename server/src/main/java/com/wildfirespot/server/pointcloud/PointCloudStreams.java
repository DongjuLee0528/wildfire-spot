package com.wildfirespot.server.pointcloud;

import com.wildfirespot.server.auth.JwtProvider;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import jakarta.servlet.AsyncContext;
import jakarta.servlet.AsyncEvent;
import jakarta.servlet.AsyncListener;
import jakarta.servlet.ServletOutputStream;
import jakarta.servlet.WriteListener;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import java.io.IOException;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

@Service
public class PointCloudStreams {
    private static final Logger log = LoggerFactory.getLogger(PointCloudStreams.class);
    private final PointCloudStore store;
    private final JwtProvider jwt;
    private final long lifetimeNs;
    private final Set<Client> clients = new HashSet<>();
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread thread = new Thread(r, "point-cloud-streams"); thread.setDaemon(true); return thread;
    });
    private boolean running = true;

    public PointCloudStreams(PointCloudStore store, JwtProvider jwt,
                             @Value("${point-cloud.stream-lifetime-ms:60000}") long lifetimeMs) {
        if (lifetimeMs <= 0 || lifetimeMs > 60000) throw new IllegalArgumentException("Invalid stream lifetime");
        this.store = store; this.jwt = jwt; this.lifetimeNs = TimeUnit.MILLISECONDS.toNanos(lifetimeMs);
    }

    @PostConstruct
    public void start() { scheduler.scheduleAtFixedRate(this::tick, 20, 20, TimeUnit.MILLISECONDS); }

    public void open(String username, String deviceId, String token,
                     HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.setContentType("application/octet-stream");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("X-Accel-Buffering", "no");
        Client client = new Client(username, deviceId, token);
        synchronized (clients) {
            if (!running) throw new PointCloudProblem(HttpStatus.SERVICE_UNAVAILABLE);
            if (clients.size() >= 8 || clients.stream().filter(c -> c.username.equals(username)).count() >= 2)
                throw new PointCloudProblem(HttpStatus.TOO_MANY_REQUESTS);
            clients.add(client);
        }
        try {
            AsyncContext context = request.startAsync(request, response);
            synchronized (client) { client.context = context; }
            client.attach(context, response.getOutputStream());
        } catch (IOException | RuntimeException error) {
            if (!response.isCommitted()) response.setStatus(500);
            client.close();
            throw error;
        }
    }

    void tick() {
        try {
            store.prune();
            Client[] snapshot;
            synchronized (clients) { snapshot = clients.toArray(Client[]::new); }
            for (Client client : snapshot) {
                try { client.tick(); }
                catch (Exception error) {
                    log.warn("Point-cloud stream failed ({})", error.getClass().getSimpleName());
                    client.close();
                }
            }
        } catch (Exception error) {
            log.warn("Point-cloud tick failed ({})", error.getClass().getSimpleName());
        }
    }

    int activeCount() { synchronized (clients) { return clients.size(); } }

    @PreDestroy
    public void close() {
        Client[] snapshot;
        synchronized (clients) { running = false; snapshot = clients.toArray(Client[]::new); }
        for (Client client : snapshot) client.close();
        scheduler.shutdownNow();
    }

    final class Client implements WriteListener, AsyncListener {
        final String username, deviceId, token;
        final AtomicBoolean active = new AtomicBoolean(true);
        final long openedAt = store.clock.getAsLong();
        AsyncContext context;
        ServletOutputStream output;
        boolean callbackSeen, closing, flushPending;
        PointCloudStore.Frame pending, lastSent;
        int offset;
        long progressAt, lastSentAt = openedAt - TimeUnit.MILLISECONDS.toNanos(100);
        Long notReadyAt, closingAt;

        Client(String username, String deviceId, String token) {
            this.username = username; this.deviceId = deviceId; this.token = token;
        }

        synchronized void attach(AsyncContext context, ServletOutputStream output) {
            this.context = context; this.output = output;
            context.setTimeout(0);
            if (!active.get()) { complete(); return; }
            context.addListener(this);
            output.setWriteListener(this);
        }

        synchronized void tick() throws IOException {
            if (!active.get()) return;
            long now = store.clock.getAsLong();
            if (now - openedAt >= lifetimeNs || !jwt.validate(token) || !jwt.isUserToken(token) || store.latest(deviceId) == null)
                closing = true;
            if (closing && closingAt == null) closingAt = now;
            if ((closingAt != null && now - closingAt > PointCloudStore.FRESH_NS) ||
                (pending != null && (now - progressAt > PointCloudStore.FRESH_NS ||
                    now - pending.receivedAt() > TimeUnit.SECONDS.toNanos(4)))) { close(); return; }
            if (!callbackSeen || output == null) {
                if (closing) close();
                return;
            }
            if (!output.isReady()) {
                if (notReadyAt == null) notReadyAt = now;
                if (now - notReadyAt > PointCloudStore.FRESH_NS) close();
                return;
            }
            notReadyAt = null;
            if (closing && pending == null) { close(); return; }
            if (!closing && pending == null && now - lastSentAt >= TimeUnit.MILLISECONDS.toNanos(100)) {
                PointCloudStore.Frame latest = store.latest(deviceId);
                if (latest != null && latest != lastSent) {
                    pending = latest; progressAt = now; lastSentAt = now; offset = 0; flushPending = true;
                }
            }
            drain();
        }

        synchronized void drain() throws IOException {
            if (!active.get() || !callbackSeen || output == null || pending == null) return;
            while (active.get() && output.isReady() && offset < pending.data().length) {
                int count = Math.min(4096, pending.data().length - offset);
                output.write(pending.data(), offset, count);
                offset += count; progressAt = store.clock.getAsLong();
            }
            if (active.get() && offset == pending.data().length && output.isReady()) {
                if (flushPending) { output.flush(); flushPending = false; progressAt = store.clock.getAsLong(); }
                if (output.isReady()) {
                    lastSent = pending; pending = null;
                    if (closing) close();
                }
            }
        }

        @Override
        public synchronized void onWritePossible() throws IOException {
            callbackSeen = true;
            try { tick(); }
            catch (IOException | RuntimeException error) { close(); throw error; }
        }
        @Override
        public void onError(Throwable error) { close(); }
        @Override
        public void onComplete(AsyncEvent event) { close(); }
        @Override
        public void onTimeout(AsyncEvent event) { close(); }
        @Override
        public void onError(AsyncEvent event) { close(); }
        @Override
        public void onStartAsync(AsyncEvent event) { close(); }

        void close() {
            if (!active.compareAndSet(true, false)) return;
            synchronized (clients) { clients.remove(this); }
            synchronized (this) { pending = lastSent = null; complete(); }
        }

        void complete() {
            if (context == null) return;
            try { context.complete(); }
            catch (RuntimeException error) { log.debug("Point-cloud context completion unavailable ({})", error.getClass().getSimpleName()); }
        }
    }
}
