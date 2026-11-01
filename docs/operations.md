# Point-cloud deployment and operations (step 7)

This is a runbook, not a deployment record. Jetson/L2 physical verification is
**NOT RUN**; use the [validation checklist](jetson-validation.md) before physical
execution. [Software integration tests](point-cloud-testing.md) use a fake SDK,
loopback services and software WebGL and do not certify real hardware.

## Components and build

| Component | Artifact and role |
| --- | --- |
| Jetson | `main.py` in the working virtual environment; owns L2 receiver, camera/inference and robot hardware |
| L2 receiver | Native Linux executable outside Git, `~/workspace/wildfire-l2-build/l2_receiver` by default |
| Backend host | Java 17 JAR and MySQL; receives device-authenticated uploads, serves owner-authenticated streams |
| Web host | React `web/dist` deployed through the existing private Docker/web setup |

On the selected build host, from the repository root, with `JAVA_HOME` pointing
to Java 17 and existing build prerequisites installed:

```bash
(cd server && ./gradlew --no-daemon -Dorg.gradle.java.home="$JAVA_HOME" bootJar)
npm --prefix web ci --ignore-scripts
npm --prefix web run build
```

Outputs are `server/build/libs/wildfire-spot-server-0.1.0-SNAPSHOT.jar` and
`web/dist`. The Java override avoids the existing machine-specific Gradle JDK
setting. Do not commit outputs, SDK files or environment secrets. On Jetson,
follow the receiver's [pinned SDK build](../hardware/l2_receiver/README.md#sdk-dependency).
This compiles/links only; do not add executable runs to the build.

Preserve the working Jetson virtual environment and record package versions before changes.
The `.venv` path used below assumes the existing target directory; confirm its
interpreter and record its actual path in the Phase A inventory before execution.
Do not blindly reinstall open-ended Torch/torchvision requirements; matching
JetPack/CUDA packages and native SDK ABI still need target verification. Main
must run from the repository root for relative model paths. Default checkpoint:
`models/wildfire_baseline/weights/best.pt`; `WILDFIRE_MODEL_PATH` can override it.

## Robot configuration and access boundary

Create `.env.robot` from `.env.robot.example` only if absent. Preserve an existing
file and compare its key names with the updated template without printing secret
values: ignored files are not updated by `git pull`. Set permissions to owner
read/write. It is a trusted shell file, not automatically loaded by Python.
Single-quote secret values containing shell metacharacters; do not enable shell
tracing or paste credentials into logs. Do not source an untrusted file.

Required choices before execution:

- Replace `SPRING_API_BASE_URL=http://localhost:8080` with the reachable backend
  URL when it is on another host. Use the registered device serial/key, not user
  credentials. For a non-local backend use HTTPS or an authorized tailnet path;
  untrusted plaintext HTTP exposes device keys/tokens. Set the final URL directly:
  the uploader does not follow redirects and a redirect permanently stops it.
  The template explicitly enables telemetry; blank credentials are
  placeholders and must be filled before main. L2 upload needs telemetry enabled.
- Confirm `L2_POINT_CLOUD_ENABLED=true`, executable `L2_RECEIVER_PATH`, and existing
  `WILDFIRE_LIDAR_HOST_IP` / `WILDFIRE_LIDAR_IP`. The 30m range is compiled into the
  receiver, not a shell setting. Address/interface persistence is not installed.
- Explicitly set nonblank `ROBOT_API_HOST` and numeric `ROBOT_API_PORT` (1–65535).
  The template uses loopback `127.0.0.1:8000`, which a separate backend cannot
  reach. Choose a present trusted interface address for that deployment and
  restrict port access to the backend host. An absent key defaults main to
  `0.0.0.0`; an empty value is not a safe restriction. Check the selected address
  exists after each reboot before starting main.

The robot API has **no authentication**. Reachable callers can issue motion and
camera commands without Spring JWT checks. Spring ownership checks apply to
point-cloud viewing, not the legacy motion/mode/camera control routes. Specific binding alone
does not authorize callers: require backend-only firewall/tailnet rules and
verify an unrelated host cannot reach it. Actual rules and connectivity remain
UNVERIFIED. Do not expose this port to public networks.

Export configuration in the same shell/pane that will start Python:

```bash
set -a
. ./.env.robot
set +a
```

