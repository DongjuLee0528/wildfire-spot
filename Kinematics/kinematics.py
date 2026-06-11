"""
Quadruped Robot Kinematics Module

This module provides inverse and forward kinematics calculations for a quadruped robot.
It includes body pose transformations, leg position calculations, and 3D visualization
capabilities. The kinematics model supports 4-legged robots with 3 joints per leg.

Classes:
    QuadrupedKinematics: Main class for kinematics calculations and visualization

Functions:
    setup_3d_view: Initialize 3D matplotlib visualization environment
"""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from math import sqrt, atan2, acos, sin, cos, pi

try:
    from utils.config import *
except ImportError:
    ROBOT_L1 = 50
    ROBOT_L2 = 20
    ROBOT_L3 = 100
    ROBOT_L4 = 100
    ROBOT_L = 140
    ROBOT_W = 75
    ROBOT_LEG_FRONT = 0
    ROBOT_LEG_BACK = 2
    ROBOT_LEG_LEFT = 0
    ROBOT_LEG_RIGHT = 1


def setup_3d_view(axis_limit):
    """
    Initialize 3D matplotlib visualization environment for robot display.

    Args:
        axis_limit (float): Maximum range for all three axes (symmetric around origin)

    Returns:
        matplotlib.axes._subplots.Axes3DSubplot: Configured 3D axes object
    """
    ax = plt.axes(projection="3d")
    ax.set_xlim(-axis_limit, axis_limit)
    ax.set_ylim(-axis_limit, axis_limit)
    ax.set_zlim(-axis_limit, axis_limit)
    ax.set_xlabel("X")
    ax.set_ylabel("Z")
    ax.set_zlabel("Y")
    return ax


