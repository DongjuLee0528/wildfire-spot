"""
Camera-based fire and smoke detection using YOLO inference.

Opens a V4L2 camera device, captures frames, and runs YOLO model
inference to detect fire and smoke. Designed for optional use alongside
sensor-based detection; all failures degrade gracefully.
"""

from utils.config import (
    CAMERA_DEVICE,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    CAMERA_FPS,
    MODEL_PATH,
    CAMERA_CONFIDENCE_THRESHOLD,
    CAMERA_IOU_THRESHOLD,
    CAMERA_FIRE_CLASSES,
)
import threading
from utils.logger import WildfireLogger

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

_BBOX_COLOR = {
    "fire": (0, 0, 255),
    "smoke": (255, 0, 0),
}
_BBOX_COLOR_DEFAULT = (0, 255, 0)

# Canonical empty result used as a template when camera or model is unavailable.
# Always copied before returning to prevent callers from mutating the shared object.
_EMPTY_RESULT = {
    "camera_available": False,
    "model_available": False,
    "detected": False,
    "fire_detected": False,
    "smoke_detected": False,
    "confidence": 0.0,
    "detections": [],
}


def _copy_result(result):
    """
    Return a shallow copy of a detection result with a fully independent detections list.

    Bbox lists inside each detection are also copied so callers cannot mutate
    the stored _latest_result through a returned reference.
    """
    copied = dict(result)
    copied["detections"] = [
        {
            **detection,
            "bbox": list(detection["bbox"]) if isinstance(detection.get("bbox"), list) else detection.get("bbox"),
        }
        if isinstance(detection, dict)
        else detection
        for detection in result.get("detections", [])
    ]
    return copied


def _empty_result(camera_available=False, model_available=False):
    """Return an empty detection result with a fresh detections list."""
    result = _copy_result(_EMPTY_RESULT)
    result["camera_available"] = camera_available
    result["model_available"] = model_available
    return result


