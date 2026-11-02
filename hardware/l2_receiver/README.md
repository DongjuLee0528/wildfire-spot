# Unitree L2 point-cloud receiver (step 1)

Standalone Linux C++17 receiver. This step does not modify `main.py`, the Python
runtime, Spring, the web UI, or the existing 2D obstacle manager. It does not use
ROS/ROS2 or PCL. No sensor command is issued explicitly: no rotation, mode,
reset, timestamp, IP, or MAC configuration calls. The opaque SDK's internal
initialization behavior has not been verified on hardware.

## SDK dependency

Official repository: https://github.com/unitreerobotics/unilidar_sdk2

Pinned revision: `0e3c51f512e6b8ff60b8c32f160b412cb48445c2` (header version 2.0.9).
It provides Linux `aarch64` and `x86_64` static libraries; these cannot be linked
as native macOS libraries. SDK files and binaries are not vendored in this repo.
Retain the upstream BSD-3-Clause license when distributing the SDK or linked
executables. This repository's existing license is unchanged.

On the Jetson/Linux build host, install CMake, a C++17 compiler, and Git. Fetch
the dependency outside this repository and build outside the source tree:

```bash
mkdir -p ~/workspace
git clone https://github.com/unitreerobotics/unilidar_sdk2.git ~/workspace/unilidar_sdk2
git -C ~/workspace/unilidar_sdk2 checkout --detach 0e3c51f512e6b8ff60b8c32f160b412cb48445c2
cmake -S ~/wildfire-spot/hardware/l2_receiver -B ~/workspace/wildfire-l2-build \
  -DCMAKE_BUILD_TYPE=Release \
  -DUNITREE_LIDAR_SDK_ROOT="$HOME/workspace/unilidar_sdk2/unitree_lidar_sdk"
cmake --build ~/workspace/wildfire-l2-build --parallel 2
```

If either destination already exists, inspect it rather than overwriting it.
The Linux production link and Jetson ABI compatibility must still be verified
on the target. Building does not run the executable or interact with hardware.

## Runtime contract

**Do not run as part of build/tests.** Hardware execution is a separate step.
The host interface must already have `192.168.1.2/24`, the L2 must already send
3D UDP to that host on port 6201, and no competing receiver should own that port.
This program does not configure the interface or start a stopped LiDAR.

After hardware execution is approved, its invocation is:

```bash
~/workspace/wildfire-l2-build/l2_receiver 192.168.1.2 192.168.1.62 > /tmp/l2-frames.bin
```

The two positional addresses may be omitted for these defaults. Ports are 6101
(sensor) and 6201 (host). Scan aggregation is explicitly 18, matching the SDK
default; it has not been tuned or benchmarked. The SDK range filter is set to
30m; an additional Euclidean XYZ filter rejects points outside the inclusive
30m radius, zero-distance points, and non-finite coordinates. No intensity or
IMU data is exported in this version.

Standard output is **binary only**. SDK stdout is redirected to stderr before
initialization. All diagnostics go to stderr. Direct binary output to a terminal
is refused. The example writes an unbounded capture file: stop it promptly and
delete the capture when finished. A future Python consumer should drain stdout
continuously and retain only the latest complete frame.

### Wire format v1

Each frame is a 32-byte header followed by `count * 12` bytes of XYZ data. All
integers, IEEE-754 floats, and doubles are explicitly little-endian. Python's
header format is `<4sIIIdII`; payload format is repeated `<fff`.

| Offset | Type | Meaning |
| --- | --- | --- |
| 0 | 4 bytes | ASCII `L2PC` |
| 4 | uint32 | Version: 1 |
| 8 | uint32 | Payload length, exactly count * 12 |
| 12 | uint32 | Point count after filtering, at most 12000 |
| 16 | float64 | SDK cloud start timestamp, system timestamp enabled, seconds |
| 24 | uint32 | SDK cloud ID (not a new local sequence counter) |
| 28 | uint32 | SDK ring count |
| 32 | float32 triples | x, y, z in meters |

Coordinates preserve the SDK LiDAR frame: +X opposite the bottom cable outlet,
+Y 90 degrees counterclockwise from +X, and +Z perpendicular to the bottom.
No pose compensation, SLAM, accumulation, or web-axis transformation is applied.
An empty filtered cloud is a valid header with zero payload. Oversized input
clouds and non-finite/negative timestamps cause an error rather than silent truncation.
When this system-timestamp-configured producer receives a cloud with timestamp 0,
it skips that cloud without changing its SDK time, coordinates, or ID. The first
such observation is warned once; the total is included in the final diagnostic.
Only an emitted cloud with a positive SDK timestamp refreshes the five-second
watchdog. Persistent zero timestamps therefore fail rather than keeping a
non-ready source alive. Consumers still accept timestamp 0 in v1 for backwards
compatibility; no wire-format or backend/web validation change is required.

### Failure and shutdown

- SIGINT/SIGTERM requests termination; the program closes the UDP reader and
  output descriptor. It does not stop the physical LiDAR rotation.
