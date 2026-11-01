package com.wildfirespot.server.pointcloud;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wildfirespot.server.auth.*;
import com.wildfirespot.server.device.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BooleanSupplier;
import static org.assertj.core.api.Assertions.*;

@Tag("point-cloud-e2e")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "server.address=127.0.0.1", "robot.gateway.mode=mock", "spring.config.import=",
        "jwt.secret=test-secret-key-minimum-32-bytes-long", "jwt.expiration-ms=86400000",
        "spring.datasource.driver-class-name=org.h2.Driver", "spring.datasource.username=sa", "spring.datasource.password=",
        "spring.jpa.database-platform=org.hibernate.dialect.H2Dialect"})
class PointCloudPipelineTest {
    @DynamicPropertySource static void database(DynamicPropertyRegistry registry) {
        String database = "jdbc:h2:mem:pipeline-" + UUID.randomUUID() + ";DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE";
        registry.add("spring.datasource.url", () -> database);
    }
    @LocalServerPort int port;
    @Autowired UserRepository users;
    @Autowired DeviceRepository devices;
    @Autowired PasswordEncoder passwords;
    @Autowired JwtProvider jwt;
    @Autowired DeviceTokenProvider deviceTokens;
    @Autowired PointCloudStore store;
    @Autowired PointCloudStreams streams;
    @TempDir Path temporary;
    final ObjectMapper json = new ObjectMapper();
    final List<Helper> helpers = new ArrayList<>();
    Path repository;
    Device device, foreign;
    String key, token, otherToken;

    @BeforeEach void setup() throws Exception {
        repository = Path.of(System.getProperty("pointCloud.repository")).toRealPath();
        assertThat(repository.resolve("hardware/l2_receiver/main.cpp")).isRegularFile();
        assertThat(repository.resolve("web/src/components/PointCloudPanel.jsx")).isRegularFile();
        String name = "pipeline-" + UUID.randomUUID();
        User owner = users.save(new User(name, name+"@example.invalid", name, "unused-fixture-hash", "USER"));
        String otherName = "pipeline-other-" + UUID.randomUUID();
        User other = users.save(new User(otherName, otherName+"@example.invalid", otherName, "unused-fixture-hash", "USER"));
        key = UUID.randomUUID().toString();
        device = devices.save(new Device(owner, "fixture", UUID.randomUUID().toString(), passwords.encode(key), "pipeline fixture"));
        foreign = devices.save(new Device(other, "foreign fixture", UUID.randomUUID().toString(), passwords.encode(UUID.randomUUID().toString()), "pipeline fixture"));
        token = jwt.generate(name, "USER"); otherToken = jwt.generate(otherName, "USER");
    }
    Map<String, Object> configuration(Path directory) {
        return new HashMap<>(Map.of("baseUrl", "http://127.0.0.1:"+port, "directory", directory.toString(),
                "serial", device.getSerialNumber(), "key", key, "deviceId", device.getId(), "otherDeviceId", foreign.getId(),
                "token", token, "otherToken", otherToken, "deviceToken", deviceTokens.generate(device.getId(), device.getSerialNumber())));
    }
    Helper start(String executable, String script, String name, long timeout) throws Exception {
        Path directory = Files.createDirectory(temporary.resolve(name));
        ProcessBuilder builder = new ProcessBuilder(required(executable), repository.resolve(script).toString()).directory(repository.toFile());
        for (String variable : List.of("TMPDIR", "TMP", "TEMP")) builder.environment().put(variable, directory.toString());
        Helper helper = new Helper(builder.start()); helpers.add(helper);
        helper.send(configuration(directory)); helper.await("ready", timeout);
        return helper;
    }
    String required(String variable) {
        String value = System.getenv(variable);
        assertThat(value).as("Required E2E tool %s", variable).isNotBlank();
        assertThat(Path.of(value)).as("E2E tool %s", variable).isRegularFile().isExecutable();
        return value;
    }
    Helper source() throws Exception { return start("POINT_CLOUD_TEST_PYTHON", "tests/point_cloud_pipeline.py", "source", 30); }
    Helper browser() throws Exception { return start("POINT_CLOUD_TEST_NODE", "web/tests/pointCloudPipeline.mjs", "browser", 20); }
    JsonNode command(Helper helper, String command) throws Exception {
        if (command.equals("stop")) helper.snapshot();
        helper.send(Map.of("command", command)); return helper.await(command.equals("stop") ? "stopped" : command, command.equals("stop") ? 18 : 10);
    }
    static byte[] expected(String mode) {
        int count = mode.equals("empty") ? 0 : mode.equals("max") ? 12000 : 4;
        ByteBuffer result = ByteBuffer.allocate(32 + count*12).order(ByteOrder.LITTLE_ENDIAN);
        result.put(new byte[]{'L','2','P','C'}).putInt(1).putInt(count*12).putInt(count).putDouble(1234.5).putInt(mode.equals("recovered") ? 43 : 42).putInt(18);
        if (mode.equals("max")) for (int i=0;i<count;i++) result.putFloat(i%30+0.25f).putFloat(0).putFloat(0);
        else if (count != 0) {
            result.putFloat(mode.equals("recovered") ? 2 : 1).putFloat(mode.equals("recovered") ? 3 : 2).putFloat(mode.equals("recovered") ? 4 : 3);
            for (float value : new float[]{30,0,0,-30,0,0,0,0,-5}) result.putFloat(value);
        }
        return result.array();
    }
    void wire(String mode) throws Exception {
        byte[] bytes = expected(mode);
        until(() -> { var frame = store.latest(device.getId()); return frame != null && Arrays.equals(frame.data(), bytes); }, 5);
    }
    void until(BooleanSupplier condition, int seconds) throws Exception {
        long end = System.nanoTime() + Duration.ofSeconds(seconds).toNanos();
        while (!condition.getAsBoolean() && System.nanoTime() < end) Thread.sleep(10);
        assertThat(condition.getAsBoolean()).as("Pipeline condition within deadline").isTrue();
    }

