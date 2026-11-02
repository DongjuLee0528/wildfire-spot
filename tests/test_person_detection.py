import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
from vision.frame_capture import FrameSnapshot
from vision.person_detection import PersonDetector, MAX_PERSON_DETECTIONS
from tests.test_frame_capture import until


def box(category=0, confidence=0.9, bounds=(1, 1, 10, 10)):
    return SimpleNamespace(cls=[category], conf=[confidence], xyxy=[list(bounds)])


def predictions(boxes=None):
    return [SimpleNamespace(boxes=[box()] if boxes is None else boxes)]


class Source:
    def __init__(self):
        self.sequence = 1
        self.frame = np.zeros((32, 48, 3), dtype=np.uint8)
        self.stamp = time.monotonic()
        self.available = True
    def get_frame_snapshot(self, after_sequence=None):
        if not self.available or self.sequence == after_sequence: return None
        return FrameSnapshot(self.sequence, self.stamp, self.frame.copy())


class FakeModel:
    names = {0: 'person', 1: 'bicycle'}
    task = 'detect'
    def __init__(self, output=None, action=None):
        self.output = predictions() if output is None else output
        self.action = action
        self.calls = []
    def predict(self, frame, **kwargs):
        self.calls.append((threading.get_ident(), kwargs))
        if self.action: self.action()
        return self.output


class VirtualStop:
    def __init__(self, clock, end): self.clock, self.end, self.stopped = clock, end, False
    def is_set(self): return self.stopped or self.clock[0] >= self.end
    def set(self): self.stopped = True
    def clear(self): self.stopped = False
    def wait(self, delay):
        self.clock[0] = min(self.end, self.clock[0] + max(0, delay))
        return self.is_set()


class ClockSource:
    def __init__(self, clock): self.clock = clock
    def get_frame_snapshot(self, after_sequence=None):
        sequence = int((self.clock[0] + 1e-9) / 0.01) + 1
        if sequence == after_sequence: return None
        return FrameSnapshot(sequence, min(self.clock[0], (sequence - 1) * 0.01), np.zeros((32, 48, 3), dtype=np.uint8))


class PersonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'yolo11n.pt'; self.path.write_bytes(b'fake model, never loaded')
    def detector(self, source=None, model=None, **kwargs):
        model = model or FakeModel()
        return PersonDetector(source or Source(), self.path, model_factory=lambda _: model, **kwargs)

    def test_multiple_people_filtered_without_fire_result_fields_and_defensive_copy(self):
        model = FakeModel(output=predictions([box() for _ in range(12)] + [box(1), box(confidence=0.1)]))
        detector = self.detector(model=model); detector.start()
        try:
            until(lambda: detector.get_latest_result()['inferences'] == 1)
            result = detector.get_latest_result()
            self.assertTrue(result['person_detected']); self.assertEqual(len(result['detections']), 12)
            self.assertNotIn('detected', result); self.assertNotIn('fire_detected', result)
            result['detections'][0]['bbox'][0] = 999
            self.assertEqual(detector.get_latest_result()['detections'][0]['bbox'][0], 1)
            self.assertEqual(model.calls[0][1]['classes'], [0])
            self.assertEqual(model.calls[0][1]['max_det'], MAX_PERSON_DETECTIONS)
            self.assertFalse(model.calls[0][1]['save']); self.assertFalse(model.calls[0][1]['show'])
            time.sleep(0.15); self.assertEqual(len(model.calls), 1)
        finally: detector.close()
        self.assertEqual(detector.get_latest_result()['state'], 'STOPPED')
        self.assertEqual(detector.get_latest_result()['detections'], [])

    def test_ten_hz_start_cadence_uses_latest_and_slow_work_does_not_queue(self):
        for latency, expected_interval in [(0.013, 0.1), (0.18, 0.18)]:
            with self.subTest(latency=latency):
                clock, calls = [0.0], []
                source = ClockSource(clock)
                original = source.get_frame_snapshot
                def snapshot(after=None):
                    value = original(after)
                    if value is not None: calls.append((clock[0], value.sequence))
                    return value
                source.get_frame_snapshot = snapshot
                def predict(): clock[0] += latency
                model = FakeModel(action=predict)
                detector = self.detector(source=source, model=model, clock=lambda: clock[0])
                detector._stop = VirtualStop(clock, 3)
                detector._run()
                self.assertGreater(len(calls), 10)
                for (a, _), (b, _) in zip(calls, calls[1:]): self.assertAlmostEqual(b - a, expected_interval)
                for at, sequence in calls: self.assertEqual(sequence, int((at + 1e-9) / 0.01) + 1)
                self.assertEqual(len(calls), len(model.calls))

    def test_no_frame_does_not_infer_and_old_results_expire_from_receipt_time(self):
        source = Source(); clock = [10.0]; source.stamp = clock[0]
        detector = self.detector(source=source, clock=lambda: clock[0]); detector.start()
        try:
            until(lambda: detector.get_latest_result()['inferences'] == 1)
            source.available = False; clock[0] = 10.5
            result = detector.get_latest_result()
            self.assertFalse(result['person_detected']); self.assertEqual(result['state'], 'STALE')
            self.assertEqual(result['detections'], [])
        finally: detector.close()
        source.available = False; model = FakeModel(); detector = self.detector(source=source, model=model)
        detector.start(); until(lambda: detector.get_latest_result()['model_available']); detector.close()
        self.assertEqual(model.calls, [])

    def test_delayed_inference_drops_expired_result(self):
        entered, gate = threading.Event(), threading.Event()
        clock = [10.0]; source = Source(); source.stamp = 10
        def action(): entered.set(); gate.wait(2)
        detector = self.detector(source=source, model=FakeModel(action=action), clock=lambda: clock[0]); detector.start()
        try:
            self.assertTrue(entered.wait(1)); clock[0] = 11; gate.set()
            until(lambda: detector.get_latest_result()['inferences'] == 1)
            self.assertEqual(detector.get_latest_result()['detections'], [])
            self.assertEqual(detector.get_latest_result()['state'], 'STALE')
        finally: gate.set(); detector.close()

    def test_missing_local_file_cannot_call_loader_or_download(self):
        factory = mock.Mock()
        detector = PersonDetector(Source(), self.path.parent / 'absent.pt', model_factory=factory)
        detector.start(); until(lambda: detector.get_latest_result()['state'] == 'ERROR')
        detector.close(); factory.assert_not_called()
        self.assertIn('Local person model', detector.get_latest_result()['error'])

    def test_load_schema_inference_and_output_failures_clear_only_person_results(self):
        cases = [FakeModel(output=predictions([box(bounds=(0, 0, float('nan'), 5))])),
                 FakeModel(output=predictions([box(confidence=float('inf'))])),
                 FakeModel(output=predictions([box() for _ in range(101)])),
                 FakeModel(output=[])]
        wrong = FakeModel(); wrong.names = {0: 'fire'}; cases.append(wrong)
        def fail(): raise RuntimeError('fake inference failure')
        cases.append(FakeModel(action=fail))
        for model in cases:
            with self.subTest(model=model):
                source = Source(); detector = self.detector(source=source, model=model)
                detector.start(); until(lambda: detector.get_latest_result()['state'] == 'ERROR')
                self.assertEqual(detector.get_latest_result()['detections'], [])
                self.assertTrue(source.available); detector.close()
        detector = PersonDetector(Source(), self.path, model_factory=mock.Mock(side_effect=RuntimeError('load failed')))
        detector.start(); until(lambda: detector.get_latest_result()['state'] == 'ERROR'); detector.close()

    def test_stop_during_inference_never_publishes_late_result_and_timeout_is_visible(self):
        entered, gate = threading.Event(), threading.Event()
        def action(): entered.set(); gate.wait(3)
        detector = self.detector(model=FakeModel(action=action)); detector.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(RuntimeError, 'did not stop'): detector.close(timeout=0.01)
            self.assertEqual(detector.get_latest_result()['detections'], [])
            with self.assertRaises(RuntimeError): detector.start()
        finally: gate.set(); detector._thread.join(2)
        self.assertEqual(detector.get_latest_result()['state'], 'ERROR')
        with self.assertRaises(RuntimeError): detector.close()

    def test_duplicate_start_and_thread_failure_and_settings(self):
        detector = self.detector(); detector.start(); detector.start(); detector.close()
        detector = self.detector()
        with mock.patch('vision.person_detection.threading.Thread', side_effect=RuntimeError('no thread')):
            detector.start()
        self.assertEqual(detector.get_latest_result()['state'], 'ERROR'); detector.close()
        for kwargs in ({'fps': 11}, {'fps': 0}, {'max_age': 0}, {'confidence': 2}, {'fps': float('nan')}):
            with self.assertRaises(ValueError): self.detector(**kwargs)


    def test_stop_during_result_parsing_cannot_publish_or_hide_shutdown_failure(self):
        entered, gate = threading.Event(), threading.Event()
        detector = self.detector()
        original = detector._parse
        def slow_parse(predictions, frame):
            entered.set(); gate.wait(3)
            return original(predictions, frame)
        detector._parse = slow_parse; detector.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(RuntimeError): detector.close(timeout=0.01)
        finally: gate.set(); detector._thread.join(2)
        result = detector.get_latest_result()
        self.assertEqual(result['state'], 'ERROR'); self.assertEqual(result['inferences'], 0)
        self.assertEqual(result['detections'], [])
        with self.assertRaises(RuntimeError): detector.close()


    def test_finite_boxes_are_clipped_and_zero_area_boxes_do_not_stop_valid_people(self):
        model = FakeModel(output=predictions([box(bounds=(-1, 0, 4, 5)), box(bounds=(4, 4, 4, 9)),
                                             box(bounds=(100, 10, 120, 20))] + [box() for _ in range(12)]))
        detector = self.detector(model=model); detector.start()
        try:
            until(lambda: detector.get_latest_result()['inferences'] == 1)
            result = detector.get_latest_result()
            self.assertEqual(result['state'], 'STREAMING'); self.assertEqual(len(result['detections']), 13)
            self.assertEqual(result['detections'][0]['bbox'], [0, 0, 4, 5])
        finally: detector.close()

    def test_interrupted_start_never_loads_model_later(self):
        factory = mock.Mock(); detector = PersonDetector(Source(), self.path, model_factory=factory)
        with mock.patch('vision.person_detection.threading.Thread.start', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): detector.start()
        detector.close(); factory.assert_not_called()
        self.assertEqual(detector.get_latest_result()['state'], 'STOPPED')


    def test_interruption_after_person_thread_spawn_leaves_no_worker_or_result(self):
        detector = self.detector(); start = threading.Thread.start
        def interrupted(thread):
            start(thread)
            raise KeyboardInterrupt
        with mock.patch('vision.person_detection.threading.Thread.start', new=interrupted):
            with self.assertRaises(KeyboardInterrupt): detector.start()
        self.assertFalse(detector._thread.is_alive()); detector.close()
        self.assertEqual(detector.get_latest_result()['state'], 'STOPPED')
        self.assertEqual(detector.get_latest_result()['detections'], [])