class QuadrupedKinematics:
    """
    Quadruped robot kinematics calculator and visualizer.

    This class handles inverse and forward kinematics for a 4-legged robot with 3 joints per leg.
    It calculates joint angles from desired foot positions and body poses, and provides
    visualization capabilities for robot configuration.

    Attributes:
        link1 (float): Hip joint offset distance (mm)
        link2 (float): Upper leg segment length (mm)
        link3 (float): Thigh bone length (mm)
        link4 (float): Shin bone length (mm)
        body_length (float): Robot body length (mm)
        body_width (float): Robot body width (mm)
        joint_angles (np.ndarray): Current joint angles for all 4 legs [4x3]
    """

    def __init__(self):
        """Initialize kinematics calculator with robot dimensions and leg configuration."""
        self.link1 = ROBOT_L1  # Hip offset
        self.link2 = ROBOT_L2  # Upper leg
        self.link3 = ROBOT_L3  # Thigh
        self.link4 = ROBOT_L4  # Shin
        self.body_length = ROBOT_L
        self.body_width = ROBOT_W

        # Leg identification indices
        self.leg_front = ROBOT_LEG_FRONT
        self.leg_back = ROBOT_LEG_BACK
        self.leg_left = ROBOT_LEG_LEFT
        self.leg_right = ROBOT_LEG_RIGHT

        # Joint angles storage: [leg0, leg1, leg2, leg3] x [joint1, joint2, joint3]
        self.joint_angles = np.zeros((4, 3), dtype=np.float64)

    def leg_ik(self, target_point):
        """
        Calculate inverse kinematics for a single leg.

        Computes joint angles required to reach a target foot position using
        geometric approach with trigonometric calculations.

        Args:
            target_point (array-like): Target foot position [x, y, z] in leg coordinate frame

        Returns:
            tuple: Joint angles (theta1, theta2, theta3) in radians
                - theta1: Hip yaw angle
                - theta2: Hip pitch angle
                - theta3: Knee angle
        """
        x, y, z = target_point[0], target_point[1], target_point[2]
        l1, l2, l3, l4 = self.link1, self.link2, self.link3, self.link4

        # Calculate projected distance in XY plane accounting for hip offset
        try:
            F = sqrt(x**2 + y**2 - l1**2)
        except ValueError:
            # Handle case where target is too close to hip joint
            F = l1

        # Adjust for upper leg segment and calculate hypotenuse to target
        G = F - l2
        H = sqrt(G**2 + z**2)

        # Hip yaw angle calculation
        theta1 = -atan2(y, x) - atan2(F, -l1)

        # Knee angle using law of cosines
        D = (H**2 - l3**2 - l4**2) / (2 * l3 * l4)
        try:
            theta3 = acos(D)
        except ValueError:
            # Handle unreachable positions
            theta3 = 0

        # Hip pitch angle accounting for knee bend
        theta2 = atan2(z, G) - atan2(l4 * sin(theta3), l3 + l4 * cos(theta3))

        return (theta1, theta2, theta3)

    def leg_fk(self, joint_angles):
        """
        Calculate forward kinematics for a single leg.

        Computes joint positions given joint angles using homogeneous transformations.

        Args:
            joint_angles (tuple): Joint angles (theta1, theta2, theta3) in radians

        Returns:
            np.ndarray: Joint positions [5x4] from hip to foot in homogeneous coordinates
                - p0: Hip base (origin)
                - p1: Hip joint
                - p2: Upper leg end
                - p3: Knee joint
                - p4: Foot position
        """
        l1, l2, l3, l4 = self.link1, self.link2, self.link3, self.link4
        theta1, theta2, theta3 = joint_angles
        theta23 = theta2 + theta3  # Combined knee-ankle angle

        # Sequential joint position calculation using DH parameters
        p0 = np.array([0, 0, 0, 1])  # Hip base
        p1 = p0 + np.array([-l1 * cos(theta1), l1 * sin(theta1), 0, 0])  # Hip joint
        p2 = p1 + np.array([-l2 * sin(theta1), -l2 * cos(theta1), 0, 0])  # Upper leg end
        p3 = p2 + np.array([-l3 * sin(theta1) * cos(theta2),
                           -l3 * cos(theta1) * cos(theta2),
                           l3 * sin(theta2), 0])  # Knee joint
        p4 = p3 + np.array([-l4 * sin(theta1) * cos(theta23),
                           -l4 * cos(theta1) * cos(theta23),
                           l4 * sin(theta23), 0])  # Foot position

        return np.array([p0, p1, p2, p3, p4])

    def body_ik(self, roll, pitch, yaw, x_offset, y_offset, z_offset):
        """
        Calculate body transformation matrices for each leg mount point.

        Computes transformation matrices for all four leg attachment points on the robot body,
        accounting for body pose (orientation and position) in 3D space.

        Args:
            roll (float): Body roll angle in radians (rotation around X-axis)
            pitch (float): Body pitch angle in radians (rotation around Y-axis)
            yaw (float): Body yaw angle in radians (rotation around Z-axis)
            x_offset (float): Body position offset in X direction
            y_offset (float): Body position offset in Y direction
            z_offset (float): Body position offset in Z direction

        Returns:
            list: Four 4x4 transformation matrices for [front_left, front_right, back_left, back_right] legs
        """
        # Create individual rotation matrices for each axis
        Rx = np.array([[1, 0, 0, 0],
                      [0, cos(roll), -sin(roll), 0],
                      [0, sin(roll), cos(roll), 0],
                      [0, 0, 0, 1]])

        Ry = np.array([[cos(pitch), 0, sin(pitch), 0],
                      [0, 1, 0, 0],
                      [-sin(pitch), 0, cos(pitch), 0],
                      [0, 0, 0, 1]])

        Rz = np.array([[cos(yaw), -sin(yaw), 0, 0],
                      [sin(yaw), cos(yaw), 0, 0],
                      [0, 0, 1, 0],
                      [0, 0, 0, 1]])

        # Combine rotations: R = Rx * Ry * Rz
        rotation_matrix = Rx.dot(Ry.dot(Rz))

        # Create translation matrix
        translation_matrix = np.array([[0, 0, 0, x_offset],
                                     [0, 0, 0, y_offset],
                                     [0, 0, 0, z_offset],
                                     [0, 0, 0, 0]])

        # Combined body transformation
        body_transform = translation_matrix + rotation_matrix

        # Precompute 90-degree rotation values for leg mounting
        half_pi_sin = sin(pi/2)
        half_pi_cos = cos(pi/2)
        L, W = self.body_length, self.body_width

        # Calculate transformation matrices for each leg mount point
        front_left = body_transform.dot(np.array([[half_pi_cos, 0, half_pi_sin, L/2],
                                                 [0, 1, 0, 0],
                                                 [-half_pi_sin, 0, half_pi_cos, W/2],
                                                 [0, 0, 0, 1]]))

        front_right = body_transform.dot(np.array([[half_pi_cos, 0, half_pi_sin, L/2],
                                                  [0, 1, 0, 0],
                                                  [-half_pi_sin, 0, half_pi_cos, -W/2],
                                                  [0, 0, 0, 1]]))

        back_left = body_transform.dot(np.array([[half_pi_cos, 0, half_pi_sin, -L/2],
                                                [0, 1, 0, 0],
                                                [-half_pi_sin, 0, half_pi_cos, W/2],
                                                [0, 0, 0, 1]]))

        back_right = body_transform.dot(np.array([[half_pi_cos, 0, half_pi_sin, -L/2],
                                                 [0, 1, 0, 0],
                                                 [-half_pi_sin, 0, half_pi_cos, -W/2],
                                                 [0, 0, 0, 1]]))

        return [front_left, front_right, back_left, back_right]

    def calc_ik(self, foot_positions, body_position, body_rotation):
        """
        Calculate inverse kinematics for all four legs given desired foot positions and body pose.

        Args:
            foot_positions (list): Target foot positions [4x4] in world coordinates
            body_position (tuple): Body center position (x, y, z)
            body_rotation (tuple): Body orientation (roll, pitch, yaw) in radians

        Returns:
            np.ndarray: Joint angles [4x3] for all legs
        """
        roll, pitch, yaw = body_rotation
        x_pos, y_pos, z_pos = body_position

        # Get transformation matrices for each leg mount point
        leg_transforms = self.body_ik(roll, pitch, yaw, x_pos, y_pos, z_pos)

        # Mirror matrix for right-side legs (flip Y-axis)
        mirror_matrix = np.array([[-1, 0, 0, 0],
                                 [0, 1, 0, 0],
                                 [0, 0, 1, 0],
                                 [0, 0, 0, 1]])

        angles = np.zeros((4, 3))

        # Calculate IK for each leg, transforming foot positions to leg coordinate frames
        angles[0] = self.leg_ik(np.linalg.inv(leg_transforms[0]).dot(foot_positions[0]))  # Front left
        angles[1] = self.leg_ik(mirror_matrix.dot(np.linalg.inv(leg_transforms[1]).dot(foot_positions[1])))  # Front right (mirrored)
        angles[2] = self.leg_ik(np.linalg.inv(leg_transforms[2]).dot(foot_positions[2]))  # Back left
        angles[3] = self.leg_ik(mirror_matrix.dot(np.linalg.inv(leg_transforms[3]).dot(foot_positions[3])))  # Back right (mirrored)

        return angles

    def init_ik(self, foot_positions):
        """
        Initialize robot kinematics with desired foot positions and neutral body pose.

        Sets up 3D visualization and calculates initial joint angles for given foot positions.
        Body is positioned at origin with zero rotation.

        Args:
            foot_positions (np.ndarray): Desired foot positions [4x4] in world coordinates

        Returns:
            np.ndarray: Calculated joint angles [4x3] for all legs
        """
        ax = setup_3d_view(200)
        ax.view_init(elev=12., azim=28)

        # Calculate and store joint angles for neutral body pose
        self.joint_angles = self.calc_ik(foot_positions, (0, 0, 0), (0, 0, 0))
        self.visualize_robot(foot_positions, (0, 0, 0), (0, 0, 0))

        return self.joint_angles

    def visualize_robot(self, foot_positions, body_position, body_rotation):
        """
        Visualize robot configuration in 3D space.

        Draws robot body outline and all four legs with current joint angles.

        Args:
            foot_positions (list): Current foot positions [4x4]
            body_position (tuple): Body center position (x, y, z)
            body_rotation (tuple): Body orientation (roll, pitch, yaw)
        """
        roll, pitch, yaw = body_rotation
        x_pos, y_pos, z_pos = body_position

        # Calculate leg mount points on body
        home_point = [0, 0, 0, 1]
        leg_transforms = self.body_ik(roll, pitch, yaw, x_pos, y_pos, z_pos)
        corner_points = [transform.dot(home_point) for transform in leg_transforms]

        # Draw body outline connecting the four leg mount points
        body_outline = [corner_points[i] for i in [0, 1, 3, 2, 0]]  # Close the shape

        plt.plot([p[0] for p in body_outline],
                [p[2] for p in body_outline],
                [p[1] for p in body_outline], 'bo-', lw=2)

        # Render front leg pair
        self.render_leg_pair(leg_transforms[0], leg_transforms[1],
                            foot_positions[0], foot_positions[1],
                            self.leg_front)

        # Render back leg pair
        self.render_leg_pair(leg_transforms[2], leg_transforms[3],
                            foot_positions[2], foot_positions[3],
                            self.leg_back)

    def render_leg_pair(self, left_transform, right_transform, left_foot, right_foot, leg_group):
        """
        Render a pair of legs (left and right) for visualization.

        Calculates joint angles and forward kinematics for both legs, then draws them.

        Args:
            left_transform (np.ndarray): Transformation matrix for left leg mount point
            right_transform (np.ndarray): Transformation matrix for right leg mount point
            left_foot (np.ndarray): Left foot target position
            right_foot (np.ndarray): Right foot target position
            leg_group (int): Leg group identifier (front or back)
        """
        # Mirror matrix for right-side legs
        mirror_matrix = np.array([[-1, 0, 0, 0],
                                 [0, 1, 0, 0],
                                 [0, 0, 1, 0],
                                 [0, 0, 0, 1]])

        # Calculate IK for both legs in the pair
        left_angles = self.leg_ik(np.linalg.inv(left_transform).dot(left_foot))
        right_angles = self.leg_ik(mirror_matrix.dot(np.linalg.inv(right_transform).dot(right_foot)))

        # Store calculated angles in joint angles array
        self.joint_angles[leg_group + self.leg_left] = np.array(left_angles)
        self.joint_angles[leg_group + self.leg_right] = np.array(right_angles)

        # Calculate forward kinematics to get joint positions for drawing
        left_points = [left_transform.dot(point) for point in self.leg_fk(left_angles)]
        right_points = [right_transform.dot(mirror_matrix.dot(point)) for point in self.leg_fk(right_angles)]

        # Draw both legs
        self.draw_leg_structure(left_points)
        self.draw_leg_structure(right_points)

    def draw_leg_structure(self, joint_points):
        """
        Draw a single leg structure with joints and links.

        Args:
            joint_points (list): Joint positions from hip to foot [5x4]
        """
        # Draw leg links as connected line segments
        plt.plot([p[0] for p in joint_points],
                [p[2] for p in joint_points],
                [p[1] for p in joint_points], 'k-', lw=3)

        # Draw hip joint marker (blue)
        plt.plot([joint_points[0][0]], [joint_points[0][2]], [joint_points[0][1]], 'bo', lw=2)
        # Draw foot marker (red)
        plt.plot([joint_points[4][0]], [joint_points[4][2]], [joint_points[4][1]], 'ro', lw=2)

    def plot(self):
        """
        Display the 3D visualization plot.
        """
        plt.show()


if __name__ == "__main__":
    foot_positions = np.array([[100, -100, 100, 1],
                              [100, -100, -100, 1],
                              [-100, -100, 100, 1],
                              [-100, -100, -100, 1]])

    robot_kinematics = QuadrupedKinematics()
    calculated_angles = robot_kinematics.init_ik(foot_positions)
    robot_kinematics.plot()