import math
import unittest

import numpy as np

from Kinematics.kinematics import DHParameterSolver, IKError
from hardware.servo_controller import QuadrupedServoManager


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
    manager._diag_last_log = 0.0
    manager._DIAG_INTERVAL = 999999.0
    return manager


class IKFailureHandlingTest(unittest.TestCase):
    def test_reachable_single_leg_target_returns_expected_finite_solution(self):
        solver = DHParameterSolver()

        angles = solver.calculate_inverse_kinematics_single_leg([100, -100, 100, 1])

        self.assertEqual(len(angles), 3)
        self.assertTrue(all(math.isfinite(angle) for angle in angles))
        self.assertTrue(np.allclose(angles, (-1.146765287304156, 0.007581557290274876, 1.439998829849497)))

    def test_d_greater_than_one_target_is_rejected(self):
        solver = DHParameterSolver()

        with self.assertRaisesRegex(IKError, "D="):
            solver.calculate_inverse_kinematics_single_leg([500, 0, 0, 1])

    def test_d_less_than_minus_one_is_not_reachable_with_current_positive_link_geometry(self):
        solver = DHParameterSolver()
        min_d = -(solver.L3 ** 2 + solver.L4 ** 2) / (2 * solver.L3 * solver.L4)

        self.assertEqual(min_d, -1)

    def test_nan_and_inf_targets_are_rejected(self):
        solver = DHParameterSolver()

        for target in ([math.nan, 0, 0, 1], [math.inf, 0, 0, 1], [0, -math.inf, 0, 1]):
            with self.subTest(target=target):
                with self.assertRaises(IKError):
                    solver.calculate_inverse_kinematics_single_leg(target)

    def test_invalid_joint_result_cannot_reach_servo_conversion_or_write(self):
        manager = fake_servo_manager()

        with self.assertRaises(ValueError):
            manager.execute_servo_motion(np.full((4, 3), math.nan))

        self.assertEqual(manager._joint_angles, [])
        self.assertTrue(all(servo.writes == [] for servo in manager._servo_array))

    def test_one_failed_leg_rejects_complete_tick_before_any_servo_write(self):
        solver = DHParameterSolver()
        manager = fake_servo_manager()
        foot_positions = np.array([
            [120.0, -100.0, 80.0, 1.0],
            [120.0, -100.0, -80.0, 1.0],
            [500.0, -100.0, 80.0, 1.0],
            [-20.0, -100.0, -80.0, 1.0],
        ])

        with self.assertRaisesRegex(IKError, "BL leg IK failed"):
            joint_angles = solver.solve_complete_inverse_kinematics(foot_positions, (50.0, 80.0, 0.0), (0.0, 0.0, 0.0))
            manager.execute_servo_motion(joint_angles)

        self.assertTrue(all(servo.writes == [] for servo in manager._servo_array))


if __name__ == "__main__":
    unittest.main()