- Five seconds without a complete SDK 3D cloud with a positive timestamp causes an error when control
  returns from `runParse()`. IMU packets alone do not refresh that deadline.
- A stalled output consumer causes an error after two seconds. A disconnected
  output consumer causes an error without SIGPIPE terminating cleanup.
- Exit codes: 0 for help/requested shutdown, 1 for runtime failure, 2 for invalid
  arguments or terminal output. Errors are reported on stderr.
- Standard and unknown runtime exceptions are logged, then UDP cleanup is
  attempted once after successful initialization. A false return, standard
  exception, or unknown exception from `closeUDP()` is also logged and results
  in exit code 1; an earlier runtime error is preserved in the log. Cleanup is
  not retried, and the output descriptor is closed even if SDK cleanup throws.
- A signal can leave a partial final frame; consumers must discard it on EOF.
- The SDK interface has no virtual destructor or destroy factory. The receiver
  calls `closeUDP()` and lets process exit reclaim the factory object's memory;
  it does not delete through the abstract base pointer.
- The SDK binary's internal blocking/thread behavior is not source-verified.
  The five-second watchdog and signal handling cannot interrupt an indefinitely
  blocked SDK call. Target testing is required before claiming bounded shutdown.
- The standalone executable has no automatic reconnect or supervision. The
  Python integration below owns restart and shutdown behavior.

## Hardware-free verification

With the pinned SDK checked out, run on macOS or Linux:

```bash
UNITREE_LIDAR_SDK_ROOT="$HOME/workspace/unilidar_sdk2/unitree_lidar_sdk" \
  python3 hardware/l2_receiver/tests/test_receiver.py
```

The tests compile the actual receiver against official headers and a fake SDK
implementation. The fake does not open sockets or access devices. It fails if
control/configuration methods are called. Tests cover binary framing, 30m
boundaries, invalid points/timestamps, frame limits, SDK initialization failure,
empty clouds, missing data, blocked/disconnected consumers, SIGINT/SIGTERM,
runtime exceptions, cleanup failure/exception, simultaneous runtime/cleanup
exceptions, initial-zero recovery and persistent-zero timeout.
This verifies application logic, not the real SDK library, Linux linking, sensor
parsing accuracy, Jetson performance, or hardware behavior.


## Python runtime integration (step 2)

`RobotRuntimeContext`, constructed by `main.py`, owns a
`hardware.point_cloud_manager.PointCloudManager`. It starts the receiver in a
background worker without delaying camera/fire startup. The existing 2D
`lidar_manager` remains uninitialized; no second UDP receiver is added. L2
frames now reach Spring and the web panel through the dedicated uploader;
manager restart/error state is not exposed through the HTTP status APIs.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| L2_POINT_CLOUD_ENABLED | true | Set false to disable the receiver |
| L2_RECEIVER_PATH | ~/workspace/wildfire-l2-build/l2_receiver | Compiled executable path |
| WILDFIRE_LIDAR_HOST_IP | 192.168.1.2 | Existing host address setting |
| WILDFIRE_LIDAR_IP | 192.168.1.62 | Existing sensor address setting |

Build the receiver first using the pinned SDK instructions above. `main.py`
then starts it automatically when enabled. No binary, SDK, or interface
configuration is installed automatically. Missing/non-executable binaries,
invalid IPv4 configuration, or process-spawn errors are reported without
preventing other runtime managers from initializing. Do not execute `main.py`
for software-only verification: it also initializes robot hardware.

`runtime.point_cloud_manager.get_status()` returns state, error, local receipt
age, restart count, child PID, and last reaped child exit code (`last_exit_code`).
States are STOPPED, STARTING, STREAMING,
STALE, RESTARTING, STOPPING, or ERROR. `get_latest_frame()` returns an immutable
`PointCloudFrame`, or None if no fresh data exists. `frame.data` preserves the
complete v1 binary frame. Empty clouds are valid fresh frames. This API does
not imply obstacle avoidance or safe navigation, and does not change existing
sensor/health API response schemas.

The decoder checks magic, version, size/count consistency, the 12000-point
limit, timestamps, finite XYZ values, and the inclusive 30m Euclidean range.
Malformed data terminates that receive attempt. Partial frames are not carried
across process restarts. Only the latest complete frame is retained, receive
chunks are bounded to 65536 bytes, and stderr is continuously drained with a
4096-byte diagnostic tail. There is no unlimited frame/log queue.

Freshness uses the parent's monotonic receipt time, independent of the SDK's
wall-clock timestamp. After two seconds without an updated frame, get_status
reports STALE and get_latest_frame returns None. After six seconds without a
complete frame (including during SDK initialization), the worker terminates the
child. Exit, malformed frames, and timeouts clear the cached frame. Restart
waits are 1, 2, 4, 8, and 16 seconds: at most five restarts per start() call.
A stable connection does not reset this budget. Exit code 2 and executable/spawn
configuration errors are permanent until the configuration is fixed and start()
is invoked again. Call start only from the owner, never from a read/status API.