class CameraVision:
    """
    Captures camera frames and runs YOLO-based fire/smoke detection.

    Initialises the camera device and loads the YOLO model independently;
    either component may be unavailable without affecting the other or the
    rest of the robot stack.
    """

    def __init__(self):
        """
        Open the camera device and load the YOLO model.

        Failures in either step are caught and logged; the instance remains
        usable so callers can check is_available() before proceeding.
        """
        self.logger = WildfireLogger("CameraVision")
        self._cap = None
        self._model = None
        self._latest_result = _empty_result()
        self._latest_frame = None

        self._camera_lock = threading.Lock()
        self._latest_overlay_frame = None
        self._camera_available = False  # True after VideoCapture is successfully opened
        self._model_available = False    # True after YOLO model is loaded from MODEL_PATH

        if cv2 is None:
            self.logger.log_error("CameraVision.__init__", "opencv-python (cv2) is not installed")
        else:
            try:
                cap = cv2.VideoCapture(CAMERA_DEVICE)
                if cap.isOpened():
                    # Set capture resolution and frame rate to config values
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
                    cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
                    self._cap = cap
                    self._camera_available = True
                else:
                    cap.release()
                    self.logger.log_error("CameraVision.__init__", f"Cannot open camera device: {CAMERA_DEVICE}")
            except Exception as e:
                self.logger.log_error("CameraVision.__init__", f"Camera init error: {e}")

        if YOLO is None:
            self.logger.log_error("CameraVision.__init__", "ultralytics is not installed")
        else:
            try:
                self._model = YOLO(MODEL_PATH)  # Loads weights from MODEL_PATH (e.g. best.pt)
                self._model_available = True
            except Exception as e:
                self.logger.log_error("CameraVision.__init__", f"Model load error ({MODEL_PATH}): {e}")

    def is_available(self) -> bool:
        """Return True only if both camera and model are ready for inference."""
        return self._camera_available and self._model_available

    def is_camera_available(self) -> bool:
        """Return True if the camera device is open and ready to capture frames."""
        return self._camera_available and self._cap is not None

    def get_latest_frame(self):
        """
        Return the most recently captured frame, or None if no frame has been captured.

        Returns:
            numpy ndarray (BGR) or None.
        """
        return self._latest_frame

    def read_frame(self):
        """
        Capture a single frame from the camera.

        Returns:
            numpy ndarray (BGR) on success, None if the camera is unavailable
            or the read fails.
        """
        with self._camera_lock:
            if not self._camera_available or self._cap is None:
                return None
            try:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    return None
                self._latest_frame = frame
                return frame
            except Exception as e:
                self.logger.log_error("CameraVision.read_frame", str(e))
                return None

    def detect(self) -> dict:
        """
        Capture a frame from the camera and run fire/smoke detection.

        Returns:
            Detection result dict. If camera or model is unavailable, or
            frame capture fails, returns the safe empty result.
        """
        frame = self.read_frame()
        if frame is None:
            result = _empty_result(self._camera_available, self._model_available)
            self._latest_result = _copy_result(result)
            return result
        return self.detect_from_frame(frame)

    def detect_from_frame(self, frame) -> dict:
        """
        Run fire/smoke inference on an externally supplied frame.

        Args:
            frame: numpy ndarray (BGR image). Must not be None.

        Returns:
            Detection result dict with the following keys:
            - camera_available (bool)
            - model_available (bool)
            - detected (bool): True if any fire-class object found
            - fire_detected (bool)
            - smoke_detected (bool)
            - confidence (float): highest confidence among detections
            - detections (list[dict]): per-detection details
        """
        result = {
            "camera_available": self._camera_available,
            "model_available": self._model_available,
            "detected": False,
            "fire_detected": False,
            "smoke_detected": False,
            "confidence": 0.0,
            "detections": [],
        }

        if not self._model_available or self._model is None:
            self._latest_result = _copy_result(result)
            return result

        if frame is None:
            self._latest_result = _copy_result(result)
            return result

        try:
            # Run YOLO inference; verbose=False suppresses per-frame console output
            predictions = self._model(frame, verbose=False, conf=CAMERA_CONFIDENCE_THRESHOLD, iou=CAMERA_IOU_THRESHOLD)
        except Exception as e:
            self.logger.log_error("CameraVision.detect_from_frame", f"Inference error: {e}")
            self._latest_result = _copy_result(result)
            return result

        try:
            detections = []
            for pred in predictions:
                boxes = pred.boxes
                if boxes is None:
                    continue
                names = pred.names if pred.names else {}
                for box in boxes:
                    try:
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = names.get(cls_id, str(cls_id)).lower()
                        if conf < CAMERA_CONFIDENCE_THRESHOLD:
                            continue  # Skip low-confidence detections
                        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                        detections.append({
                            "class_id": cls_id,
                            "class_name": cls_name,
                            "confidence": conf,
                            "bbox": [x1, y1, x2, y2],  # Pixel coordinates [left, top, right, bottom]
                        })
                        if cls_name in CAMERA_FIRE_CLASSES:
                            result["detected"] = True
                            if cls_name == "fire":
                                result["fire_detected"] = True
                            if cls_name == "smoke":
                                result["smoke_detected"] = True
                            if conf > result["confidence"]:
                                result["confidence"] = conf  # Track highest confidence among detections
                    except Exception as e:
                        self.logger.log_error("CameraVision.detect_from_frame", f"Box parse error: {e}")

            result["detections"] = detections
        except Exception as e:
            self.logger.log_error("CameraVision.detect_from_frame", f"Result parse error: {e}")

        self._latest_result = _copy_result(result)
        self._latest_overlay_frame = self._draw_overlay(frame, result["detections"])
        return result

    def _draw_overlay(self, frame, detections: list):
        """
        Draw bounding boxes and labels onto a copy of frame.

        Args:
            frame: numpy ndarray (BGR). Must not be None.
            detections: list of detection dicts from detect_from_frame().

        Returns:
            New numpy ndarray with boxes/labels drawn, or the original frame
            if cv2 is unavailable or drawing fails.
        """
        if cv2 is None or frame is None:
            return frame
        try:
            overlay = frame.copy()
            for det in detections:
                try:
                    bbox = det.get("bbox")
                    cls_name = det.get("class_name", "")
                    conf = det.get("confidence", 0.0)
                    if bbox is None or len(bbox) < 4:
                        continue
                    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                    color = _BBOX_COLOR.get(cls_name, _BBOX_COLOR_DEFAULT)
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
                    label = cls_name.capitalize()
                    cv2.putText(overlay, label, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
                except Exception as e:
                    self.logger.log_error("CameraVision._draw_overlay", f"Box draw error: {e}")
            return overlay
        except Exception as e:
            self.logger.log_error("CameraVision._draw_overlay", str(e))
            return frame

    def get_latest_overlay_frame(self):
        """
        Return the most recent frame with bounding box overlay applied.

        Returns the overlay frame produced by the last detect_from_frame() call,
        or None if no detection has been performed yet.

        Returns:
            numpy ndarray (BGR) or None.
        """
        return self._latest_overlay_frame

    def save_evidence_image(self, state_name: str, output_dir: str) -> str | None:
        """
        Save the most recent frame to disk as a JPEG evidence image.

        Prefers the overlay frame (with bounding boxes drawn) when available;
        falls back to the raw captured frame if no overlay exists yet.

        Args:
            state_name: Detection state label used in the filename (e.g. 'suspected_fire').
            output_dir: Directory path where the image will be written.

        Returns:
            Path of the saved image on success, None on failure.
        """
        if cv2 is None:
            self.logger.log_error("CameraVision.save_evidence_image", "cv2 not available")
            return None
        frame = self._latest_overlay_frame if self._latest_overlay_frame is not None else self._latest_frame
        if frame is None:
            self.logger.log_error("CameraVision.save_evidence_image", "no frame available")
            return None
        try:
            import os
            from datetime import datetime
            os.makedirs(output_dir, exist_ok=True)
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"fire_{state_name}_{timestamp_str}.jpg"
            filepath = os.path.join(output_dir, filename)
            success = cv2.imwrite(filepath, frame)
            if not success:
                self.logger.log_error("CameraVision.save_evidence_image", f"cv2.imwrite failed: {filepath}")
                return None
            self.logger.info(f"EVIDENCE | Saved: {filepath}")
            return filepath
        except Exception as e:
            self.logger.log_error("CameraVision.save_evidence_image", str(e))
            return None

    def get_latest_result(self) -> dict:
        """Return the result from the most recent detect() or detect_from_frame() call."""
        return _copy_result(self._latest_result)

    def draw_overlay_on_frame(self, frame):
        """
        Draw the most recent detection results onto an externally supplied frame.

        Uses the detections list from the last detect() or detect_from_frame() call.
        No YOLO inference is performed.

        Args:
            frame: numpy ndarray (BGR). If None, returns None.

        Returns:
            New numpy ndarray with bounding boxes drawn, or None if frame is None.
        """
        if frame is None:
            return None
        return self._draw_overlay(frame, self._latest_result.get("detections", []))

    def release(self):
        """
        Release the camera device.

        Should be called during system shutdown. Safe to call if the camera
        was never successfully opened.
        """
        with self._camera_lock:
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception as e:
                    self.logger.log_error("CameraVision.release", str(e))
                finally:
                    self._cap = None
                    self._camera_available = False