A plain source without export is insufficient. `sudo` may discard environment
settings; use the established account/device permissions rather than assuming
sudo preserves them. Do not display environment values to troubleshoot auth.

## Backend and web configuration

The backend reads `.env` as Spring properties relative to its working directory,
not as a sourced shell script. Preserve the existing private file; use
`server/.env.example` for key names only. Required values include `JWT_SECRET`,
`MYSQL_DATABASE`, `MYSQL_USER` and `MYSQL_PASSWORD`; confirm host/port and token
lifetime. Start the JAR from the directory holding this `.env`, or use a verified
process environment. Existing environment/property values can override profile
defaults: the example explicitly sets `ROBOT_GATEWAY_MODE=mock`.

For actual camera/control access set `ROBOT_GATEWAY_MODE=http` and
`ROBOT_API_BASE_URL` to the reachable restricted Jetson API. Mock mode can accept
a web STOP without contacting hardware. Confirm actual routing before relying on
it. Point-cloud upload uses the robot's outbound backend URL independently.

Backend startup uses `ddl-auto=update` and can modify the database schema. Have a
separately reviewed database backup before an upgrade. Switching JARs does not
undo schema changes; do not improvise database restore commands.

No production Docker/Compose/nginx or service configuration is in this checkout.
Container names, mounts, release paths and proxy configuration are UNVERIFIED;
inspect the existing private deployment before copying `dist` or restarting it.
The Vite development proxy is not production forwarding. The deployed origin
must forward same-origin `/api` requests to the backend. Requirements:

- Point-cloud stream `/api/devices/{id}/point-cloud/stream`: preserve bearer
  Authorization and Spring ownership enforcement; disable response buffering
  and caching, allow streaming and normal reconnect/60-second stream rotation.
- Camera `/api/camera/stream`: disable buffering/cache. It currently permits
  unauthenticated requests; the dashboard image sends no bearer header. Adding a
  proxy bearer requirement would break that image flow without further changes.
- `/api/status`, `/api/health` and `/api/logs` also permit unauthenticated reads.
  Restrict the web/backend origin to trusted networks pending separately reviewed
  authentication work. Do not describe these routes as protected by user JWT.

Signup at `/api/auth/signup` is open. Any authenticated USER can issue motion,
mode and camera-control commands without device ownership checks in http gateway
mode. Restricting the robot API to the backend alone does not prevent this path.
The trusted-network origin restriction is therefore a required motion-safety
boundary, not just a privacy measure. Do not enable http gateway mode on an
origin reachable beyond authorized operators; separate authorization work is open.

## Start and keep running after SSH disconnect

**Start the backend first and verify it is reachable before starting main**,
including after reboot. Then start the robot and open the deployed web UI.
The robot instructions below describe its terminal setup, not an alternate start
order. Main attempts ordinary device telemetry login only once; a failed login
leaves heartbeat/GPS/sensor/fire telemetry disabled for that process lifetime.

Full main initializes sensors and actuators, commands an automatic stand pose,
and sets camera tilt to 90 degrees even without input. Use only after the full
runtime trial is approved, with support, clearance and independent power-cut
readiness. Keep cloud testing free of motion/calibration commands.

Use a dedicated tmux terminal because main uses raw terminal input. From the
repository root on Jetson, create a session (inspect/attach if already present):

```bash
tmux new-session -s wildfire-robot -c "$PWD"
```

Inside that session, confirm the repository directory and configuration, then:

```bash
set -a
. ./.env.robot
set +a
.venv/bin/python -u main.py
```

Verify the actual listening address/port locally after start, for example with
`ss -ltnp`, and compare it with the explicit configured host/port. The startup
print does not confirm the daemon server actually bound. Missing or wildcard
binding is a stop condition; backend-only reachability must also be tested.
Main's L2 manager internally retries up to five times with 1/2/4/8/16s waits.
This is separate from service-level restarts, which this runbook does not install.

Detach with Ctrl-B then lowercase `d`; reconnect with:

```bash
tmux attach-session -t wildfire-robot
```

