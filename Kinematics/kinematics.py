import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from math import sqrt, atan2, acos, sin, cos, pi, isfinite

from utils.config import (ROBOT_L1, ROBOT_L2, ROBOT_L3, ROBOT_L4, ROBOT_L, ROBOT_W,
                         ROBOT_LEG_FRONT, ROBOT_LEG_BACK, ROBOT_LEG_LEFT, ROBOT_LEG_RIGHT,
                         ROBOT_BODY_HEIGHT, GAIT_BODY_POS, GAIT_BODY_ROT)

def create_3d_plot(axis_range):
    figure_axis = plt.axes(projection="3d")
    figure_axis.set_xlim(-axis_range, axis_range)
    figure_axis.set_ylim(-axis_range, axis_range)
    figure_axis.set_zlim(-axis_range, axis_range)
    figure_axis.set_xlabel("X")
    figure_axis.set_ylabel("Z")
    figure_axis.set_zlabel("Y")
    return figure_axis

def _is_valid_coordinate_sequence(values, min_length):
    """Return True if values has at least min_length finite numeric elements."""
    try:
        if values is None or len(values) < min_length:
            return False
        return all(isfinite(float(values[i])) for i in range(min_length))
    except (TypeError, ValueError, OverflowError):
        return False

class DHParameterSolver:
    """
    Denavit-Hartenberg inverse kinematics solver for the Wildfire Spot quadruped.

    Each leg has three revolute joints (shoulder, femur, tibia) and four link
    lengths (L1-L4). The solver computes joint angles from Cartesian foot
    target positions and can optionally apply a body transformation so the
    robot compensates for body tilt or translation.
    """

    def __init__(self):
        # Link lengths (mm) loaded from config
        self.L1 = ROBOT_L1   # Coxa (shoulder to femur pivot)
        self.L2 = ROBOT_L2   # Femur lateral offset
        self.L3 = ROBOT_L3   # Femur link
        self.L4 = ROBOT_L4   # Tibia link

        # Body dimensions (mm)
        self.body_length_L = ROBOT_L  # Front-to-back leg spacing
        self.body_width_W  = ROBOT_W  # Left-to-right leg spacing

        # Index constants used when storing angles into the 4×3 results array
        self.front_leg_index = ROBOT_LEG_FRONT  # Row offset for front legs (0)
        self.back_leg_index  = ROBOT_LEG_BACK   # Row offset for rear legs  (2)
        self.left_leg_index  = ROBOT_LEG_LEFT   # Column offset for left legs (0)
        self.right_leg_index = ROBOT_LEG_RIGHT  # Column offset for right legs (1)

        # Output buffer; updated by solve_complete_inverse_kinematics / init_ik
        self.computed_angles = np.zeros((4, 3), dtype=np.float64)

    def calculate_inverse_kinematics_single_leg(self, end_effector_pos):
        """
        Solve IK for a single leg given a foot target in the leg's local frame.

        Uses the geometric (closed-form) method:
          theta1 — shoulder yaw (rotation about vertical axis)
          theta2 — femur pitch
          theta3 — tibia pitch (elbow angle)

        Args:
            end_effector_pos: Sequence of at least 3 floats [x, y, z] in mm,
                expressed in the leg's local coordinate frame.

        Returns:
            Tuple (theta1, theta2, theta3) in radians, or (0, 0, 0) on failure.
        """
        L1, L2, L3, L4 = self.L1, self.L2, self.L3, self.L4

        try:
            if not _is_valid_coordinate_sequence(end_effector_pos, 3):
                print(f"Invalid IK target: {end_effector_pos}")
                return (0, 0, 0)

            x, y, z = float(end_effector_pos[0]), float(end_effector_pos[1]), float(end_effector_pos[2])

            # Horizontal distance from shoulder to foot projected onto the XY plane
            F = sqrt(max(0, x**2 + y**2 - L1**2))
            G = F - L2  # Subtract the femur lateral offset
            H = sqrt(G**2 + z**2)  # Straight-line distance from femur pivot to foot

            # Shoulder yaw: atan2 of projected position minus coxa offset angle
            theta1 = -atan2(y, x) - atan2(F, -L1)

            if abs(L3 * L4) < 1e-10:
                return (0, 0, 0)

            # Cosine rule for the knee angle (theta3)
            D = (H**2 - L3**2 - L4**2) / (2 * L3 * L4)
            if not isfinite(D) or D < -1 or D > 1:
                print(f"Unreachable IK target: {end_effector_pos}")
                return (0, 0, 0)

            theta3 = acos(D)  # Knee angle (always positive; sign handled by geometry)

            # Femur angle: difference between line-to-foot angle and tibia contribution
            theta2 = atan2(z, G) - atan2(L4*sin(theta3), L3+L4*cos(theta3))

            if not all(isfinite(angle) for angle in (theta1, theta2, theta3)):
                print(f"Invalid IK result for target: {end_effector_pos}")
                return (0, 0, 0)

            return (theta1, theta2, theta3)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError, IndexError) as e:
            print(f"IK calculation failed: {type(e).__name__}: {e}")
            return (0, 0, 0)

    def forward_kinematics_dh_method(self, joint_angles):
        """
        Compute forward kinematics: joint angles → world-space joint positions.

        Used for visualisation only; not called in the real-time gait loop.

        Args:
            joint_angles: Tuple/list (theta1, theta2, theta3) in radians.

        Returns:
            numpy array of shape (5, 4) — one homogeneous point per joint
            [base, shoulder, femur_base, femur_tip, foot].
        """
        L1, L2, L3, L4 = self.L1, self.L2, self.L3, self.L4
        theta1, theta2, theta3 = joint_angles
        combined_angle_23 = theta2 + theta3  # Femur + tibia combined pitch

        joint_0 = np.array([0, 0, 0, 1])  # Body attachment point

        # Shoulder pivot — rotated by theta1 around vertical
        joint_1 = joint_0 + np.array([-L1 * cos(theta1), L1 * sin(theta1), 0, 0])

        # Femur base — offset perpendicular to shoulder
        joint_2 = joint_1 + np.array([-L2 * sin(theta1), -L2 * cos(theta1), 0, 0])

        # Femur tip
        joint_3 = joint_2 + np.array([-L3 * sin(theta1) * cos(theta2),
                                     -L3 * cos(theta1) * cos(theta2),
                                     L3 * sin(theta2), 0])

        # Foot (end effector)
        joint_4 = joint_3 + np.array([-L4 * sin(theta1) * cos(combined_angle_23),
                                     -L4 * cos(theta1) * cos(combined_angle_23),
                                     L4 * sin(combined_angle_23), 0])

        return np.array([joint_0, joint_1, joint_2, joint_3, joint_4])

    def compute_body_transformation(self, roll_angle, pitch_angle, yaw_angle, x_trans, y_trans, z_trans):
        """
        Build per-leg transformation matrices that encode the body pose.

        The body transform (rotation + translation) is composed with fixed
        leg-attachment offsets to produce four 4×4 matrices — one per leg.
        The IK solver then inverts these to express foot targets in each
        leg's local frame.

        Args:
            roll_angle, pitch_angle, yaw_angle: Body orientation in radians.
            x_trans, y_trans, z_trans: Body translation in mm.

        Returns:
            List of four 4×4 numpy arrays [FL, FR, BL, BR].
        """
        # Rotation matrices around each axis
        rotation_x = np.array([[1, 0, 0, 0],
                             [0, cos(roll_angle), -sin(roll_angle), 0],
                             [0, sin(roll_angle), cos(roll_angle), 0],
                             [0, 0, 0, 1]])

        rotation_y = np.array([[cos(pitch_angle), 0, sin(pitch_angle), 0],
                             [0, 1, 0, 0],
                             [-sin(pitch_angle), 0, cos(pitch_angle), 0],
                             [0, 0, 0, 1]])

        rotation_z = np.array([[cos(yaw_angle), -sin(yaw_angle), 0, 0],
                             [sin(yaw_angle), cos(yaw_angle), 0, 0],
                             [0, 0, 1, 0],
                             [0, 0, 0, 1]])

        # Combined rotation: R = Rx · Ry · Rz
        combined_rotation = rotation_x.dot(rotation_y.dot(rotation_z))

        # Pure translation component
        translation_transform = np.array([[0, 0, 0, x_trans],
                                        [0, 0, 0, y_trans],
                                        [0, 0, 0, z_trans],
                                        [0, 0, 0, 0]])

        complete_transform = translation_transform + combined_rotation

        # Fixed 90° rotation used to reorient each leg attachment point
        cos_90 = cos(pi/2)
        sin_90 = sin(pi/2)
        L, W = self.body_length_L, self.body_width_W

        # Each leg attachment matrix = body_transform · fixed_leg_offset
        front_left_transform = complete_transform.dot(np.array([[cos_90, 0, sin_90, L/2],
                                                              [0, 1, 0, 0],
                                                              [-sin_90, 0, cos_90, W/2],
                                                              [0, 0, 0, 1]]))

        front_right_transform = complete_transform.dot(np.array([[cos_90, 0, sin_90, L/2],
                                                               [0, 1, 0, 0],
                                                               [-sin_90, 0, cos_90, -W/2],
                                                               [0, 0, 0, 1]]))

        back_left_transform = complete_transform.dot(np.array([[cos_90, 0, sin_90, -L/2],
                                                             [0, 1, 0, 0],
                                                             [-sin_90, 0, cos_90, W/2],
                                                             [0, 0, 0, 1]]))

        back_right_transform = complete_transform.dot(np.array([[cos_90, 0, sin_90, -L/2],
                                                              [0, 1, 0, 0],
                                                              [-sin_90, 0, cos_90, -W/2],
                                                              [0, 0, 0, 1]]))

        return [front_left_transform, front_right_transform, back_left_transform, back_right_transform]

    def solve_complete_inverse_kinematics(self, foot_target_positions, body_pos, body_orient):
        """
        Solve IK for all four legs given foot targets in world space.

        Applies the body transformation so foot targets are expressed in each
        leg's local frame before calling the single-leg IK solver.

        Right-side legs (FR, BR) are mirrored along the X axis via
        leg_mirror_transform so the same single-leg solver can be reused.

        Args:
            foot_target_positions: numpy array of shape (4, 4) — one
                homogeneous foot target per leg [FL, FR, BL, BR].
            body_pos: (x, y, z) body translation in mm.
            body_orient: (roll, pitch, yaw) body rotation in radians.

        Returns:
            numpy array of shape (4, 3) — joint angles (radians) per leg.

        Raises:
            ValueError: if any input has wrong shape or non-finite values.
        """
        if foot_target_positions is None or len(foot_target_positions) < 4:
            raise ValueError("foot_target_positions must contain 4 leg targets")
        for i in range(4):
            if not _is_valid_coordinate_sequence(foot_target_positions[i], 3):
                raise ValueError(f"foot_target_positions[{i}] must contain 3 finite coordinates")
        if not _is_valid_coordinate_sequence(body_pos, 3):
            raise ValueError("body_pos must contain 3 finite coordinates")
        if not _is_valid_coordinate_sequence(body_orient, 3):
            raise ValueError("body_orient must contain 3 finite values")

        roll, pitch, yaw = body_orient
        x_position, y_position, z_position = body_pos

        # Build the four leg-frame transforms from the current body pose
        leg_coordinate_transforms = self.compute_body_transformation(roll, pitch, yaw, x_position, y_position, z_position)

        # Mirror matrix flips the X axis so right-side legs share the left-side IK solver
        leg_mirror_transform = np.array([[-1, 0, 0, 0],
                                       [0, 1, 0, 0],
                                       [0, 0, 1, 0],
                                       [0, 0, 0, 1]])

        joint_angle_solutions = np.zeros((4, 3))

        # Front-left (no mirror needed)
        joint_angle_solutions[0] = self.calculate_inverse_kinematics_single_leg(
            np.linalg.inv(leg_coordinate_transforms[0]).dot(foot_target_positions[0]))

        # Front-right (mirrored)
        joint_angle_solutions[1] = self.calculate_inverse_kinematics_single_leg(
            leg_mirror_transform.dot(np.linalg.inv(leg_coordinate_transforms[1]).dot(foot_target_positions[1])))

        # Back-left (no mirror needed)
        joint_angle_solutions[2] = self.calculate_inverse_kinematics_single_leg(
            np.linalg.inv(leg_coordinate_transforms[2]).dot(foot_target_positions[2]))

        # Back-right (mirrored)
        joint_angle_solutions[3] = self.calculate_inverse_kinematics_single_leg(
            leg_mirror_transform.dot(np.linalg.inv(leg_coordinate_transforms[3]).dot(foot_target_positions[3])))

        return joint_angle_solutions

    def init_ik(self, foot_positions, enable_plot=False):
        """
        Simplified IK without a body transformation (body-fixed frame).

        Used in the servo controller self-test and for quick stand-pose
        calculations where no body tilt compensation is needed.

        Args:
            foot_positions: Array-like of shape (4, 4) — homogeneous foot targets.
            enable_plot: If True, open an interactive 3D visualisation window.

        Returns:
            numpy array of shape (4, 3) — joint angles in radians.
        """
        if enable_plot:
            visualization_axis = create_3d_plot(200)
            visualization_axis.view_init(elev=12., azim=28)

        self.computed_angles = np.zeros((4, 3))
        for i in range(4):
            self.computed_angles[i] = self.calculate_inverse_kinematics_single_leg(foot_positions[i])

        return self.computed_angles

    def render_robot_structure(self, foot_positions, body_pos, body_orient):
        """
        Render the full robot skeleton in a 3D matplotlib plot.

        Computes FK for each leg and draws body outline plus all leg links.
        Intended for offline debugging and validation only.
        """
        roll, pitch, yaw = body_orient
        x_position, y_position, z_position = body_pos

        origin_point = [0, 0, 0, 1]
        leg_transforms = self.compute_body_transformation(roll, pitch, yaw, x_position, y_position, z_position)
        body_corner_points = [transform.dot(origin_point) for transform in leg_transforms]

        # Draw body rectangle: FL → FR → BR → BL → FL
        body_frame_outline = [body_corner_points[i] for i in [0, 1, 3, 2, 0]]

        plt.plot([p[0] for p in body_frame_outline],
                [p[2] for p in body_frame_outline],
                [p[1] for p in body_frame_outline], 'bo-', lw=2)

        self.visualize_leg_pair(leg_transforms[0], leg_transforms[1],
                              foot_positions[0], foot_positions[1],
                              self.front_leg_index)

        self.visualize_leg_pair(leg_transforms[2], leg_transforms[3],
                              foot_positions[2], foot_positions[3],
                              self.back_leg_index)

    def visualize_leg_pair(self, left_leg_transform, right_leg_transform, left_foot_pos, right_foot_pos, leg_pair_index):
        """
        Solve and plot one left+right leg pair.

        Stores the computed angles into self.computed_angles so the result
        can be inspected after rendering.
        """
        mirror_matrix = np.array([[-1, 0, 0, 0],
                                [0, 1, 0, 0],
                                [0, 0, 1, 0],
                                [0, 0, 0, 1]])

        left_leg_angles = self.calculate_inverse_kinematics_single_leg(
            np.linalg.inv(left_leg_transform).dot(left_foot_pos))
        right_leg_angles = self.calculate_inverse_kinematics_single_leg(
            mirror_matrix.dot(np.linalg.inv(right_leg_transform).dot(right_foot_pos)))

        # Store into the shared results array using front/back and left/right index offsets
        self.computed_angles[leg_pair_index + self.left_leg_index] = np.array(left_leg_angles)
        self.computed_angles[leg_pair_index + self.right_leg_index] = np.array(right_leg_angles)

        left_joint_positions  = [left_leg_transform.dot(point) for point in self.forward_kinematics_dh_method(left_leg_angles)]
        right_joint_positions = [right_leg_transform.dot(mirror_matrix.dot(point)) for point in self.forward_kinematics_dh_method(right_leg_angles)]

        self.plot_leg_links(left_joint_positions)
        self.plot_leg_links(right_joint_positions)

    def plot_leg_links(self, joint_coordinate_list):
        """Draw a single leg as a connected line with markers at base and foot."""
        plt.plot([p[0] for p in joint_coordinate_list],
                [p[2] for p in joint_coordinate_list],
                [p[1] for p in joint_coordinate_list], 'k-', lw=3)

        plt.plot([joint_coordinate_list[0][0]], [joint_coordinate_list[0][2]], [joint_coordinate_list[0][1]], 'bo', lw=2)
        plt.plot([joint_coordinate_list[4][0]], [joint_coordinate_list[4][2]], [joint_coordinate_list[4][1]], 'ro', lw=2)

    def plot(self):
        """Display any open matplotlib figures."""
        plt.show()

    def numerical_validation_test(self):
        """
        Run a self-test comparing solve_complete_inverse_kinematics and init_ik.

        Prints joint angles for four symmetric foot positions and checks that
        both IK methods agree within 0.1°. Returns the degree-converted angles
        from the full body-transform solver.
        """
        test_foot_positions = np.array([
            [100, -100, 87.5, 1],
            [100, -100, -87.5, 1],
            [-100, -100, 87.5, 1],
            [-100, -100, -87.5, 1]
        ])

        print("SpotMicro Validation Test Results:")
        print(f"Robot Parameters: L1={self.L1}, L2={self.L2}, L3={self.L3}, L4={self.L4}")
        print(f"Body dimensions: L={self.body_length_L}, W={self.body_width_W}")

        joint_angles = self.solve_complete_inverse_kinematics(test_foot_positions, (0, 0, 0), (0, 0, 0))
        joint_angles_degrees = joint_angles * 180/pi

        print("\nFoot positions and calculated joint angles:")
        leg_names = ["Front Left", "Front Right", "Back Left", "Back Right"]

        for i in range(4):
            foot_pos = test_foot_positions[i]
            angles_deg = joint_angles_degrees[i]

            print(f"\n{leg_names[i]}:")
            print(f"  Foot position: x={foot_pos[0]}, y={foot_pos[1]}, z={foot_pos[2]}")
            print(f"  Joint angles: θ1={angles_deg[0]:.1f}°, θ2={angles_deg[1]:.1f}°, θ3={angles_deg[2]:.1f}°")

            valid_angles = all(-180 <= angle <= 180 for angle in angles_deg)
            print(f"  Valid range (-180° to 180°): {valid_angles}")

            if not valid_angles:
                out_of_range = [f"θ{j+1}={angles_deg[j]:.1f}°" for j in range(3) if not (-180 <= angles_deg[j] <= 180)]
                print(f"  Out of range: {', '.join(out_of_range)}")

        all_valid = all(all(-180 <= angle <= 180 for angle in leg) for leg in joint_angles_degrees)

        print(f"\nOverall validation: {'PASSED' if all_valid else 'FAILED'}")
        if all_valid:
            print("All joint angles are within reasonable servo limits (-180° to 180°)")
        else:
            print("Some joint angles exceed reasonable servo limits")

        print("\nComparing with init_ik() method:")
        init_ik_angles = self.init_ik(test_foot_positions)
        init_ik_degrees = init_ik_angles * 180/pi

        max_difference = np.max(np.abs(joint_angles_degrees - init_ik_degrees))
        print(f"Maximum difference between methods: {max_difference:.3f}°")

        if max_difference < 0.1:
            print("Both methods produce consistent results")
        else:
            print("Significant difference detected between methods")

        return joint_angles_degrees


if __name__ == "__main__":
    test_foot_positions = np.array([[100, -100, 100, 1],
                                  [100, -100, -100, 1],
                                  [-100, -100, 100, 1],
                                  [-100, -100, -100, 1]])

    kinematics_engine = DHParameterSolver()
    computed_joint_angles = kinematics_engine.init_ik(test_foot_positions)

    kinematics_engine.numerical_validation_test()

    kinematics_engine.plot()
