# Point-cloud transport and web viewer (steps 3–4)

## Data path

L2 -> standalone C++ receiver -> Python PointCloudManager -> dedicated
PointCloudUploader -> Spring latest-frame cache -> authenticated HTTP binary
stream -> browser transport module -> WebGL viewer. No ROS2, WebSocket
dependency, base64, or raw point-cloud database persistence is added.

The existing camera, robot controls, and fire telemetry remain separate. The
legacy 2D lidar-status API is unchanged. The 3D panel sits below keyboard
controls and provides visible connection status and a Reconnect button.

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
write-ready callback. One scheduler polls at20ms; each client selects at most one frame per100ms, measured from selection rather than write completion. Scheduling jitter and slow links can reduce the achieved rate. Each stream holds one frame
in progress and then selects only the latest, without a frame task queue.
Writes are4096-byte slices. Continuous not-ready or no successful write/flush progress for2s closes the stream. Independently, an unfinished frame older than4s from server receipt closes even if progress continues; a blocked viewer cannot retain an application slot indefinitely.
Slots are released exactly once when close is decided, before AsyncContext
completion; context completion/error/timeout is also idempotent. Underlying OS
socket teardown and container-buffer reclamation are not promised within2s.

Streams rotate after60s and check captured JWT validity during ticks. Planned
lifetime/stale/auth closure finishes the current frame boundary if possible,
with at most2s grace from the first close decision (progress does not reset it) and no new frame after invalid auth. The absolute4s frame age cap still applies. Ownership is checked
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
connectPointCloud({deviceId,getToken,onFrame,onState}). App.jsx mounts
PointCloudPanel, which calls it through pointCloudViewerSession.js. Callbacks
must be synchronous. onFrame receives the latest complete
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
budget is EXHAUSTED with no live reader/timers. The panel Reconnect button
creates a new session and transport. stop() aborts/cancels reads and waits, suppresses late
callbacks, and disposes the connection. Caller must stop on unmount/logout or
device change; getToken should return the current stored token on reconnect.

Reverse proxies must permit streaming and disable buffering for this endpoint.
The response header requests this but does not verify deployment behavior.
Actual Jetson bandwidth, AI/video coexistence and end-to-end latency remain for
the later target test, not asserted from software-only checks.

## Software proof (no physical hardware)

```bash
python3 -m unittest tests.test_point_cloud_manager tests.test_point_cloud_uploader -v
node --test web/tests/*.test.js
./server/gradlew -p server --no-daemon test
npm --prefix web ci --ignore-scripts
npm --prefix web run build
```

Use installed Java17 and a local Gradle cache. Existing server/gradle.properties
contains a pre-existing machine-specific Java path; adapt the local environment
when building elsewhere rather than committing another personal path. Tests
use temporary fake processes, shared fixtures, H2 and loopback-only HTTP/Tomcat.
They never run real main.py/SDK, connect to a Jetson, or access physical devices.


## Web 3D viewer

The dashboard places a live point-cloud panel below manual keyboard control,
including tablet and mobile layouts. By default it draws only the latest validated
frame, up to12000 points, using native WebGL with fixed GPU buffers. No production
package is added.30m is the fixed sensor data filter, not a display range slider
or a guarantee of detection on every surface. This is individual-frame point
visualization, not meshing, mapping, SLAM or fire detection from LiDAR.

Raw sensor XYZ is unchanged and Z is shown up; physical mounting alignment is
not calibrated here. The grid spacing is5m, the colored short axes mark XYZ at
the sensor origin. The first nonempty frame centers the view on its XYZ bounds
and fits its bounding sphere with a margin. New frames do not continually move
the view. Fit scene repeats this operation on the latest frame while preserving
the viewing angle; Reset view also restores the default oblique angle. A65m
origin-centered view remains the fallback before any nonempty frame. The narrower
viewport dimension sets the field of view so portrait canvases also fit.
User zoom can crop points without changing the received count.