These are standard [tmux session operations](https://github.com/tmux/tmux/wiki/Getting-Started).
Do not close/kill the pane or session to stop main. No automatic startup,
service restart, `nohup`/SIGTERM shutdown policy is supplied.

For the backend, first change into the existing deployment directory containing
its `.env` and JAR, then create a separate session:

```bash
tmux new-session -s wildfire-backend -c "$PWD"
```

Inside that directory/session, with Java 17 selected:

```bash
java -jar wildfire-spot-server-0.1.0-SNAPSHOT.jar
```

Check backend startup without printing secrets. Detach/attach as above using
`wildfire-backend`. The Java foreground process can be stopped with Ctrl-C in its
verified pane. Never stop all Java/Python processes indiscriminately.

## Stop, abnormal exit and reboot

The terminal has no motion-stop key. Primary software STOP is POST
`/robot/control` with JSON `{"command":"STOP"}` to the verified local listener,
or web STOP only with the confirmed http gateway/base URL. Require accepted
response and direct physical observation of idle; API status alone is not proof.
If unavailable or motion persists, use the independent power-cut condition.

After confirmed idle, attach the robot session and press `q` for software exit.
It does not stop motion immediately: gait/API threads remain alive through
cleanup, and actuator state after driver deinit is unverified. Raw mode can
consume Ctrl-C as a character; do not promise it interrupts main. Record shutdown
delay and confirm the Python parent and receiver exited and UDP6201 is released.

A crash, SIGTERM/SIGHUP or killed pane can bypass cleanup. The receiver has its
own session and can survive the parent. Before restarting: confirm main is gone,
inspect candidate `l2_receiver` processes, verify exact PID and executable path
(e.g. `/proc/<verified-pid>/exe` on Linux), and inspect UDP6201 ownership with
`ss -lunp` using appropriate observation permissions. Only then request termination
of the verified orphan PID. If graceful termination fails, review its retained
identity before targeted forced cleanup; do not use `killall` or blind PID reuse.
Confirm death/port release before another receiver. Servo/camera cleanup cannot
be assumed after abnormal exit; physically secure the robot before recovery.

After reboot tmux sessions do not survive. Recheck addresses/routes, chosen API
bind address, Tailscale connectivity/authorization, model, `.venv`, executable and
port ownership before a controlled manual restart. Start and verify the backend
first, then main. A Tailscale address is stable
while registered, subject to administrative change; it is not a public static IP.
Both devices still need connectivity and allowed access. See
[Tailscale address behavior](https://tailscale.com/docs/concepts/ip-and-dns-addresses).
Expired device keys can stop connectivity; inspect
[key expiry](https://tailscale.com/docs/features/access-control/key-expiry) with
alternate access available before reauthentication. Do not force reauth over the
only remote session or silently disable expiry.

Receiver failures warn with `(exit N); stderr: ...`, for example
`L2 receiver stdout closed` or `No complete point-cloud frame within timeout`;
decoder errors use the same shape. On the current main path these manager
warnings go to pane stderr through Python's fallback handler, not the daily
`wildfire_*.log` file. Capture pane output during the approved trial and confirm
its visibility on the target. Watch verified receiver PID changes independently.

## Update, rollback and troubleshooting

Before pull/switch on the target inspect `git status` and preserve local changes.
Patrol calibration can rewrite tracked `utils/config.py` with site GPS points;
preserve that private state locally and do not commit it accidentally. Preserve
existing environments, previous matching artifacts and SDK revision. Avoid blind
reset/overwrite. Stop normally before changing a release; verify the new build
and repeat the approved validation as needed. Roll back to matching prior
artifacts/configuration, remembering database changes are not reversed by a JAR.

| Observation | Check before retrying |
| --- | --- |
| Receiver ERROR/no frames | Exact executable/ABI, host address, exclusive UDP6201, pre-close error/stderr; ping alone is insufficient |
| Full-main receiver changes | Warning ending `(exit N); stderr: ...` or verified PID change; no HTTP restart counter exists, stop trial and retain pane stderr |
| Viewer stale/empty | Correct owner/device, registered credentials, telemetry enabled, fresh uploads and real proxy; empty clouds can be valid |
| `device login failed — telemetry disabled` or `Device credentials rejected` | Does not self-recover: fix backend/configuration, then use a controlled approved main restart; this repeats actuator initialization |
| Camera/control unavailable | http vs mock, actual Jetson listener, restricted reachability and base URL |
| Looks healthy but no 3D data | Generic health lights are not L2 evidence; legacy 2D manager is intentionally unavailable |
| Slow cloud or detection | Measure receiver/upload/display cadence and resources with AI/video; do not tune SDK aggregation or dependency versions by guess |

No real Jetson performance or production proxy result is asserted by this guide.