close() interrupts a restart delay, requests termination, waits up to three
seconds, then kills and waits up to one more second. Cleanup failure is logged,
keeps the original error context, and disables further automatic restarts. A
child that cannot be reaped remains an error and blocks another start. Repeated
start while running is idempotent. Repeated normal close is idempotent; a retained
shutdown failure is raised again on repeated close until a new explicit start.
main.py explicitly
closes this manager before unrelated hardware cleanup; RuntimeContext.close()
also closes it safely. Main normally enters cleanup on q; Ctrl-C only interrupts when the terminal
is not in raw mode. q is not an immediate motion stop. SIGKILL,
parent crashes, OS/kernel stalls, and a child that cannot be killed/reaped
cannot be guaranteed clean shutdown. No physical sensor reset/reconfiguration
is attempted for recovery.

Hardware-free Python tests, using temporary child programs and mocked runtime
hardware managers:

```bash
python3 -m unittest tests.test_point_cloud_manager -v
```

To verify the actual step-1 C++ receiver feeding the Python manager, using the
real official headers and the hardware-free fake SDK implementation:

```bash
UNITREE_LIDAR_SDK_ROOT="$HOME/workspace/unilidar_sdk2/unitree_lidar_sdk" \
  python3 hardware/l2_receiver/tests/test_python_bridge.py
```

Tests do not run main.py or the real SDK library. They cover framing, invalid input,
staleness, bounded restart/recovery, stderr backpressure, process termination,
and runtime ownership/shutdown ordering. Actual Jetson integration and workload
performance remain unverified until hardware testing.

For target trials use [Jetson validation](../../docs/jetson-validation.md).
For configuration, terminal sessions and recovery use [operations](../../docs/operations.md).


## Timestamp and shutdown diagnostics (step 2)

A Jetson capture observed the first SDK cloud timestamp as 0 and subsequent
clouds with positive epoch timestamps. The wrapper previously exported 0 as-is;
it never computed that timestamp. The pinned public SDK utilities select system
time when requested, but the aggregate reader implementation is supplied as a
Linux static library. This work does not establish why that first aggregate
cloud was unset, nor does it modify, sync, reset or otherwise command the sensor.
Skipping unset timestamps is a producer readiness policy, not a diagnosis of
sensor failure or a replacement timestamp.

The receiver writes bounded lifecycle diagnostics to stderr, outside the binary
stream: receive-loop completion with the actual SIGINT/SIGTERM number (or 0),
zero-timestamp skip total, `SDK closeUDP begin`, `SDK closeUDP complete` on success,
and a final `Exit result=N; signal=N; skipped_zero_timestamps=N` summary before return. C++ and unknown exceptions retain their
existing error diagnostics. Markers identify the last reached stage; they are
not a stack trace or proof of where earlier memory corruption originated. A
fatal OS signal cannot be caught by the C++ exception handler. A final marker
also cannot prove that destructors/SDK process teardown later completed.

A previous Jetson signal-based stop produced a core-dump message, but no usable
crash trace was available. The cause remains UNVERIFIED. No speculative SDK
upgrade, cleanup bypass, crash handler, or sensor reset is added. Real-SDK crash
reproduction and a usable crash trace are still required before claiming the
core-dump cause is fixed. Do not automatically repeat a physical trial.

Python retains `last_exit_code` after reaping, including negative POSIX signal
codes, and logs the bounded stderr tail for nonzero exits during requested
shutdown. Runtime/SDK failure codes or unexpected fatal signals during shutdown
are retained as ERROR; `close()` raises the same error on repeat calls until a
new explicit start resets the run. A cleanup exception during requested stop is
also preserved. Existing requested SIGINT/SIGTERM and forced SIGKILL fallback
remain reaped STOPPED outcomes (and are logged when nonzero); STOPPED certifies
process removal, not that SDK cleanup or physical rotation stopped. Normal
exit 0 stays idempotent. Startup/runtime retries and all shutdown deadlines stay
unchanged. This Python change does not add actuator or GPIO operations.

Deploy this step by updating the Jetson repository and rebuilding the standalone
receiver using the existing commands above. No frontend or backend JAR update
is needed. Building is hardware-free; running the rebuilt receiver or main.py
requires a separately described and approved physical trial.


The Python manager emits one `L2_RECEIVER_EXIT` JSON line to its text stdout for
each reaped child, including normal exit 0. It contains the PID, actual exit
code, and parsed numeric native result/signal/zero-skip count from the bounded
stderr tail. Missing native summaries (old executable, forced termination or
crash before final summary) use null, never an invented zero. The event uses
the same tee text log as the existing Python metrics; inspect it from the second
terminal with `grep 'L2_RECEIVER_EXIT' /path/to/the-run.log`. In the test pipeline
helper it goes to diagnostic stderr, leaving JSON protocol stdout unchanged.
This is how a normal first-zero skip stays observable even when the Python
frame metric correctly reports `zero_timestamps: 0` for exported frames.
