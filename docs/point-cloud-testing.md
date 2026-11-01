# Hardware-free point-cloud integration tests (step 5)

The opt-in `pointCloudE2e` task connects the production C++ receiver, Python
manager and uploader, Spring Security/Tomcat/H2, and the actual browser panel,
decoder and WebGL renderer. Only the sensor SDK implementation is fake. The
central login, upload and streaming HTTP endpoints are real loopback requests.
The browser mounts `PointCloudPanel` in a dedicated fixture page, not the full
App camera/mission dashboard or the user-login flow.

No real SDK library is linked, no UDP interface is opened, and `main.py`,
camera, GPIO and actuators are not started. The fake SDK throws on control
methods. Temporary users, device keys and tokens exist only for that test run;
no `.env` or production credentials are loaded. The fixture server binds
`127.0.0.1` with an in-memory H2 database and a mock robot gateway. Browser API
requests are limited to GET point-cloud streams; external traffic and control
writes fail the test.

## Prerequisites

Use a POSIX host with Java 17, Python 3.10 or newer with `requests`, a C++17
compiler, Node 18 or newer, and an installed Chrome executable. Install the
locked web dependencies with `npm --prefix web ci --ignore-scripts`.

Fetch the pinned SDK headers outside the repository as described in
[the receiver instructions](../hardware/l2_receiver/README.md). The pin is
`0e3c51f512e6b8ff60b8c32f160b412cb48445c2`, header version 2.0.9. The tests
compile `main.cpp` together with `tests/fake_sdk.cpp`; they never link the SDK's
Linux `.a` library. This is also how these tests can run on macOS.

Playwright is a test-tool prerequisite installed outside the project; it is
not a new application dependency. For example, choose an external tools folder:

```bash
export POINT_CLOUD_TOOLS_DIR=/path/to/external/point-cloud-test-tools
npm install --prefix "$POINT_CLOUD_TOOLS_DIR" --no-audit --no-fund --ignore-scripts playwright@1.56.1
export POINT_CLOUD_PLAYWRIGHT_MODULE="$POINT_CLOUD_TOOLS_DIR/node_modules/playwright/index.mjs"
export POINT_CLOUD_TEST_PYTHON="$(command -v python3)"
export POINT_CLOUD_TEST_NODE="$(command -v node)"
export UNITREE_LIDAR_SDK_ROOT=/path/to/pinned/unilidar_sdk2/unitree_lidar_sdk
export POINT_CLOUD_CHROME=/path/to/installed/chrome-executable
```

`CXX`, if provided, must be the compiler executable path, not a string of flags.
Otherwise the test uses `c++` on PATH. Set `JAVA_HOME` to Java 17 and make sure
local Gradle Java settings match the host. No particular user's tool path is
required by these tests. Chrome compatibility with Playwright must be checked
on the selected host; no browser binary is downloaded by the task.

## Commands

From the repository root, run the focused hardware-free component suites:

```bash
python3 hardware/l2_receiver/tests/test_receiver.py
python3 hardware/l2_receiver/tests/test_python_bridge.py
python3 -m unittest tests.test_point_cloud_manager tests.test_point_cloud_uploader tests.test_point_cloud_pipeline_helper -v
node --test web/tests/*.test.js
npm --prefix web run build
```

From `server/`, run the normal Java suite and the opt-in pipeline separately:

```bash
./gradlew --no-daemon test
./gradlew --no-daemon pointCloudE2e
./gradlew --no-daemon pointCloudE2e
```

The default Java task excludes the integration tag, so it does not require
Python, Node, SDK headers or Chrome. The explicit pipeline task fails if a
required environment variable is missing, a helper fails, or zero/skipped
tests are reported. It deliberately disables up-to-date and build-cache reuse:
both successive invocations must actually execute. Check the task outcome and
fresh `build/test-results/pointCloudE2e/TEST-*.xml`; a cached exit code is not
integration evidence. There are currently three pipeline JUnit test cases.
The XML and build output are generated artifacts and must not be committed.

A negative prerequisite check is also useful after a successful run:

