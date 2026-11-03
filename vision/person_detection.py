import copy
import logging
import math
from pathlib import Path
import threading
import time


logger = logging.getLogger(__name__)
MAX_PERSON_DETECTIONS = 100


class PersonDetectionError(ValueError):
    pass


def _load_model(path):
    from ultralytics import YOLO
    return YOLO(str(path))


class PersonDetector:
    def __init__(self, source, model_path, *, fps=10, confidence=0.5, max_age=0.5,
                 model_factory=_load_model, clock=time.monotonic):
        if (source is None or not math.isfinite(fps) or not 0 < fps <= 10 or
                not math.isfinite(confidence) or not 0 < confidence <= 1 or
                not math.isfinite(max_age) or max_age <= 0):
            raise ValueError('Invalid person detection settings')
        self._source = source
        self._path = Path(model_path).expanduser()
        self._period, self._confidence, self._max_age = 1 / fps, confidence, max_age
        self._factory, self._clock = model_factory, clock
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._lifecycle = threading.RLock()
        self._thread = None
        self._state, self._error = 'STOPPED', None
        self._model_available = False
        self._latest = None
        self._inferences = 0
        self._shutdown_error = None
        self._last_expiry_warning = None

    def _set_state(self, state, error=None):
        with self._lock:
            if self._shutdown_error is not None:
                state, error = 'ERROR', self._shutdown_error
            self._state, self._error = state, error

    def start(self):
        with self._lifecycle:
            if self._thread is not None and self._thread.is_alive():
                if self._stop.is_set():
                    raise RuntimeError('Person detection worker is still stopping')
                return
            self._stop.clear()
            with self._lock:
                self._latest, self._inferences, self._model_available = None, 0, False
                self._shutdown_error = None
                self._last_expiry_warning = None
            self._set_state('STARTING')
            try:
                self._thread = threading.Thread(target=self._run, name='person-detection', daemon=True)
                self._thread.start()
            except Exception:
                self._thread = None
                self._set_state('ERROR', 'Cannot start person detection worker')
                logger.error('Cannot start person detection worker')
            except BaseException:
                try:
                    self.close()
                except Exception as error:
                    logger.error('Person startup cancellation cleanup failed (%s)', type(error).__name__)
                raise

    def _parse(self, predictions, frame):
        height, width = frame.shape[:2]
        detections = []
        if len(predictions) != 1:
            raise PersonDetectionError('Unexpected person prediction batch')
        prediction = predictions[0]
        if prediction.boxes is None:
            return detections
        if len(prediction.boxes) > MAX_PERSON_DETECTIONS:
            raise PersonDetectionError('Person prediction limit exceeded')
        for box in prediction.boxes:
            category = float(box.cls[0])
            if not math.isfinite(category) or category != int(category):
                raise PersonDetectionError('Invalid person class')
            if category != 0:
                continue
            confidence = float(box.conf[0])
            bounds = [float(value) for value in box.xyxy[0]]
            if (not math.isfinite(confidence) or not 0 <= confidence <= 1 or len(bounds) != 4 or
                    not all(math.isfinite(value) for value in bounds)):
                raise PersonDetectionError('Invalid person detection')
            x1, y1, x2, y2 = bounds
            bounds = [max(0, min(width, x1)), max(0, min(height, y1)),
                      max(0, min(width, x2)), max(0, min(height, y2))]
            if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                continue
            if confidence >= self._confidence:
                detections.append({'class_id': 0, 'class_name': 'person', 'confidence': confidence, 'bbox': bounds})
        return detections

    def _run(self):
        phase = 'model loading'
        try:
            if self._stop.is_set():
                return
            if not self._path.is_file() or self._path.suffix.lower() != '.pt':
                raise PersonDetectionError('Local person model file is unavailable')
            model = self._factory(self._path.resolve())
            if self._stop.is_set():
                return
            names = model.names
            if model.task != 'detect' or not names or str(names[0]).lower() != 'person':
                raise PersonDetectionError('Person model must detect COCO class zero as person')
            with self._lock:
                self._model_available = True
            self._set_state('WAITING')
            sequence, next_at = None, self._clock()
            while not self._stop.is_set():
                remaining = next_at - self._clock()
                if remaining > 0:
                    if self._stop.wait(remaining):
                        break
                    continue
                phase = 'frame selection'
                snapshot = self._source.get_frame_snapshot(sequence)
                if snapshot is None or snapshot.sequence == sequence:
                    self._stop.wait(min(0.01, self._period))
                    continue
                if (not isinstance(snapshot.sequence, int) or snapshot.sequence < 1 or
                        not math.isfinite(snapshot.received_at) or snapshot.received_at > self._clock()):
                    raise PersonDetectionError('Invalid camera snapshot metadata')
                if self._clock() - snapshot.received_at >= self._max_age:
                    self._stop.wait(min(0.01, self._period))
                    continue
                shape = snapshot.frame.shape
                if len(shape) != 3 or shape[2] != 3 or shape[0] <= 0 or shape[1] <= 0:
                    raise PersonDetectionError('Invalid person input frame')
                if self._stop.is_set():
                    break
                sequence = snapshot.sequence
                self._set_state('INFERENCING')
                phase = 'inference'
                next_at = self._clock() + self._period
                predictions = model.predict(snapshot.frame, classes=[0], conf=self._confidence,
                                            iou=0.45, imgsz=640, max_det=MAX_PERSON_DETECTIONS,
                                            verbose=False, save=False, show=False)
                if self._stop.is_set():
                    break
                phase = 'result parsing'
                detections = self._parse(predictions, snapshot.frame)
                with self._lock:
                    if self._stop.is_set():
                        break
                    self._inferences += 1
                    age = self._clock() - snapshot.received_at
                    if age < self._max_age:
                        self._latest = (sequence, snapshot.received_at, detections)
                        self._state = 'STREAMING'
                    else:
                        self._latest, self._state = None, 'STALE'
                now = self._clock()
                if (age >= self._max_age and not self._stop.is_set() and
                        (self._last_expiry_warning is None or now - self._last_expiry_warning >= 5)):
                    logger.warning('Person inference result expired before publication (frame age %.3fs; limit %.3fs)',
                                   age, self._max_age)
                    self._last_expiry_warning = now
        except Exception as error:
            message = str(error) if isinstance(error, PersonDetectionError) else 'Person ' + phase + ' failed: ' + type(error).__name__
            self._set_state('ERROR', message)
            logger.error('%s', message)
        finally:
            with self._lock:
                self._latest = None
                self._model_available = False
                if self._shutdown_error is not None:
                    self._state, self._error = 'ERROR', self._shutdown_error
                elif self._stop.is_set() and self._error is None:
                    self._state = 'STOPPED'

    def get_latest_result(self):
        with self._lock:
            latest = self._latest
            age = None if latest is None else max(0, self._clock() - latest[1])
            fresh = latest is not None and age < self._max_age and not self._stop.is_set() and self._error is None
            state = self._state
            if latest is not None and not fresh and self._error is None and not self._stop.is_set():
                state = 'STALE'
            return {'state': state, 'error': self._error, 'model_available': self._model_available and not self._stop.is_set(),
                    'sequence': latest[0] if fresh else None, 'age_seconds': age,
                    'person_detected': bool(latest[2]) if fresh else False,
                    'detections': copy.deepcopy(latest[2]) if fresh else [], 'inferences': self._inferences}

    def request_stop(self):
        self._stop.set()
        with self._lock:
            self._latest = None

    def close(self, timeout=3):
        if not math.isfinite(timeout) or timeout < 0:
            raise PersonDetectionError('Invalid person close timeout')
        with self._lifecycle:
            self.request_stop()
            if self._thread is not None and self._thread.ident is not None:
                self._thread.join(timeout)
                if self._thread.is_alive():
                    with self._lock:
                        self._shutdown_error = 'Person detection worker did not stop'
                    self._set_state('ERROR', self._shutdown_error)
                    logger.error('%s', self._shutdown_error)
                    raise RuntimeError(self._shutdown_error)
            if self._shutdown_error is not None:
                raise RuntimeError(self._shutdown_error)
            with self._lock:
                if self._error is None:
                    self._state = 'STOPPED'