    @Test @Timeout(value=100, threadMode=Timeout.ThreadMode.SAME_THREAD)
    void receiverThroughRealServerToBrowserAndRecovery() throws Exception {
        Helper source = source(); JsonNode initial = command(source, "status");
        long originalPid = initial.path("pid").asLong();
        assertThat(originalPid).isPositive(); assertThat(initial.path("restarts").asInt()).isZero();
        wire("normal"); Helper browser = browser(); command(browser, "isolation");
        System.out.println("PIPELINE normal coordinates and real authorization passed");
        for (String mode : List.of("empty", "max", "normal")) {
            command(source, mode); wire(mode); command(browser, mode);
            System.out.println("PIPELINE " + mode + " wire and current-canvas upload passed");
        }
        command(source, "idle"); command(browser, "clear");
        JsonNode stale = command(source, "stale"); assertThat(stale.path("state").asText()).isEqualTo("STALE");
        until(() -> store.latest(device.getId()) == null, 1);
        command(source, "normal"); wire("normal"); command(browser, "normal");
        JsonNode resumed = command(source, "status");
        assertThat(resumed.path("pid").asLong()).isEqualTo(originalPid); assertThat(resumed.path("restarts").asInt()).isZero();
        System.out.println("PIPELINE pause/stale/resume kept the same receiver PID");
        JsonNode recovered = command(source, "crash");
        assertThat(recovered.path("pid").asLong()).isPositive().isNotEqualTo(originalPid);
        assertThat(recovered.path("restarts").asInt()).isEqualTo(1);
        wire("recovered"); command(browser, "recovered");
        System.out.println("PIPELINE one crash/reap/restart delivered distinct recovered coordinates");
        command(browser, "foreign"); until(() -> streams.activeCount() == 0, 5);
        command(browser, "back");
        JsonNode before = command(source, "status");
        assertThat(before.path("restarts").asInt()).isEqualTo(1);
        assertThat(before.path("uploadState").asText()).isNotIn("ERROR", "DEGRADED");
        JsonNode stopped = command(source, "stop");
        assertThat(stopped.path("state").asText()).isEqualTo("STOPPED"); assertThat(stopped.path("pid").isNull()).isTrue();
        assertThat(stopped.path("uploadState").asText()).isEqualTo("STOPPED");
        until(() -> store.latest(device.getId()) == null, 3);
        command(browser, "clear"); command(browser, "stop");
        until(() -> streams.activeCount() == 0, 5);
        System.out.println("PIPELINE source stop cleared viewer and released all streams");
    }

    @Test @Timeout(value=60, threadMode=Timeout.ThreadMode.SAME_THREAD)
    void stdinEofStopsBothHelpersAndTheirDescendants() throws Exception {
        Helper source = source(); wire("normal"); Helper browser = browser();
        source.endInput(); browser.endInput();
        source.exitedCleanly(18); browser.exitedCleanly(18);
        until(() -> streams.activeCount() == 0, 5);
        source.verifyDead(); browser.verifyDead();
        System.out.println("PIPELINE stdin EOF stopped both helpers and recorded descendants");
    }

