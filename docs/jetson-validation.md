# Jetson and L2 validation (step 6)

Status: **NOT RUN**. The target is powered off. Completing the software and
operator documentation does not complete this step. No deployment, real SDK
execution, sensor timing, GPU performance or physical control is certified.
Use [operations](operations.md) for configuration and
[hardware-free proofs](point-cloud-testing.md) for the separate software checks.

## Trial boundaries

Each physical trial and retest needs explicit approval after its purpose,
effects, setup and stop conditions are reviewed. Do not run `main.py`, import
`utils.config`/runtime hardware modules, or run the real receiver as a preflight.
`main.py --help` is not a hardware-free probe. SDK `initializeUDP` and `closeUDP`
are opaque; their internal sensor effects are **UNVERIFIED**. Wiring, servo
calibration and post-deinit actuator state are also **UNVERIFIED**.

| Phase | Purpose and effects | Prerequisites and stop conditions | Result |
| --- | --- | --- | --- |
| A: metadata/build | Inspect target versions and compile/link; do not execute SDK | Correct checkout, Linux architecture, preserved environment; stop on mismatch/build failure | NOT RUN |
| B: isolated L2 | One bounded receive attempt, SDK UDP init/close, no runtime GPIO/camera/servo initialization | Approved network and SDK effects, exclusive UDP6201; stop on error, stale after streaming, timeout or unexpected device behavior | NOT RUN |
| C: full runtime | Starts sensors/GPS, camera inference, actuator drivers, automatic stand pose, camera tilt to 90 degrees, API and uploads | Separate approval, supported robot, clearance, independent power cut ready, trusted API access; conditions below | NOT RUN |
| D: measured workload/recovery | Compare cloud-only and AI/video coexistence, deliberately interrupt/recover only with separate approval | Baseline B/C evidence, bounded duration and explicit failure/recovery plan | NOT RUN |

## A. Target inventory and build

Record the deployed Git revision, SDK revision/header version, `uname -m`, OS
and JetPack release, Python version and installed package metadata (use
`importlib.metadata`, not imports of Torch, camera or hardware drivers). Preserve
the working virtual environment. Do not blindly install `requirements.txt`:
Torch/torchvision requirements are open-ended and CUDA compatibility has not
been checked for this target. Verify the selected model file exists; default
`models/wildfire_baseline/weights/best.pt` is relative to the repository root.

