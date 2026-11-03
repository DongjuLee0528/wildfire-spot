import ast
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
from tests.test_camera_vision_shared import load_camera_module
from tests.test_frame_capture import FakeCapture, until
from tests.test_person_detection import FakeModel, Source, VirtualStop, ClockSource, box, predictions
from vision.person_detection import PersonDetector

ROOT = Path(__file__).resolve().parents[1]


def main_functions(*names):
    tree = ast.parse((ROOT / 'main.py').read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    scope = {'WildfireLogger': mock.Mock()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<main functions, fake dependencies only>', 'exec'), scope)
    return scope


class PersonStartupTests(unittest.TestCase):
    def setUp(self):
        self.scope = main_functions('_start_person_detection')
        self.logger, self.camera, self.detector = mock.Mock(), mock.Mock(), mock.Mock()
        self.settings = SimpleNamespace(PERSON_DETECTION_ENABLED=True, PERSON_MODEL_PATH='/unused/yolo11n.pt',
                                        PERSON_DETECTION_FPS=10, PERSON_CONFIDENCE_THRESHOLD=0.5)
        self.factory = mock.Mock(return_value=self.detector)
        self.modules = {'utils.config': self.settings, 'vision.person_detection': SimpleNamespace(PersonDetector=self.factory)}

    def start(self, camera=True):
        with mock.patch.dict(sys.modules, self.modules):
            return self.scope['_start_person_detection'](self.logger, self.camera if camera else None)

    def test_enabled_attaches_and_starts_with_config(self):
        self.assertIs(self.start(), self.detector)
        self.factory.assert_called_once_with(self.camera, '/unused/yolo11n.pt', fps=10, confidence=0.5)
        self.camera.set_person_detector.assert_called_once_with(self.detector)
        self.detector.start.assert_called_once(); self.detector.close.assert_not_called()
        self.scope['WildfireLogger'].assert_called_once_with('vision.person_detection')
        self.logger.log_system_state.assert_called_with('PERSON_DETECTION_START_REQUESTED fps=10')

    def test_disabled_and_unavailable_camera_do_not_create_worker(self):
        self.settings.PERSON_DETECTION_ENABLED = False
        self.assertIsNone(self.start()); self.factory.assert_not_called()
        self.settings.PERSON_DETECTION_ENABLED = True
        self.assertIsNone(self.start(camera=False)); self.factory.assert_not_called()
        self.camera.is_camera_available.return_value = False
        self.assertIsNone(self.start()); self.factory.assert_not_called()

    def test_constructor_start_and_partial_cleanup_errors_do_not_release_camera(self):
        self.factory.side_effect = ValueError('invalid settings')
        self.assertIsNone(self.start()); self.camera.release.assert_not_called()
        self.factory.side_effect = None
        self.detector.start.side_effect = RuntimeError('start failure')
        self.detector.close.side_effect = RuntimeError('close failure')
        self.assertIsNone(self.start()); self.detector.close.assert_called_once()
        self.camera.set_person_detector.assert_called_with(None)
        self.logger.log_error.assert_any_call('Main.person_detection_cleanup', 'RuntimeError')
        self.camera.release.assert_not_called()

    def test_start_interrupt_cleans_partial_worker_and_propagates(self):
        self.detector.start.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt): self.start()
        self.detector.close.assert_called_once(); self.camera.set_person_detector.assert_called_with(None)

    def test_missing_local_model_errors_asynchronously_without_disabling_fire(self):
        with tempfile.TemporaryDirectory() as directory:
            self.settings.PERSON_MODEL_PATH = str(Path(directory) / 'absent.pt')
            self.modules['vision.person_detection'] = SimpleNamespace(PersonDetector=PersonDetector)
            detector = self.start()
            try:
                until(lambda: detector.get_latest_result()['state'] == 'ERROR')
                self.assertEqual(detector.get_latest_result()['detections'], [])
                self.camera.release.assert_not_called()
            finally: detector.close()


class PersonOverlayTests(unittest.TestCase):
    def test_people_confidence_and_fire_boxes_coexist_without_merging_fire_results(self):
        cap = FakeCapture(); module, cv2, fire = load_camera_module(cap)
        camera = module.CameraVision()
        source, clock = Source(), [10.0]; source.stamp = 10
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'yolo11n.pt'; path.write_bytes(b'fake only')
            model = FakeModel(output=predictions([box(confidence=0.92) for _ in range(12)]))
            detector = PersonDetector(source, path, model_factory=lambda _: model, clock=lambda: clock[0])
            camera.set_person_detector(detector); detector.start()
            try:
                until(lambda: detector.get_latest_result()['inferences'] == 1)
                fire.return_value = [SimpleNamespace(boxes=[box()], names={0: 'fire'})]
                frame = np.ones((32, 48, 3), dtype=np.uint8)
                result = camera.detect_from_frame(frame)
                self.assertEqual([call.args[1] for call in cv2.putText.call_args_list], ['Fire'])
                evidence = camera.get_latest_overlay_frame()
                evidence_path = camera.save_evidence_image('verified_fire', directory)
                self.assertIsNotNone(evidence_path)
                self.assertIs(cv2.imwrite.call_args.args[1], evidence)
                self.assertEqual([call.args[1] for call in cv2.putText.call_args_list], ['Fire'])
                cv2.putText.reset_mock(); cv2.rectangle.reset_mock()
                overlay = camera.draw_overlay_on_frame(frame)
                self.assertEqual([call.args[1] for call in cv2.putText.call_args_list], ['Fire'] + ['Person 92%'] * 12)
                self.assertEqual(cv2.rectangle.call_args_list[-1].args[3], (0, 255, 255))
                self.assertIsNot(overlay, frame); self.assertTrue(np.all(frame == 1))
                self.assertEqual(camera.get_latest_result(), result)
                self.assertEqual(len(result['detections']), 1); self.assertTrue(result['fire_detected'])
                clock[0] = 10.5; cv2.putText.reset_mock(); camera.draw_overlay_on_frame(frame)
                self.assertEqual([call.args[1] for call in cv2.putText.call_args_list], ['Fire'])
                self.assertEqual(len(model.calls), 1)
                detector.close(); cv2.putText.reset_mock(); camera.draw_overlay_on_frame(frame)
                self.assertEqual([call.args[1] for call in cv2.putText.call_args_list], ['Fire'])
            finally: detector.close(); camera.release()

    def test_person_labels_at_top_right_stay_visible_in_real_synthetic_image(self):
        import cv2 as real_cv2
        cap = FakeCapture(); module, _, _ = load_camera_module(cap)
        camera = module.CameraVision()
        try:
            module.cv2 = real_cv2
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            person = {'class_name': 'person', 'confidence': 0.91, 'bbox': [600, 0, 639, 400]}
            original_put = real_cv2.putText
            with mock.patch.object(real_cv2, 'putText', wraps=original_put) as put_text:
                overlay = camera._draw_overlay(frame, [person])
            label, (x, y) = put_text.call_args.args[1:3]
            (width, height), baseline = real_cv2.getTextSize(label, real_cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            self.assertGreaterEqual(x, 0); self.assertLess(x + width, 640)
            self.assertGreaterEqual(y - height, 0); self.assertLess(y + baseline, 480)
            blank = frame.copy()
            real_cv2.putText(blank, label, (x, y), real_cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, real_cv2.LINE_AA)
            self.assertGreater(np.count_nonzero(blank), 100)
            self.assertGreater(np.count_nonzero(overlay), np.count_nonzero(blank))
            self.assertFalse(np.any(frame))
        finally: camera.release()

    def test_slow_expired_results_warn_at_most_once_every_five_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'yolo11n.pt'; path.write_bytes(b'fake only')
            clock, warnings = [0.0], []
            def slow(): clock[0] += 0.55
            detector = PersonDetector(ClockSource(clock), path,
                                      model_factory=lambda _: FakeModel(action=slow), clock=lambda: clock[0])
            detector._stop = VirtualStop(clock, 12)
            with mock.patch('vision.person_detection.logger.warning', side_effect=lambda *args: warnings.append((clock[0], args))):
                detector._run()
            self.assertEqual(len(warnings), 3)
            self.assertIn('expired before publication', warnings[0][1][0])
            for (before, _), (after, _) in zip(warnings, warnings[1:]): self.assertGreaterEqual(after - before, 5)
            self.assertEqual(detector.get_latest_result()['detections'], [])
            self.assertGreater(detector.get_latest_result()['inferences'], 15)

    def test_request_stop_returns_without_waiting_for_blocked_inference(self):
        entered, gate = threading.Event(), threading.Event()
        def blocked():
            entered.set()
            gate.wait(3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'yolo11n.pt'; path.write_bytes(b'fake only')
            detector = PersonDetector(Source(), path, model_factory=lambda _: FakeModel(action=blocked))
            detector.start()
            try:
                self.assertTrue(entered.wait(1))
                started = time.monotonic(); detector.request_stop()
                self.assertLess(time.monotonic() - started, 0.2)
                self.assertTrue(detector._thread.is_alive())
                self.assertEqual(detector.get_latest_result()['detections'], [])
                gate.set(); detector.close()
                self.assertEqual(detector.get_latest_result()['state'], 'STOPPED')
            finally: gate.set(); detector.close()

    def test_failed_person_getter_keeps_fire_overlay_and_logs_failure(self):
        cap = FakeCapture(); module, cv2, _ = load_camera_module(cap)
        camera = module.CameraVision()
        try:
            camera._latest_result['detections'] = [{'class_name': 'smoke', 'confidence': 0.8, 'bbox': [1, 1, 4, 4]}]
            broken = mock.Mock(); broken.get_latest_result.side_effect = RuntimeError('fake result failure')
            camera.set_person_detector(broken)
            self.assertIsNotNone(camera.draw_overlay_on_frame(np.ones((32, 48, 3))))
            self.assertEqual(cv2.putText.call_args.args[1], 'Smoke')
            camera.logger.log_error.assert_called_with('CameraVision.person_overlay', 'RuntimeError')
            camera.set_person_detector(None)
            self.assertIsNone(camera.draw_overlay_on_frame(None))
        finally: camera.release()

    def test_actual_mjpeg_composes_person_boxes_without_extra_inference(self):
        from robot import robot_api
        cap = FakeCapture(); module, cv2, fire = load_camera_module(cap)
        cv2.imencode = mock.Mock(return_value=(True, np.array([7], dtype=np.uint8)))
        camera = module.CameraVision(); person = mock.Mock()
        person.get_latest_result.return_value = {'detections': [{'class_name': 'person', 'confidence': 0.87, 'bbox': [1, 1, 8, 9]}]}
        camera.set_person_detector(person)
        async def stream():
            response = await robot_api.get_camera_stream()
            try: self.assertIn(b'Content-Type: image/jpeg', await response.body_iterator.__anext__())
            finally: await response.body_iterator.aclose()
        try:
            until(lambda: camera.get_frame_snapshot() is not None)
            with mock.patch.object(robot_api, '_camera_vision', camera), mock.patch.dict(sys.modules, {'cv2': cv2}):
                asyncio.run(stream())
            self.assertEqual(cv2.putText.call_args.args[1], 'Person 87%')
            fire.assert_not_called(); person.start.assert_not_called()
        finally: camera.release()


class MainPersonLifecycleTests(unittest.TestCase):
    def environment(self):
        scope = main_functions('main')
        camera, detector, runtime, logger = mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock()
        runtime.point_cloud_manager = None
        keys = mock.Mock(); keys.get_key.return_value = 'q'
        scope.update(WildfireLogger=mock.Mock(return_value=logger), PatrolZoneCalibrator=mock.Mock(),
                     KeyboardInput=mock.Mock(return_value=keys), CameraControlManager=mock.Mock(),
                     _init_servo_hardware=mock.Mock(return_value=None), _start_keyboard_controller=mock.Mock(return_value=None),
                     _start_person_detection=mock.Mock(return_value=detector), _start_robot_api_server=mock.Mock(),
                     _start_fire_detection_loop=mock.Mock(return_value=(mock.Mock(), mock.Mock())),
                     SPRING_TELEMETRY_ENABLED=False, FIRE_DETECTION_INTERVAL_SECONDS=1, robot_api=mock.Mock())
        modules = {'robot.robot_runtime_context': SimpleNamespace(RobotRuntimeContext=lambda: runtime),
                   'vision.camera_vision': SimpleNamespace(CameraVision=lambda: camera),
                   'robot.robot_core_data_collector': SimpleNamespace(RobotCoreDataCollector=mock.Mock()),
                   'robot.manual_control_manager': SimpleNamespace(ManualControlManager=mock.Mock()),
                   'robot.mode_control_manager': SimpleNamespace(ModeControlManager=mock.Mock()),
                   'navigation.patrol_zone_manager': SimpleNamespace(PatrolZoneManager=mock.Mock())}
        return scope, modules, camera, detector, runtime, logger

    def test_real_main_starts_person_and_closes_before_camera(self):
        scope, modules, camera, detector, runtime, logger = self.environment()
        order = []
        detector.request_stop.side_effect = lambda: order.append('person-stop')
        scope['CameraControlManager'].return_value.close.side_effect = lambda: order.append('hardware')
        detector.close.side_effect = lambda: order.append('person')
        camera.release.side_effect = lambda: order.append('camera')
        with mock.patch.dict(sys.modules, modules), mock.patch('builtins.print'): scope['main']()
        scope['_start_person_detection'].assert_called_once_with(logger, camera)
        scope['robot_api'].configure.assert_called_once(); self.assertIs(runtime.fire_detector.camera_vision, camera)
        self.assertEqual(order, ['person-stop', 'hardware', 'person', 'camera']); detector.close.assert_called_once()

    def test_person_shutdown_error_does_not_skip_camera_or_runtime_cleanup(self):
        scope, modules, camera, detector, runtime, logger = self.environment()
        detector.close.side_effect = RuntimeError('blocked inference')
        with mock.patch.dict(sys.modules, modules), mock.patch('builtins.print'): scope['main']()
        logger.log_error.assert_any_call('Main.person_detection_shutdown', 'RuntimeError')
        camera.release.assert_called_once(); runtime.close.assert_called_once(); logger.close.assert_called_once()

    def test_person_stops_despite_later_initialization_or_unrelated_cleanup_error(self):
        for failure in ('initialization', 'cleanup'):
            with self.subTest(failure=failure):
                scope, modules, _, detector, _, logger = self.environment()
                if failure == 'initialization': scope['robot_api'].configure.side_effect = RuntimeError('API init failure')
                else: scope['CameraControlManager'].return_value.close.side_effect = RuntimeError('camera control cleanup failure')
                with mock.patch.dict(sys.modules, modules), mock.patch('builtins.print'):
                    if failure == 'cleanup':
                        with self.assertRaises(RuntimeError): scope['main']()
                    else: scope['main']()
                detector.close.assert_called_once(); logger.close.assert_called_once()


class PersonConfigTests(unittest.TestCase):
    def load(self, **settings):
        spec = importlib.util.spec_from_file_location('isolated_person_config', ROOT / 'utils/config.py')
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, settings, clear=True), mock.patch.dict(sys.modules, {'board': None}):
            spec.loader.exec_module(module)
        return module

    def test_default_off_and_portable_model_location(self):
        config = self.load()
        self.assertFalse(config.PERSON_DETECTION_ENABLED)
        self.assertEqual(Path(config.PERSON_MODEL_PATH), ROOT / 'models/person/yolo11n.pt')
        self.assertEqual(config.PERSON_DETECTION_FPS, 10); self.assertEqual(config.PERSON_CONFIDENCE_THRESHOLD, 0.5)

    def test_custom_settings_and_finite_bounded_timing(self):
        config = self.load(PERSON_DETECTION_ENABLED='true', PERSON_MODEL_PATH='/tmp/fake-person.pt',
                           PERSON_DETECTION_FPS='6', PERSON_CONFIDENCE_THRESHOLD='0.7')
        self.assertTrue(config.PERSON_DETECTION_ENABLED); self.assertEqual(config.PERSON_MODEL_PATH, '/tmp/fake-person.pt')
        self.assertEqual(config.PERSON_DETECTION_FPS, 6); self.assertEqual(config.PERSON_CONFIDENCE_THRESHOLD, 0.7)
        for fps, confidence in [('nan', 'inf'), ('bad', 'bad'), ('100', '2'), ('0', '-1')]:
            config = self.load(PERSON_DETECTION_FPS=fps, PERSON_CONFIDENCE_THRESHOLD=confidence)
            self.assertGreater(config.PERSON_DETECTION_FPS, 0); self.assertLessEqual(config.PERSON_DETECTION_FPS, 10)
            self.assertGreater(config.PERSON_CONFIDENCE_THRESHOLD, 0); self.assertLessEqual(config.PERSON_CONFIDENCE_THRESHOLD, 1)