Point color represents sensor Z height using blue, cyan, yellow and red. Its
range is set from the fitted frame's minimum/maximum Z, with a minimum0.5m span
for flat clouds; subsequent values outside that range are clamped. Fitting or
resetting updates this color range, not the underlying XYZ coordinates. Colors
are relative to the fitted scene, not a fixed absolute-height legend. Point
sprites target2 CSS pixels, bounded by the WebGL device's supported size.
There is no intensity channel or invented data. Drag to orbit, scroll to zoom,
or use the labeled orbit/zoom/fit/reset buttons. These controls never send robot commands.
Existing dashboard WASD/Escape robot shortcuts remain unchanged.

A new frame, view/size change, or accumulation-expiration timer schedules a draw;
there is no idle render loop. In single-frame mode CPU staging capacity and GPU cloud buffer are fixed
at12000 XYZ triples; the latest update replaces previous points. Device pixel ratio is capped at2,
and drawing dimensions at2048px per axis with a shared scale to preserve aspect. A valid zero-point frame clears old
points and says no points; stale, retry and terminal failure clear the cloud.
A healthy connection rotation preserves a still-fresh cloud while showing
Reconnecting. Only onFrame(null), not CONNECTING by itself, clears the cloud.

Accumulation is an optional, off-by-default browser display mode for a stationary
sensor. It retains at most5 distinct frames from the last500ms of browser
monotonic receipt time, not sensor timestamps, with at most60000 displayed points.
Each source frame still obeys the12000-point wire limit. Raw XYZ is not transformed,
and no points are interpolated. Source cloud ID plus timestamp identifies repeated
frames: duplicates neither inflate the count nor renew their retention time.
Clearing points on an automatic retry retains the last identity, so the same
last cloud cannot revive the window. A new viewer session starts a new identity
check; manual Reconnect and device/mode changes intentionally create that session.
An empty frame immediately removes previous points. Expiration also runs without
new input using one scheduled timer per viewer; browser timer throttling or a
blocked event loop can delay cleanup, so this is not a hard real-time guarantee.

Accumulation uses fixed CPU/GPU staging of60000 XYZ triples each and at most5
source-frame buffers (at most720160 source bytes including headers). Switching
mode recreates the viewer, resets its view, and clears history. Stale/retry/error,
manual reconnect, device changes and unmount discard history and cancel the
expiration timer. Healthy stream rotation can keep only the still-unexpired
history, never extend its window. The latest source point count and combined
displayed count are shown separately; coincident points can still overlap.
This mode has no motion/pose compensation and can leave trails when the sensor
or scene moves. It is not a persistent map or SLAM. Fit scene uses the currently
displayed window; use it after the window fills if the initial fit was sparse.
No server or receiver settings change when selecting this mode.

Every session creates its own canvas. Device switch, reconnect, unmount and
React StrictMode cleanup stop the old stream, cancel pending render work,
remove event/resize listeners, delete GL resources and discard its context.
Graphics initialization or context loss reports an error and stops that stream;
Reconnect creates a new canvas/context and retries with the current token.
No automatic context restoration or simulated fallback cloud is used.

Single-frame browser freshness means2s since a complete local frame receipt, not2s
since acquisition. Accumulation instead clears its visible window after500ms
without a distinct frame and reports No fresh data even if the transport has not
yet reached its2s stale deadline. A link below2Hz can therefore alternate between
Live and No fresh data in accumulation mode; use single-frame mode on such links. Sensor timestamps are not synchronized clocks. Server frame
transfer age is capped at4s from server receipt, but network/proxy buffering
can add delay. The browser aborts after6s without a complete frame, so links
unable to transfer a frame within that limit eventually exhaust retries. This
is a known limitation, not a real-time acquisition-age guarantee. Real Jetson,
production proxy buffering, sensor-axis alignment and achieved rate require
step6 hardware/network validation.

For the opt-in hardware-free C++/Python/Spring/browser pipeline, prerequisites,
negative checks and exact cleanup limits, see
[point-cloud integration tests](point-cloud-testing.md).
