# Local dashboard on Jetson

The local dashboard runs React and the existing Python robot API on the Jetson.
It needs no account, database, Spring server, NAS or Tailscale connection.
The NAS deployment remains the default frontend mode and keeps its login,
device selection, mission storage and Spring API routes.

## Prepare once after the changes have been committed and pushed

On the Jetson, from the existing checkout and virtual environment:

```bash
cd ~/wildfire-spot
git switch dev
git pull --ff-only origin dev
cd web
npm ci
```

Use Node.js 18+ supported by Vite 5 (Node.js 22 is suitable). Do not replace the
working Jetson Torch/CUDA environment to enable this frontend mode. Existing
Python requirements cover the API. The local launcher uses .venv/bin/python.
The first npm installation needs internet access; after dependencies and model
files are present, the local dashboard can run without internet.

## Start the robot and local API

The robot process still uses its existing hardware initialization and control
code. For a display-only verification, isolate servo/movement power first.
This change does not turn main.py into a hardware-free program.

Connect the L2 to the USB Ethernet adapter enx00e04b68daec. In terminal 1:

```bash
cd ~/wildfire-spot
sudo ip addr replace 192.168.1.2/24 dev enx00e04b68daec
bash scripts/start-local-robot.sh
```

The address is temporary and must be reapplied after reboot or interface
reconfiguration. It does not change the internet default route. The L2 remains
192.168.1.62. The receiver executable must already be built at the existing
L2_RECEIVER_PATH (normally ~/workspace/wildfire-l2-build/l2_receiver).

The launcher loads .env.robot if present, then overrides:

```ini
LOCAL_DASHBOARD_ENABLED=true
SPRING_TELEMETRY_ENABLED=false
ROBOT_API_HOST=127.0.0.1
ROBOT_API_PORT=8000
```

Even if .env.robot enables Spring, local mode skips both Spring telemetry and
point-cloud upload. No device key or serial number is required. Person detection
and L2 enable settings still use the existing configuration. For L2, ensure
L2_POINT_CLOUD_ENABLED=true, WILDFIRE_LIDAR_HOST_IP=192.168.1.2 and
WILDFIRE_LIDAR_IP=192.168.1.62 if overriding defaults. Existing person weights
and PERSON_DETECTION_ENABLED settings remain applicable; no models are bundled.
Logs are displayed in terminal 1. To also save them:

```bash
set -o pipefail
bash scripts/start-local-robot.sh 2>&1 | tee local-robot.log
```

## Start the dashboard

In terminal 2:

```bash
cd ~/wildfire-spot/web
npm run dev:local
```

On the Jetson's DP-connected monitor, open Chromium at:

http://127.0.0.1:5173/

The UI and API are deliberately bound to loopback. No login or active device is
needed. Keep both terminals running. Ctrl+C stops each process; let the robot
print STOPPED before powering it off. Use the existing mode, movement and camera
controls only when the robot is prepared for physical operation. The browser
uses the same Python command validation and managers as the NAS gateway.

For a prebuilt local frontend instead of development serving:

```bash
cd ~/wildfire-spot/web
npm run build:local
npm run preview:local
```

The address is still http://127.0.0.1:5173/. Vite preview retains the local proxy.
The local output is web/dist-local; the NAS output remains web/dist. Neither
build output is tracked. A bare file:// page or a static server without a /robot
proxy will not connect to the Python API.

## Direct connections and contracts

Vite's robot-local mode proxies /robot to http://127.0.0.1:8000 without rewriting
paths. The browser sees one origin, so permissive CORS is not enabled. Foreign
browser Origin headers are rejected by Python only while local mode is enabled.
Allowed browser origins are http://127.0.0.1:5173, http://localhost:5173 and their
8000-port equivalents. Existing NAS mode does not use this local origin guard.

| Feature | Python API | Behavior |
| --- | --- | --- |
| Live video with fire/person boxes | GET /robot/camera/stream | Existing MJPEG; no inference in the UI |
| Pan/tilt availability | GET /robot/camera/status | Existing available/pan/tilt fields; independent of video capture |
| Camera commands | POST /robot/camera/control | Existing command names, including CAMERA_STOP |
| Movement | POST /robot/control | Existing command body and accepted/reason result |
| Mode | POST /robot/mode | Existing AUTO/MANUAL body and accepted/reason result |
| Dashboard readings | GET /robot/dashboard | Local-only aggregate of existing status, GPS, sensors, fire, health and logs |
| L2 state | GET /robot/point-cloud/status | Existing manager state, age and error |
| L2 point cloud | GET /robot/point-cloud/stream | Original L2PC v1 binary frames; latest fresh frame only |

The three new read endpoints return 404 outside local mode. The local point-cloud
viewer sends no NAS token and retains the existing decoder, stale clearing,
retries and renderer. Viewers never start or stop the receiver. No frame history
is stored on the Python side; slow consumers skip older frames. Missing or stale
frames produce 503 at stream startup or close an existing stream for retry.

The dashboard polls non-overlapping snapshots with a 10s request timeout, waiting
2s between completed requests. Failures clear old readings and health flags.
Missing measurements stay unknown; they are not zero, GPS acquired or healthy.
The existing collector treats incomplete environmental readings as unavailable,
so a missing DHT can leave the environmental panel unknown. Battery has no
Python source and remains unknown. Confidence is shown only when the existing
vision result reports model availability; fire state is not invented severity.

Local mode hides accounts, devices, persisted missions/history and the illustrative
GPS map. It does not send requests to /api. Logs come from /robot/logs through the
collector: main currently supplies no log reader, so the panel explicitly says
no entries are available. Terminal 1 remains the actual runtime log. No sample
success logs or permanently green local health indicators are inserted.

## Troubleshooting without starting another robot process

```bash
curl -sS http://127.0.0.1:8000/robot/dashboard
curl -sS http://127.0.0.1:8000/robot/point-cloud/status
ip route get 192.168.1.62
```

The L2 route should show enx00e04b68daec and source 192.168.1.2. A LiDAR 503 means
there is no fresh receiver frame; it does not mean a NAS route is needed.
A camera error can be retried with Reconnect camera after addressing the device.
Missing DHT/GPS remains unavailable and does not prevent video or L2 display.

## Existing NAS mode

Run the existing robot launch without LOCAL_DASHBOARD_ENABLED=true. Unset that
variable or set it false if exported in the shell. Existing /api routes, auth,
NAS build/deployment and Spring telemetry settings are unchanged. npm run dev
still proxies /api to localhost:8080; npm run build still creates web/dist.
Do not deploy web/dist-local as the NAS frontend: it intentionally has no login.

## Verification limits

Mac verification uses injected fake managers, synthetic camera images and binary
fixtures. It does not open real cameras, run main.py on hardware, move servos,
start the native receiver or contact the deployed NAS. Actual Jetson display/GPU
performance, 9FPS/5200-point streaming and physical controls require target checks.
The Python API and Vite loopback origins are local-only; the mode intentionally
adds no remote access or standalone production reverse proxy.
