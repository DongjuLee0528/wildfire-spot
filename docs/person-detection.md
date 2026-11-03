# Person detection: stages 2 and 3

## Scope and activation

Shared capture and a separate person-inference worker are now connected to
main.py. One main process starts/stops the worker and composes fresh person
boxes with the existing fire/smoke boxes in the existing MJPEG stream. There is
no separate person API or telemetry schema, and no frontend or JAR change.
Person results do not change fire decisions, alerts, evidence or robot movement.

Person detection is opt-in and disabled by default. Prepare the official
COCO-pretrained yolo11n.pt as models/person/yolo11n.pt, then set these environment
variables before starting main.py from the project root:

```ini
PERSON_DETECTION_ENABLED=true
PERSON_MODEL_PATH=./models/person/yolo11n.pt
PERSON_DETECTION_FPS=10
PERSON_CONFIDENCE_THRESHOLD=0.5
```

Without a PERSON_MODEL_PATH override, the default resolves relative to the
project directory, independent of the launch directory. An explicit relative
path resolves from the process working directory. FPS is bounded to 0.1–10 and
confidence to 0.01–1; invalid/non-finite numbers use defaults. The target of
10 inference starts/s is not verified Jetson throughput. The model can return
up to 100 person boxes; this is not a real-world accuracy guarantee.

The existing .env.robot is not loaded automatically: export its values using
the existing launch procedure. The example keeps person detection disabled.
No training, model download or dependency changes were performed. Missing local
weights stop only the person worker and are logged; no automatic download is
allowed. Do not replace the fire/smoke best.pt. PERSON_DETECTION_START_REQUESTED
means asynchronous startup was requested, not that model loading succeeded.
Worker errors use the project logger vision.person_detection.

No physical tests were run. Main still initializes its existing hardware and
actuator paths; tests use only fake dependencies, not a real main launch.

## Frame ownership

SharedFrameCapture owns one open capture handle and is its only read/release
worker. CameraVision opens/configures the existing device once, starts that
worker and keeps the fire-model load independent. read_frame/get_latest_frame
now return defensive copies of its latest fresh image; get_frame_snapshot
also supplies a sequence and monotonic receipt timestamp. Supplying the last
sequence skips repeated copies. The producer retains only one owned image,
not a queue. Consumers must not interpret a sequence gap as camera packet loss.

Default capture target is the existing CAMERA_FPS=30; this is not a measured
rate. Images expire after 500ms since local read completion. Read failures and
read exceptions immediately clear the shared image and retry
on the same handle at the capture interval, with one warning per failure streak.
get_status exposes read_error until recovery. Invalid image format, release
errors and shutdown timeouts remain terminal errors. There is no automatic
hardware reopen. Initialization cancellation stops capture before propagating.
Driver buffering and actual
acquisition-to-read latency are unknown; receipt age is not acquisition age.
Independent copies and continuous capture add CPU/memory bandwidth cost.

close requests stop and joins for 2s by default. The read owner releases the
handle in finally. A blocked native read is not forcibly interrupted and the
handle is not concurrently released; timeout is an explicit ERROR/exception,
not proof that the worker exited. A capture instance starts once; a new device
handle/instance is required after close or failed start.

## Person worker

PersonDetector(source, model_path) expects get_frame_snapshot(after_sequence)
on its source. start loads a local .pt detection model in its own worker and
validates class 0 is person. The model instance is used only by that worker.
The default loader is Ultralytics YOLO. predict receives one image, classes=[0],
imgsz=640, conf=0.5, iou=0.45, max_det=100, save=False and show=False. Other-class
outputs are ignored defensively. Finite boxes are clipped to the image and
zero-area boxes are ignored; other valid people continue. Non-finite values,
invalid confidence or output batches fail this worker and clear its results.
Runtime GPU selection follows the
installed Ultralytics environment; no CUDA, FP16 or TensorRT upgrade is forced.

Default inference target is at most 10 starts/second, measured with a monotonic
start deadline. Request duration counts toward the interval. Slow inference
selects a new latest snapshot on the next attempt, without catch-up work or a
frame queue. The same sequence is never inferred twice. Empty input is polled
with an interruptible 10ms wait. Logical separation does not isolate GPU/CPU
resources from fire inference, video encoding or L2.