    @Test @Timeout(value=35, threadMode=Timeout.ThreadMode.SAME_THREAD)
    void forcedHelperDeathDoesNotHideItsReceiverAndWaitIsInterruptible() throws Exception {
        Helper source = source();
        Thread.currentThread().interrupt();
        assertThatThrownBy(() -> source.await("never", 1)).isInstanceOf(InterruptedException.class);
        assertThat(Thread.currentThread().isInterrupted()).isFalse();
        JsonNode reported = command(source, "status");
        long pid = reported.path("pid").asLong();
        ProcessHandle receiver = ProcessHandle.of(pid).orElseThrow();
        assertThat(source.reportedReceivers).as("Reported-PID path is nonempty before any snapshot").isNotEmpty().contains(receiver);
        assertThat(source.descendants).contains(receiver);
        assertThat(receiver.isAlive()).isTrue();
        command(source, "idle");
        assertThat(command(source, "stale").path("state").asText()).isEqualTo("STALE");
        source.forceAllowed = true; source.snapshot(); source.process.destroyForcibly();
        assertThat(source.process.waitFor(3, TimeUnit.SECONDS)).isTrue();
        assertThat(receiver.isAlive()).as("Idle receiver survives its parent before forced cleanup").isTrue();
        assertThat(source.process.descendants()).noneMatch(handle -> handle.pid() == pid);
        assertThat(receiver.parent().map(ProcessHandle::pid).orElse(-1L)).isNotEqualTo(source.process.pid());
        assertThat(source.reportedReceivers).contains(receiver);
        assertThat(source.forceCleanup()).as("Known orphan received a kill request").contains(pid);
        assertThat(receiver.isAlive()).isFalse(); source.verifyDead();
        System.out.println("PIPELINE interrupted reply wait and forced helper/receiver cleanup passed");
    }

    @AfterEach void cleanup() throws Exception {
        boolean interrupted = Thread.interrupted();
        List<Throwable> failures = new ArrayList<>();
        ExecutorService pool = Executors.newFixedThreadPool(2, task -> { Thread thread = new Thread(task, "pipeline-cleanup"); thread.setDaemon(true); return thread; });
        long end = System.nanoTime() + Duration.ofSeconds(18).toNanos();
        List<Future<?>> closers = new ArrayList<>();
        try {
            for (Helper helper : helpers) closers.add(pool.submit(() -> { helper.closeGracefully(); return null; }));
            for (Future<?> closer : closers) {
                try { closer.get(Math.max(1, end-System.nanoTime()), TimeUnit.NANOSECONDS); }
                catch (Exception error) { failures.add(error); closer.cancel(true); }
            }
            long forceDeadline = System.nanoTime()+Duration.ofSeconds(4).toNanos();
            for (Helper helper : helpers) {
                try {
                    if (!helper.forceAllowed && helper.hasLiveProcess()) failures.add(new AssertionError("Fixture process survived graceful shutdown"));
                    helper.forceCleanup(forceDeadline); helper.verifyDead();
                }
                catch (Throwable error) { failures.add(error); }
            }
        } finally {
            pool.shutdownNow();
            long readerDeadline = System.nanoTime()+Duration.ofSeconds(2).toNanos();
            for (Helper helper : helpers) {
                try { helper.closeReaders(readerDeadline); }
                catch (Throwable error) { failures.add(error); }
            }
            if (interrupted) Thread.currentThread().interrupt();
        }
        if (!failures.isEmpty()) {
            AssertionError error = new AssertionError("Pipeline teardown failed"); failures.forEach(error::addSuppressed); throw error;
        }
    }

