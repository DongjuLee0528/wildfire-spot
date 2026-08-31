import json
import math
import os
import tempfile
import time
import unittest
from unittest import mock

import numpy as np

from Kinematics.kinematics import DHParameterSolver, IKError
from hardware.servo_controller import QuadrupedServoManager
from kinematicMotion import QuadrupedGaitPattern
from utils.gait_diagnostics import GaitDiagnosticLogger


class FakeServo:
    def __init__(self):
        self.writes = []

    @property
    def angle(self):
        return self.writes[-1] if self.writes else None

    @angle.setter
    def angle(self, value):
        self.writes.append(value)


def fake_servo_manager():
    manager = object.__new__(QuadrupedServoManager)
    manager._servo_array = [FakeServo() for _ in range(12)]
    manager._offset_values = [180, 90, 90, 1, 90, 90, 180, 90, 90, 1, 90, 90]
    manager._angle_array = list(range(12))
    manager._joint_angles = []
    return manager


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


class GaitDiagnosticsTest(unittest.TestCase):
    def test_disabled_does_not_create_file_or_change_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "diag.jsonl")
            logger = GaitDiagnosticLogger(enabled=False, path=path)

            logger.snapshot({"value": 1})
            logger.anomaly({"anomaly_type": "test"})

            self.assertFalse(os.path.exists(path))

        gait = QuadrupedGaitPattern()
        plain_positions = gait.calculate_leg_positions(123.456, {})
        diag_positions, _ = gait.calculate_leg_positions(123.456, {}, include_diagnostics=True)
        self.assertTrue(np.allclose(plain_positions, diag_positions))

        solver = DHParameterSolver()
        plain_angles = solver.calculate_inverse_kinematics_single_leg([100, -100, 100, 1])
        details = {}
        diag_angles = solver.calculate_inverse_kinematics_single_leg([100, -100, 100, 1], details)
        self.assertTrue(np.allclose(plain_angles, diag_angles))

        angles = np.zeros((4, 3), dtype=np.float64)
        plain_manager = fake_servo_manager()
        diag_manager = fake_servo_manager()
        plain_manager.execute_servo_motion(angles)
        servo_details = {}
        diag_manager.execute_servo_motion(angles, diagnostics=servo_details)
        self.assertEqual(plain_manager.get_current_angles(), diag_manager.get_current_angles())

    def test_snapshot_sampling_is_rate_limited_and_single_record_has_four_legs(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(time, "sleep", side_effect=AssertionError):
            path = os.path.join(temp_dir, "diag.jsonl")
            logger = GaitDiagnosticLogger(enabled=True, path=path, rate_hz=5.0)
            record = {"monotonic_time": 1.0, "legs": [{"leg": leg} for leg in ("FL", "FR", "BL", "BR")]}

            logger.snapshot(record, now=0.0)
            logger.snapshot(record, now=0.1)
            logger.snapshot(record, now=0.2)

            lines = read_jsonl(path)
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0]["event_type"], "snapshot")
            self.assertEqual([leg["leg"] for leg in lines[0]["legs"]], ["FL", "FR", "BL", "BR"])

    def test_ikerror_anomaly_is_immediate_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "diag.jsonl")
            logger = GaitDiagnosticLogger(enabled=True, path=path, rate_hz=0.1)
            logger.snapshot({"legs": []}, now=0.0)

            solver = DHParameterSolver()
            diagnostics = {}
            with self.assertRaises(IKError):
                solver.solve_complete_inverse_kinematics(
                    np.array([
                        [120.0, -100.0, 80.0, 1.0],
                        [120.0, -100.0, -80.0, 1.0],
                        [500.0, -100.0, 80.0, 1.0],
                        [-20.0, -100.0, -80.0, 1.0],
                    ]),
                    (50.0, 80.0, 0.0),
                    (0.0, 0.0, 0.0),
                    diagnostics=diagnostics,
                )
            anomaly = {
                "anomaly_type": "IKError",
                "failed_leg": diagnostics.get("failed_leg"),
                "failure_reason": diagnostics.get("failure_reason"),
                "legs": diagnostics.get("legs", []),
                "servo_write_occurred": False,
            }
            logger.anomaly(anomaly, now=0.1)
            logger.anomaly(anomaly, now=0.2)

            lines = read_jsonl(path)
            self.assertEqual([line["event_type"] for line in lines], ["snapshot", "anomaly"])
            self.assertEqual(lines[1]["anomaly_type"], "IKError")
            self.assertEqual(lines[1]["failed_leg"], "BL")

    def test_non_finite_targets_are_rejected_by_stage1_path(self):
        solver = DHParameterSolver()

        for target in ([math.nan, 0, 0, 1], [math.inf, 0, 0, 1]):
            with self.subTest(target=target):
                with self.assertRaises(IKError):
                    solver.calculate_inverse_kinematics_single_leg(target, {})

    def test_malformed_servo_input_is_available_for_anomaly_without_write(self):
        manager = fake_servo_manager()
        details = {}

        with self.assertRaises(ValueError):
            manager.execute_servo_motion(np.zeros((3, 3)), diagnostics=details)

        self.assertFalse(details["servo_write_occurred"])
        self.assertTrue(all(not servo.writes for servo in manager._servo_array))

    def test_clamp_activation_and_near_reach_boundary_are_recordable_anomalies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "diag.jsonl")
            logger = GaitDiagnosticLogger(enabled=True, path=path)
            manager = fake_servo_manager()
            servo_details = {}
            angles = np.zeros((4, 3), dtype=np.float64)
            angles[0][2] = -1.0

            manager.execute_servo_motion(angles, diagnostics=servo_details)
            logger.anomaly({
                "anomaly_type": "servo_clamp",
                "failure_reason": f"clamped_channels={servo_details['clamped_channels']}",
                "clamped_channels": servo_details["clamped_channels"],
            }, now=1.0)

            ik_details = {}
            DHParameterSolver().calculate_inverse_kinematics_single_leg([220.0, 0.0, 0.0, 1.0], ik_details)
            self.assertGreaterEqual(ik_details["reach_distance_ratio"], 0.95)
            logger.anomaly({
                "anomaly_type": "near_reach_boundary",
                "failed_leg": "FL",
                "failure_reason": f"reach_distance_ratio={ik_details['reach_distance_ratio']}",
                "H": ik_details["H"],
                "D": ik_details["D"],
            }, now=2.0)

            lines = read_jsonl(path)
            self.assertEqual([line["anomaly_type"] for line in lines], ["servo_clamp", "near_reach_boundary"])
            self.assertIn(0, lines[0]["clamped_channels"])

    def test_rotation_and_backup_retention_use_small_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "diag.jsonl")
            logger = GaitDiagnosticLogger(enabled=True, path=path, max_bytes=200, backup_count=1)

            for index in range(20):
                logger.anomaly({"anomaly_type": "rotation", "failure_reason": str(index), "payload": "x" * 60}, now=float(index))

            self.assertTrue(os.path.exists(path))
            self.assertTrue(os.path.exists(path + ".1"))
            self.assertFalse(os.path.exists(path + ".2"))

    def test_write_failure_isolated_and_handlers_are_not_duplicated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "diag.jsonl")
            logger_one = GaitDiagnosticLogger(enabled=True, path=path)
            logger_two = GaitDiagnosticLogger(enabled=True, path=path)
            handlers = [handler for handler in logger_one._logger.handlers if getattr(handler, "_gait_diag_path", None) == path]
            self.assertEqual(len(handlers), 1)
            self.assertIs(logger_one._logger, logger_two._logger)

            with mock.patch.object(logger_one._logger, "info", side_effect=OSError):
                logger_one.snapshot({"legs": []}, now=0.0)

            manager = fake_servo_manager()
            manager.execute_servo_motion(np.zeros((4, 3)), diagnostics={})
            self.assertEqual(sum(len(servo.writes) for servo in manager._servo_array), 12)


if __name__ == "__main__":
    unittest.main()
