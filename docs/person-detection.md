# Person detection: stage 2

## Scope and activation

This stage adds shared camera capture and a separate person-inference worker.
It does not add person boxes, a person API, device telemetry, environment flags,
or a person-worker startup/shutdown connection in main.py. Those belong to
stage 3. Starting the existing main still runs only its existing fire/smoke
model; the camera is now continuously read by one capture worker rather than
by each video viewer and fire evaluation. No physical tests were run here.

No training, model download, dependency changes, frontend build or JAR change
is part of this stage. Prepare the official COCO-pretrained yolo11n.pt locally
before activating the worker in the later integration stage. A missing file
fails the person worker before importing its model loader; it never downloads
a replacement. Do not replace the existing fire/smoke best.pt.

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
The current MJPEG endpoint still draws only existing fire/smoke boxes; it reads
the shared camera instead of initiating native reads. No inference is added
inside an HTTP request. Fire evaluation still uses its existing sensor path
and completion-plus-interval timing. A failed fire model does not prevent
shared camera capture or a separately started person worker from running.

## Verification and remaining checks

Run only hardware-free mocks from the project root:

```bash
python3 -m unittest tests.test_frame_capture tests.test_person_detection tests.test_camera_vision_shared
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

Hardware boundary review: no main, actuator, GPIO/PWM, pan/tilt, navigation,
fire decision/state-machine, backend or L2 control code is changed. Camera read
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
