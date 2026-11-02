import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from vision.person_detection import PersonDetector
from tests.test_frame_capture import FakeCapture, until
from tests.test_person_detection import FakeModel, predictions, box


def load_camera_module(cap, fire_model=None, load_error=False):
    cv2 = SimpleNamespace(VideoCapture=mock.Mock(return_value=cap), CAP_PROP_FRAME_WIDTH=1,
                          CAP_PROP_FRAME_HEIGHT=2, CAP_PROP_FPS=3, FONT_HERSHEY_SIMPLEX=0, LINE_AA=0,
                          rectangle=mock.Mock(), putText=mock.Mock(), imwrite=mock.Mock(return_value=True))
    fire = mock.Mock(return_value=predictions([box()])) if fire_model is None else fire_model
    loader = mock.Mock(side_effect=RuntimeError('fire load failure')) if load_error else mock.Mock(return_value=fire)
    spec = importlib.util.spec_from_file_location('isolated_camera_vision', Path(__file__).parents[1] / 'vision/camera_vision.py')
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {'cv2': cv2, 'ultralytics': SimpleNamespace(YOLO=loader), 'board': None}):
        spec.loader.exec_module(module)
    module.WildfireLogger = mock.Mock()
    return module, cv2, fire


class CameraSharedTests(unittest.TestCase):
    def test_fire_and_video_share_latest_frame_and_fire_result_contract_is_unchanged(self):
        cap = FakeCapture(block_after_first=True)
        fire = mock.Mock(return_value=[SimpleNamespace(boxes=[box()], names={0: 'fire'})])
        module, cv2, _ = load_camera_module(cap, fire_model=fire)
        camera = module.CameraVision()
        try:
            self.assertTrue(cap.blocked.wait(1))
            result = camera.detect()
            self.assertTrue(result['detected']); self.assertTrue(result['fire_detected'])
            self.assertFalse(result['smoke_detected']); self.assertEqual(result['confidence'], 0.9)
            self.assertEqual(set(result), {'camera_available', 'model_available', 'detected', 'fire_detected',
                                          'smoke_detected', 'confidence', 'detections'})
            frame = camera.read_frame(); overlay = camera.draw_overlay_on_frame(frame)
            self.assertIsNot(overlay, frame); self.assertEqual(len(cap.calls), 2)
            self.assertEqual(fire.call_count, 1); cv2.rectangle.assert_called()
            self.assertEqual(cv2.putText.call_args.args[1], 'Fire')
            result['detections'][0]['bbox'][0] = 999
            self.assertEqual(camera.get_latest_result()['detections'][0]['bbox'][0], 1)
            self.assertIsNone(camera.get_frame_snapshot(1))
        finally: cap.gate.set(); camera.release()
        self.assertFalse(camera.is_camera_available()); self.assertEqual(len(cap.releases), 1)

    def test_person_failure_does_not_disable_fire_and_person_is_not_a_fire_event(self):
        cap = FakeCapture()
        fire = mock.Mock(return_value=[SimpleNamespace(boxes=[], names={0: 'fire'})])
        module, _, _ = load_camera_module(cap, fire_model=fire)
        camera = module.CameraVision()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'yolo11n.pt'; path.write_bytes(b'fake only')
            person = PersonDetector(camera, path, model_factory=lambda _: FakeModel(output=predictions([box() for _ in range(12)])))
            broken = PersonDetector(camera, path, model_factory=mock.Mock(side_effect=RuntimeError('load failed')))
            try:
                until(lambda: camera.get_frame_snapshot() is not None)
                person.start(); until(lambda: person.get_latest_result()['person_detected'])
                self.assertEqual(len(person.get_latest_result()['detections']), 12)
                result = camera.detect(); self.assertFalse(result['detected']); self.assertEqual(result['detections'], [])
                from detection.fire_detection import FireDetector
                with mock.patch('detection.fire_detection.WildfireLogger'):
                    detector = FireDetector(SimpleNamespace(read_all=lambda: {'flame': False}),
                                            SimpleNamespace(get_coordinates=lambda: None), None, camera_vision=camera)
                    state, alert, report = detector.evaluate()
                self.assertEqual(state.value, 'normal'); self.assertIsNone(alert); self.assertIsNone(report)
                broken.start(); until(lambda: broken.get_latest_result()['state'] == 'ERROR')
                fire.return_value = [SimpleNamespace(boxes=[box()], names={0: 'fire'})]
                self.assertTrue(camera.detect()['fire_detected']); self.assertTrue(camera.is_available())
            finally: person.close(); broken.close(); camera.release()

    def test_fire_model_failure_keeps_camera_and_independent_person_model_usable(self):
        cap = FakeCapture(); module, _, _ = load_camera_module(cap, load_error=True)
        camera = module.CameraVision()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'yolo11n.pt'; path.write_bytes(b'fake only')
            detector = PersonDetector(camera, path, model_factory=lambda _: FakeModel())
            try:
                until(lambda: camera.get_frame_snapshot() is not None)
                self.assertTrue(camera.is_camera_available()); self.assertFalse(camera.is_available())
                detector.start(); until(lambda: detector.get_latest_result()['person_detected'])
                self.assertFalse(camera.detect()['detected'])
            finally: detector.close(); camera.release()

    def test_camera_open_config_and_thread_errors_release_without_loading_real_hardware(self):
        cap = FakeCapture(); module, cv2, _ = load_camera_module(cap)
        cv2.VideoCapture.return_value.isOpened = lambda: False
        camera = module.CameraVision(); camera.release()
        self.assertEqual(len(cap.releases), 1); self.assertFalse(camera.is_camera_available())
        cap = FakeCapture(); module, cv2, _ = load_camera_module(cap)
        cap.set = mock.Mock(side_effect=OSError('config failed'))
        camera = module.CameraVision(); camera.release(); self.assertEqual(len(cap.releases), 1)
        cap = FakeCapture(); module, cv2, _ = load_camera_module(cap)
        with mock.patch('vision.frame_capture.threading.Thread', side_effect=RuntimeError('no thread')):
            camera = module.CameraVision()
        with self.assertRaises(RuntimeError): camera.release()
        self.assertEqual(len(cap.releases), 1)


    def test_unopened_camera_release_error_is_not_retried(self):
        cap = FakeCapture(release_error=True); cap.isOpened = lambda: False
        module, _, _ = load_camera_module(cap)
        camera = module.CameraVision(); camera.release()
        self.assertEqual(len(cap.releases), 1); self.assertFalse(camera.is_camera_available())


    def test_interrupted_model_initialization_stops_capture_before_propagating(self):
        cap = FakeCapture(); module, _, _ = load_camera_module(cap)
        from vision.frame_capture import SharedFrameCapture
        created = []
        def create(*args, **kwargs):
            capture = SharedFrameCapture(*args, **kwargs); created.append(capture); return capture
        module.SharedFrameCapture = create
        module.YOLO = mock.Mock(side_effect=KeyboardInterrupt)
        with self.assertRaises(KeyboardInterrupt): module.CameraVision()
        self.assertFalse(created[0]._thread.is_alive()); self.assertEqual(len(cap.releases), 1)
        self.assertEqual(created[0].get_status()['state'], 'STOPPED')


    def test_actual_mjpeg_generator_uses_shared_frames_without_own_native_reads_or_inference(self):
        import numpy as np
        from robot import robot_api
        cap = FakeCapture(block_after_first=True)
        fire = mock.Mock(return_value=[SimpleNamespace(boxes=[box()], names={0: 'fire'})])
        module, cv2, _ = load_camera_module(cap, fire_model=fire)
        cv2.imencode = mock.Mock(return_value=(True, np.array([1, 2, 3], dtype=np.uint8)))
        camera = module.CameraVision()
        async def check_stream():
            response = await robot_api.get_camera_stream()
            try:
                for _ in range(2):
                    payload = await response.body_iterator.__anext__()
                    self.assertTrue(payload.startswith(b'--frame\r\nContent-Type: image/jpeg'))
                    self.assertIn(bytes([1, 2, 3]), payload)
            finally: await response.body_iterator.aclose()
        try:
            self.assertTrue(cap.blocked.wait(1)); camera.detect()
            with mock.patch.object(robot_api, '_camera_vision', camera), mock.patch.dict(sys.modules, {'cv2': cv2}):
                asyncio.run(check_stream())
            self.assertEqual(fire.call_count, 1); self.assertEqual(len(cap.calls), 2)
            self.assertEqual(cv2.imencode.call_count, 2); self.assertTrue(camera.is_camera_available())
        finally: cap.gate.set(); camera.release()
        with mock.patch.object(robot_api, '_camera_vision', camera), mock.patch.dict(sys.modules, {'cv2': cv2}):
            response = asyncio.run(robot_api.get_camera_stream())
        self.assertEqual(response.status_code, 503)


    def test_mjpeg_waits_through_stale_capture_and_resumes_then_stops_on_shutdown(self):
        import numpy as np
        from robot import robot_api
        cap = FakeCapture(block_after_first=True)
        module, cv2, _ = load_camera_module(cap)
        cv2.imencode = mock.Mock(return_value=(True, np.array([1], dtype=np.uint8)))
        camera = module.CameraVision()
        async def check_stream():
            response = await robot_api.get_camera_stream()
            iterator = response.body_iterator
            try:
                await iterator.__anext__()
                pending = asyncio.create_task(iterator.__anext__())
                await asyncio.sleep(1.7)
                if pending.done():
                    await pending
                    pending = asyncio.create_task(iterator.__anext__())
                    await asyncio.sleep(1.7)
                self.assertFalse(pending.done())
                self.assertTrue(camera.is_camera_available())
                cap.gate.set()
                self.assertTrue((await asyncio.wait_for(pending, 1)).startswith(b'--frame'))
                camera.release()
                with self.assertRaises(StopAsyncIteration): await iterator.__anext__()
            finally:
                if 'pending' in locals() and not pending.done():
                    pending.cancel()
                    try: await pending
                    except asyncio.CancelledError: pass
                await iterator.aclose()
        try:
            self.assertTrue(cap.blocked.wait(1))
            with mock.patch.object(robot_api, '_camera_vision', camera), mock.patch.dict(sys.modules, {'cv2': cv2}):
                asyncio.run(check_stream())
        finally: cap.gate.set(); camera.release()

    def test_release_failure_is_recorded_in_project_logger_before_propagating(self):
        cap = FakeCapture(release_error=True)
        module, _, _ = load_camera_module(cap)
        camera = module.CameraVision()
        with self.assertRaises(RuntimeError): camera.release()
        camera.logger.log_error.assert_called_with('CameraVision.release', 'Camera release failed: OSError')
