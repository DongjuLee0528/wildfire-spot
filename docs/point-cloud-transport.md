# Point-cloud transport (step 3)

## Data path

L2 -> standalone C++ receiver -> Python PointCloudManager -> dedicated
PointCloudUploader -> Spring latest-frame cache -> authenticated HTTP binary
stream -> browser transport module. No ROS2, WebSocket dependency, base64, raw
point-cloud database persistence, or 3D renderer is added by this step.

The existing camera, robot controls, and fire telemetry remain separate. The
legacy 2D lidar-status API is unchanged. Step 4 must connect the transport to a
3D panel below keyboard controls and implement visible reconnect handling.

## Python configuration and lifecycle

The existing `SPRING_TELEMETRY_ENABLED`, `DEVICE_SERIAL_NUMBER`, `DEVICE_KEY`,
`SPRING_API_BASE_URL`, `L2_POINT_CLOUD_ENABLED`, and `L2_RECEIVER_PATH` settings
are reused. There are no new credentials. Keep real keys in existing local
environment files, not source control or command examples. The receiver must
be built/configured separately as documented in hardware/l2_receiver/README.md.

main.py creates the uploader only when telemetry is enabled and a point-cloud
manager exists. Missing credentials/import/setup errors are reported without
aborting camera/fire functionality. It signals the uploader to stop before the
receiver, then performs existing hardware cleanup before joining the upload
worker. The join runs in a finally block even if another cleanup fails, and
logging closes last. Network waits therefore do not add latency ahead of the
existing hardware shutdown sequence. The pre-existing receiver cleanup may
still wait up to its own timeout before legacy servo shutdown; physical shutdown
behavior needs its separate hardware review/testing before deployment. No import starts a network worker.

The uploader owns one requests.Session (not shared with SpringTelemetry), selects
only the latest fresh frame before every send, and sends at most 10Hz. A frame
is not resent solely because its SDK ID is repeated; object identity tracks
already-sent frames. The server returns exact HTTP204 with no body, consumed so
the connection is reused. Redirects are disabled. Login JSON is bounded to8192
bytes. Keys/tokens/raw frames/response bodies are not logged.

Upload401/403 permits one device login and one retry using the latest frame.
Another401/403 is terminal ERROR. Login401 is terminal; login403/429/5xx/network
failures and upload429/5xx/network failures retry after1/2/4/8/16 seconds, then
continue in DEGRADED at30 seconds plus0-3s jitter. Successful upload resets the
consecutive failure budget. Other statuses (including3xx and unexpected2xx),
invalid login JSON, and missing tokens are terminal protocol errors. Source
without a fresh frame waits without queueing/uploading stale data.

get_status() exposes WAITING/CONNECTING/STREAMING/RETRYING/DEGRADED/ERROR/STOPPED
and the error/failure count. close() interrupts waits and joins up to7 seconds;
a worker that does not stop or session cleanup failure is reported. Requests
connect/read timeouts are1s/2s, not a universal total operation deadline: OS,
header-drip, DNS, parent crash/SIGKILL, or pathological network behavior can still
prevent a timely clean shutdown. No sensor reset/reconfiguration is attempted.

## HTTP contract and authorization

- POST `/api/device/point-cloud`: existing DEVICE JWT, application/octet-stream.
  Device ID comes only from the authenticated principal. Success204; bad
  frame400; unknown device404; oversize413; wrong media415; quotas/rate429;
  unavailable metadata/cache503. Request body read capped at144033 bytes.
- GET `/api/devices/{deviceId}/point-cloud/stream`: USER/ADMIN Bearer JWT and
  current DeviceService ownership check. Wrong/unknown owner404; no fresh
  frame503; quota429. Tokens never appear in URLs. Initial auth failures follow
  the existing security403 behavior.
- Stream response: application/octet-stream; Cache-Control:no-store;
  X-Accel-Buffering:no. Consecutive v1 binary frames, unchanged from step1.
- Only Servlet ERROR dispatch is permitted through the security error fallback
  so framework415/5xx statuses are not masked as403. Direct REQUEST `/error`
  remains denied. This also corrects masked errors on existing endpoints;
  genuine unauthenticated requests are still denied.

All implementations validate magic L2PC, version1, unsigned count<=12000,
size=count*12, total=32+size, finite timestamp>=0 and finite XYZ with
0<x*x+y*y+z*z<=900 computed in double precision. Count0 is valid. A single
invalid point rejects the entire frame; the step1 producer already drops those
points. The strict IPC policy is preserved. Java uses unsigned-long conversion
before arithmetic. Shared canonical fixtures live in tests/fixtures.