Follow the [pinned native build](../hardware/l2_receiver/README.md#sdk-dependency):
SDK `0e3c51f512e6b8ff60b8c32f160b412cb48445c2`, header 2.0.9, C++17,
Linux aarch64 on Jetson. Check executable metadata with `file`/`readelf` before
execution. A successful macOS fake-SDK build does not verify this Linux link.

Inspect addresses, routes, physical link and UDP6201 ownership after the target
is available. Identify the actual USB Ethernet interface; do not guess its name.
The existing L2 defaults are `192.168.1.62:6101` to host `192.168.1.2:6201`.
A previous `ip addr add` is temporary, not persistence evidence. Do not replace
default routes or reconfigure the sensor as part of this checklist. A ping or
captured UDP packet alone does not prove valid point clouds.

## B. Isolated receiver trial

Only after approval, from the repository root with the trusted robot environment
exported as in operations, use the existing manager directly. This disables
manager retries for this trial, samples metadata only, and retains failure
status before cleanup clears it. The 15 seconds bound sampling, not an absolute
SDK shutdown guarantee. Review stderr for cleanup failure too.

```python
import os
import time
from hardware.point_cloud_manager import PointCloudManager

manager = PointCloudManager(
    os.environ['L2_RECEIVER_PATH'],
    local_ip=os.environ['WILDFIRE_LIDAR_HOST_IP'],
    lidar_ip=os.environ['WILDFIRE_LIDAR_IP'],
    restart_delays=(),
)
seen_stream = False
last_status = None
try:
    manager.start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        last_status = manager.get_status()
        frame = manager.get_latest_frame()
        print(last_status, None if frame is None else {
            'cloud_id': frame.cloud_id, 'count': frame.point_count,
            'timestamp': frame.timestamp, 'rings': frame.ring_count,
        }, flush=True)
        seen_stream = seen_stream or frame is not None
        if last_status['state'] == 'ERROR':
            raise RuntimeError('L2 trial failed; retain printed status and stderr')
        if seen_stream and last_status['state'] == 'STALE':
            raise RuntimeError('L2 trial became stale')
        time.sleep(0.1)
    if not seen_stream:
        raise RuntimeError('No fresh complete frame observed')
finally:
    last_status = manager.get_status()
    print('Before close:', last_status, flush=True)
    try:
        manager.close()
    except Exception as error:
        print('FAILED cleanup:', type(error).__name__, str(error), flush=True)
        raise
    print('After close:', manager.get_status(), flush=True)
```

Require changing valid cloud metadata, plausible XYZ/orientation in a later
approved viewer trial, and no receiver left alive after close. Empty frames
are valid but do not alone prove useful scene acquisition. Sampling the latest
frame every 0.1s does not measure the sensor's frame rate. Save status/error
output before close; STOPPED clears the manager error field.

## C. Full runtime and browser trial

Starting main commands a stand pose automatically and writes the camera tilt
angle even without key or web input. Use a physical support and clearance.
Do not use movement, calibration or pan/tilt controls for a cloud-only trial.
Confirm the actual API listener address/port after startup; the printed startup
message does not prove the daemon server bound successfully. A missing or
wildcard listener is a stop condition. The API is unauthenticated: restrict it
before starting, then later verify backend reachability and unrelated-host denial.

The primary software STOP is POST `/robot/control` with `{"command":"STOP"}`
to the verified local listener. Require an accepted response **and direct
physical observation of idle**; no status field proves the gait stopped. Web
STOP counts only with `ROBOT_GATEWAY_MODE=http` and the verified Jetson base URL.
Under mock, accepted proves nothing. There is no terminal motion-stop key.
If STOP is unavailable or movement persists, use the independent power-cut
condition. `q` is a software exit, not an emergency stop: gait/API threads remain
active during cleanup and shutdown delay must be measured. Confirm idle before
q; servo state after deinit is unverified.

Main's manager can reinitialize the real SDK up to five times with waits of
1/2/4/8/16 seconds. No service-level restart policy is provided. In the isolated
trial `get_status()` exposes restart_count directly. Full main does not publish
that field through HTTP/UI: observe warnings ending `(exit N); stderr: ...`, such as
`L2 receiver stdout closed`, `No complete point-cloud frame within timeout`, or
decoder errors, and the verified receiver PID changing. These manager warnings
reach pane stderr through the fallback handler on the current main path, not
the daily `wildfire_*.log`. Capture pane output during the approved trial. Stop the trial on
any such warning/change, unexpected motion, loss of visibility or unusual device
behavior. Record inferred retries and confirm warning visibility on the target;
absence of a visible warning is not proof of zero retries.

In the owning user's dashboard, select the registered device. The point-cloud
panel below keyboard controls must show fresh changing scene data. Sensor view
starts at the L2 origin looking +X; confirm physical mounting against a known
front/rear object. Look/zoom/reset and Overview affect only the view. For a
stationary sensor compare0.5s and1s accumulation, moving-person trails, scene
visibility and CPU/GPU load; raw coordinates are not motion-compensated. There is no range slider; filtering is fixed at
30m. Green generic system-health indicators do not prove L2 reception. The
legacy 2D LiDAR status may be unavailable because its manager is intentionally
not initialized. The live 3D feature is not SLAM, mapping accumulation or an
obstacle-avoidance guarantee.

## D. Measurement and failure record

Record observed receiver/input cadence, uploads, displayed updates, bytes/sec,
CPU/RSS/GPU usage, browser renderer and AI/video coexistence. Upload/render
selection is capped at 10Hz, not a promise of achieved 10Hz. Include Spring's
20ms stream scheduler/JWT work and the real Docker/proxy path in load testing.
The timestamp is SDK-provided with system timestamp enabled; the capture point
is opaque. Cross-host clocks need measured alignment. Neither this field nor
browser receipt freshness alone proves acquisition-to-display latency.

Use a separate approved bounded trial for sensor interruption, retries, slow
network, token expiry, stream rotation, reload/reboot and abnormal parent death.
Do not automatically repeat physical tests after a failure. Record orphan
receivers and follow operations before any restart.

Copy this record for each trial; do not prefill PASS:

| Field | Value |
| --- | --- |
| Phase, operator, approval, duration | NOT RUN |
| Git/SDK revisions, OS/JetPack/ABI/tool versions and verified virtual-environment interpreter path | NOT RUN |
| Trusted config keys checked, model/executable paths (no secrets) | NOT RUN |
| Interface/address/routes, exclusive UDP6201 | NOT RUN |
| Actual API bind, backend allow/unrelated-host deny | NOT RUN |
| Trusted-origin restriction: public camera/status/health/logs and open signup/authenticated control; unrelated-host negative reachability | NOT RUN |
| Gateway http/base URL, STOP response and observed idle | NOT RUN |
| Frame/cloud evidence, retries/PIDs, warnings | NOT RUN |
| Cadence/resources/network/proxy/AI-video measurements | NOT RUN |
| Shutdown delay, pre-close error, cleanup/orphan evidence | NOT RUN |
| Outcome, failure evidence, remaining risk, next approved action | NOT RUN |