    final class Helper {
        final Process process;
        final BufferedWriter input;
        final BlockingQueue<String> lines = new ArrayBlockingQueue<>(16);
        final Set<ProcessHandle> descendants = ConcurrentHashMap.newKeySet();
        final Set<ProcessHandle> reportedReceivers = ConcurrentHashMap.newKeySet();
        final StringBuilder stderr = new StringBuilder();
        final AtomicBoolean inputEnded = new AtomicBoolean();
        volatile boolean closing, forceAllowed;
        volatile String readerError;
        final Thread out, err;
        Helper(Process process) {
            this.process = process; input = new BufferedWriter(new OutputStreamWriter(process.getOutputStream(), StandardCharsets.UTF_8));
            out = new Thread(() -> readOutput(process.getInputStream(), true), "pipeline-stdout");
            err = new Thread(() -> readOutput(process.getErrorStream(), false), "pipeline-stderr");
            out.setDaemon(true); err.setDaemon(true); out.start(); err.start();
        }
        void readOutput(InputStream stream, boolean output) {
            try (Reader reader = new InputStreamReader(stream, StandardCharsets.UTF_8)) {
                if (output) {
                    StringBuilder line = new StringBuilder(); int value;
                    while ((value=reader.read()) != -1) {
                        if (value=='\n') { if (!lines.offer(line.toString())) throw new IOException("Reply queue overflow"); line.setLength(0); }
                        else { line.append((char)value); if (line.length()>8192) throw new IOException("Reply line limit"); }
                    }
                    lines.offer("EOF");
                } else {
                    char[] block = new char[1024]; int size;
                    while ((size=reader.read(block)) != -1) synchronized (stderr) {
                        stderr.append(block,0,size); if (stderr.length()>16384) stderr.delete(0,stderr.length()-16384);
                    }
                }
            } catch (IOException error) { if (!closing) readerError = "Fixture output reader failed: " + error.getClass().getSimpleName(); }
        }
        void send(Map<String, ?> data) throws Exception {
            assertThat(inputEnded.get()).isFalse(); input.write(json.writeValueAsString(data)); input.newLine(); input.flush();
        }
        JsonNode await(String expected, long seconds) throws Exception {
            String line = lines.poll(seconds, TimeUnit.SECONDS);
            String tail; synchronized (stderr) { tail=stderr.toString(); }
            assertThat(readerError).isNull();
            assertThat(line).withFailMessage("Fixture reply timeout (%s); stderr: %s", expected, tail).isNotNull().isNotEqualTo("EOF");
            JsonNode value = json.readTree(line);
            assertThat(value.path("event").asText()).withFailMessage("Fixture event expected %s, got %s; stderr: %s", expected, value, tail).isEqualTo(expected);
            if (value.has("pids")) for (JsonNode pid : value.path("pids")) ProcessHandle.of(pid.asLong()).ifPresent(handle -> { descendants.add(handle); reportedReceivers.add(handle); });
            if (value.has("browserPid")) ProcessHandle.of(value.path("browserPid").asLong()).ifPresent(descendants::add);
            if (value.has("renderer")) System.out.println("PIPELINE GL renderer: " + value.path("renderer").asText());
            return value;
        }
        void snapshot() { process.descendants().forEach(descendants::add); }
        void endInput() throws IOException { snapshot(); if (inputEnded.compareAndSet(false,true)) input.close(); }
        void exitedCleanly(long seconds) throws Exception {
            assertThat(process.waitFor(seconds,TimeUnit.SECONDS)).as("Fixture exit deadline").isTrue();
            assertThat(process.exitValue()).as("Fixture exit status").isZero();
        }
        void closeGracefully() throws Exception {
            closing=true; endInput();
            long end = System.nanoTime()+Duration.ofSeconds(18).toNanos();
            assertThat(process.waitFor(18,TimeUnit.SECONDS)).as("Fixture graceful shutdown").isTrue();
            if (!forceAllowed) {
                assertThat(process.exitValue()).as("Fixture successful exit").isZero();
                while (hasLiveProcess() && System.nanoTime()<end) Thread.sleep(10);
                verifyDead();
            }
        }
        Set<Long> forceCleanup() throws Exception { return forceCleanup(System.nanoTime()+Duration.ofSeconds(4).toNanos()); }
        Set<Long> forceCleanup(long end) throws Exception {
            snapshot();
            Set<Long> killed = new HashSet<>();
            for (ProcessHandle child : descendants) if (child.isAlive() && child.destroyForcibly()) killed.add(child.pid());
            if (process.isAlive()) { process.destroyForcibly(); killed.add(process.pid()); }
            assertThat(process.waitFor(Math.max(1,end-System.nanoTime()),TimeUnit.NANOSECONDS)).isTrue();
            while (descendants.stream().anyMatch(ProcessHandle::isAlive) && System.nanoTime()<end) Thread.sleep(10);
            return killed;
        }
        boolean hasLiveProcess() { return process.isAlive() || descendants.stream().anyMatch(ProcessHandle::isAlive); }
        void verifyDead() { assertThat(process.isAlive()).isFalse(); assertThat(descendants).allMatch(handle -> !handle.isAlive()); }
        void closeReaders(long deadline) throws Exception {
            closing=true; process.getInputStream().close(); process.getErrorStream().close();
            for (Thread reader : List.of(out,err)) reader.join(Math.max(1, TimeUnit.NANOSECONDS.toMillis(deadline-System.nanoTime())));
            assertThat(out.isAlive() || err.isAlive()).as("Fixture reader threads stopped").isFalse();
        }
    }
}