## Bounds and failure handling

Backend cache holds at most64 device entries and4 per owner, one latest copied
frame each (at most144032 bytes). Admission is atomic. Accepted uploads are
limited to20Hz/device; metadata/existence uses a scalar owner-ID query with5s
TTL, one in-flight lookup/device and at most16 concurrent lookups. Followers
wait at most1s; query timeout hint1s does not guarantee pool/database latency.
Failed rechecks return503 rather than using expired authorization metadata.
Frames are fresh for2s after receipt and pruned after5s. Freshness is measured
per hop, not proof of end-to-end age or synchronized sensor clocks.

There are at most8 active browser streams globally and2 per username. Reads
and writes are nonblocking Servlet I/O, started only after the first container
write-ready callback. One scheduler polls at100ms. Each stream holds one frame
in progress and then selects only the latest, without a frame task queue.
Writes are4096-byte slices. Continuous not-ready or an unfinished frame for2s
closes the stream; a blocked viewer cannot retain an application slot indefinitely.
Slots are released exactly once when close is decided, before AsyncContext
completion; context completion/error/timeout is also idempotent. Underlying OS
socket teardown and container-buffer reclamation are not promised within2s.

Streams rotate after60s and check captured JWT validity during ticks. Planned
lifetime/stale/auth closure finishes the current frame boundary if possible,
with at most2s grace and no new frame after invalid auth. Ownership is checked
on every new connection; owner changes can take up to the stream lifetime to
be noticed, and upload device deletion can take up to metadata TTL. Shutdown
may truncate because Boot can stop connectors before @PreDestroy. Parent/OS
crashes and proxy/network failures remain external limits.

Public signup remains available. Per-owner quotas do not prevent multi-account
Sybil exhaustion of global limits. Rejected/deleted devices do not gain a
positive metadata cache entry and can trigger repeated bounded metadata lookups;
this is an accepted residual risk alongside existing public-login load. There
is no new signup policy, durable rejection cache or per-IP gate in this step.

## Browser integration contract

`web/src/transport/pointCloudTransport.js` exports PointCloudDecoder and
connectPointCloud({deviceId,getToken,onFrame,onState}). It is not yet called by
App.jsx. Callbacks must be synchronous. onFrame receives the latest complete
frame per read batch, or null to clear stale/disconnected data; frame.data
contains the full binary header+XYZ bytes. onState receives state/error.

The transport attaches Authorization on each fetch, parses arbitrary split and
coalesced data with a fixed-size decoder, marks STALE after2s and aborts a read
with no complete frame after6s. Structural/coordinate protocol errors and
HTTP401/403/404 are terminal ERROR. Partial EOF/network/429/503/5xx retry with
1/2/4/8/16-second waits. Retry budget resets only after10s stable streaming.
A clean EOF after55s is normal rotation and reconnects promptly without clearing
a still-fresh frame. The existing stale deadline continues across reconnect;
only a new complete frame resets it, so a failed/slow reconnect still clears
the display after2s. An exhausted
budget is EXHAUSTED with no live reader/timers: step4 must allow creating a new
transport to reconnect. stop() aborts/cancels reads and waits, suppresses late
callbacks, and disposes the connection. Caller must stop on unmount/logout or
device change; getToken should return the current stored token on reconnect.

Reverse proxies must permit streaming and disable buffering for this endpoint.
The response header requests this but does not verify deployment behavior.
Actual Jetson bandwidth, AI/video coexistence and end-to-end latency remain for
the later target test, not asserted from software-only checks.

## Software proof (no physical hardware)

```bash
python3 -m unittest tests.test_point_cloud_manager tests.test_point_cloud_uploader -v
node --test web/tests/pointCloudTransport.test.js
./server/gradlew -p server --no-daemon test
npm --prefix web ci --ignore-scripts
npm --prefix web run build
```

Use installed Java17 and a local Gradle cache. Existing server/gradle.properties
contains a pre-existing machine-specific Java path; adapt the local environment
when building elsewhere rather than committing another personal path. Tests
use temporary fake processes, shared fixtures, H2 and loopback-only HTTP/Tomcat.
They never run real main.py/SDK, connect to a Jetson, or access physical devices.