get_latest_result returns only person state, error, model readiness, source
sequence, receipt age, inference count and copied person detections (class,
confidence and pixel xyxy box). There is deliberately no generic detected or
fire_detected flag. Results expire 500ms from frame receipt, including time
spent inferring; a late completed result is discarded. No raw frames, model
contents, identities or credentials are logged. Loading/inference errors stop
only the person worker. Explicit start can restart a finished person worker.

close clears results immediately, requests stop and joins for 3s. Model load
and native inference cannot be forcibly interrupted in a thread. A timeout
remains an ERROR even if the worker exits later; start while still stopping
is rejected. Restart after the old thread ends is explicit, never automatic.
The source camera is owned separately and must outlive the person worker.

## Fire and display compatibility

Existing fire/smoke thresholds, result keys, evidence overlay and FireDetector
rules remain unchanged. Person results are not appended to the fire result.
The MJPEG endpoint draws existing fire/smoke boxes plus yellow Person labels
with confidence percentages. Expired, stopped or failed person results have no
boxes. Rendering reads the shared camera instead of initiating native reads. No inference is added
inside an HTTP request. Fire evaluation still uses its existing sensor path
and completion-plus-interval timing. A failed fire model does not prevent
shared camera capture or a separately started person worker from running.

## Verification and remaining checks

Run only hardware-free mocks from the project root:

```bash
python3 -m unittest tests.test_frame_capture tests.test_person_detection tests.test_camera_vision_shared tests.test_person_integration
```

Tests use synthetic arrays, fake capture handles and fake models. They cover
single-reader/copy ownership, freshness, 12-person parsing, person/fire isolation,
10Hz start cadence, slow inference/latest selection, local-file-only loading,
failures, transient read recovery, initialization cancellation, clipped/degenerate
boxes, the actual MJPEG generator with fake JPEG/camera objects, blocked close
and stop during copy/parsing. This does not establish
12-real-person accuracy, actual YOLO checkpoint compatibility or Jetson 10Hz.
The actual model loader, CUDA driver, JetPack and installed Torch/torchvision
versions need target validation. Do not blindly reinstall open-ended packages.
Only package metadata was read locally; real camera/model/GPU execution was
not used to claim compatibility. Source weights and deployment are later work.

Hardware boundary review: main adds only person-worker lifecycle wiring.
Actuator, GPIO/PWM, pan/tilt, navigation, fire decision/state-machine, backend
and L2 control code are unchanged. Camera read
ownership/lifecycle is changed and still needs physical device verification
with movement power isolated before target deployment.

The MJPEG stream waits through temporary stale or missing frames while capture
is available, resumes on fresh frames, and ends on capture shutdown or fatal
error. CameraVision.release records capture/close failures in the project log
before propagating them to the caller.

Independent review found a LOW buffering risk: capture pacing also waits after
successful reads. In a synthetic 30Hz/four-buffer driver model, a 250ms stall
left about 147ms acquisition lag until the end of the measurement. That model
has not been confirmed on the real driver. Receipt-age expiry cannot detect
this backlog. Keep the bounded capture cadence for now; measure acquisition
latency and driver buffering on Jetson before changing successful-read pacing.
Long frame gaps can also exceed the existing Spring proxy read timeout (5s),
which still requires client reconnection. No automatic hardware reopen is added.

On shutdown, main requests person stop without joining, runs its existing
hardware cleanup, then joins the person worker before releasing the shared
camera. The person join and camera release also run if unrelated cleanup fails.
A person close timeout is logged and does not skip camera cleanup. A blocked
native call cannot be forcibly interrupted. Person boxes are used only by the
live overlay; fire evidence images and fire/telemetry schemas remain unchanged.

Person labels are placed inside the image bounds, including top/right-edge
boxes, when the image is large enough for the text. Fire label placement is
unchanged. Results that already exceed the 500ms receipt-age limit on completion
are dropped and emit an expiry warning at most once every 5s. Slow inference
can therefore cause flickering or no person boxes even while inferences run;
absence of boxes is not proof that no person is present. Target latency must
be measured with fire inference enabled before changing the freshness policy.