```bash
env -u POINT_CLOUD_TEST_PYTHON ./gradlew --no-daemon pointCloudE2e
```

This command must fail with the missing-variable message. It is a negative
check, not a successful end-to-end run. Do not use unrestricted Python test
discovery here: other existing integration scripts can target configured
external services.

## What the three cases prove

- The full pipeline filters invalid/out-of-range SDK points, preserves exact
  surviving XYZ and metadata, handles empty and 12000-point frames, and replaces
  old frames. Java compares the complete server wire frame; browser probes use
  the currently mounted canvas's actual GPU upload and draw calls.
- A short pause must show stale/cleared data and resume with the same receiver
  PID and zero restarts. A deliberate parse crash must reap the old child,
  restart exactly once, and deliver distinct recovered XYZ and cloud ID 43.
  A fresh per-canvas upload counter prevents old displayed data from passing as
  recovery. A one-second restart need not visibly interrupt the viewer.
- Real ownership checks reject a non-owner with 404 and a device token used as
  a viewer with 403. Switching to the foreign device detaches the previous
  canvas and releases the old stream; switching back obtains new frame data.
- Stopping the source clears the still-mounted viewer and expires the server
  latest-frame entry. Explicit stop and stdin
  EOF shut down both helpers. A separate forced-helper-death case puts the receiver in idle mode, proves
  the reported handle is retained before any descendant snapshot, verifies it
  remains alive after its parent dies and is no longer discoverable through
  that parent, then requests its forced termination and verifies death.
  An interrupted reply wait checks cancellation without waiting for a real
  100-second method timeout.

Helper failure regressions use stub managers, uploaders, SDK headers and a fake
compiler; they perform no network or sensor access. They assert that malformed
commands, compiler errors and manager/uploader cleanup failures after stdin EOF
exit nonzero. Cleanup errors are retained across repeated cleanup calls, rather
than being treated as requested cancellation. The fake SDK also rejects unknown
control-file words instead of silently emitting normal frames.

Existing focused tests cover malformed frames, token expiry, quotas, retry
budgets, slow streams and shutdown exceptions. The pipeline does not duplicate
all of those cases. The browser uses explicit SwiftShader flags and reports its
actual renderer string; this is software rendering, not real GPU validation.

## Bounds and cleanup

JUnit method timeouts use the same test thread: full pipeline 100 seconds,
EOF 60 seconds and forced kill 35 seconds. Reply readers run on separate daemon
threads with bounded queues and diagnostics; waits on the JUnit thread are
interruptible. `@AfterEach` finishes before JUnit deletes its temporary folder.
Both helpers are closed in parallel under one 18-second grace period, followed
by a shared four-second forced process verification and two seconds for reader
cleanup. Python's production close allowances can total 13 seconds, so the
helper shutdown grace exceeds them.

The aggregate method/cleanup budget is 267 seconds. The Gradle task's
420-second last-resort timeout leaves 153 seconds for Spring, worker startup
and overhead. Each case compiles its own fake-linked binary within its method
budget. Helper input EOF requests one cleanup path; Python signal handlers set
only a plain flag, and the stdin reader uses unbuffered descriptor reads.
Java records receiver/browser handles and snapshots descendants before explicit
stop as well as forced termination. A process surviving graceful shutdown fails
the test before fallback forced cleanup can hide it. Its temporary folder owns binaries, control files, Vite cache and
helper temporary files. These are removed after the recorded processes stop.

A hard kill of the entire supervisor, OS/kernel stalls, or a child that cannot
be killed cannot guarantee JUnit callbacks or temporary-file removal. These
conditions fail the task; they are not successful cleanup evidence.

## Remaining hardware work

Passing software tests does not verify Jetson ABI/linking with the real SDK,
L2 data timing, physical sensor alignment, real GPU/touch behavior, production
proxy buffering, bandwidth, actual frame rate or AI/video coexistence. Those
belong to step 6. Include the 20ms Spring stream scheduler's JWT work in the
load measurement. Operator startup/deployment instructions remain step 7.
