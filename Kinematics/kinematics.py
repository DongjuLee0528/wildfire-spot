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
    ax = plt.axes(projection="3d")
    ax.set_xlim(-axis_limit, axis_limit)
    ax.set_ylim(-axis_limit, axis_limit)
    ax.set_zlim(-axis_limit, axis_limit)
    ax.set_xlabel("X")
    ax.set_ylabel("Z")
    ax.set_zlabel("Y")
    return ax


class QuadrupedKinematics:

    def __init__(self):
        self.link1 = ROBOT_L1
        self.link2 = ROBOT_L2
        self.link3 = ROBOT_L3
        self.link4 = ROBOT_L4
        self.body_length = ROBOT_L
        self.body_width = ROBOT_W

        self.leg_front = ROBOT_LEG_FRONT
        self.leg_back = ROBOT_LEG_BACK
        self.leg_left = ROBOT_LEG_LEFT
        self.leg_right = ROBOT_LEG_RIGHT

        self.joint_angles = np.zeros((4, 3), dtype=np.float64)

    def leg_ik(self, target_point):
        x, y, z = target_point[0], target_point[1], target_point[2]
        l1, l2, l3, l4 = self.link1, self.link2, self.link3, self.link4

        try:
            F = sqrt(x**2 + y**2 - l1**2)
        except ValueError:
            F = l1

        G = F - l2
        H = sqrt(G**2 + z**2)
        theta1 = -atan2(y, x) - atan2(F, -l1)

        D = (H**2 - l3**2 - l4**2) / (2 * l3 * l4)
        try:
            theta3 = acos(D)
        except ValueError:
            theta3 = 0

        theta2 = atan2(z, G) - atan2(l4 * sin(theta3), l3 + l4 * cos(theta3))

        return (theta1, theta2, theta3)

    def leg_fk(self, joint_angles):
        l1, l2, l3, l4 = self.link1, self.link2, self.link3, self.link4
        theta1, theta2, theta3 = joint_angles
        theta23 = theta2 + theta3

        p0 = np.array([0, 0, 0, 1])
        p1 = p0 + np.array([-l1 * cos(theta1), l1 * sin(theta1), 0, 0])
        p2 = p1 + np.array([-l2 * sin(theta1), -l2 * cos(theta1), 0, 0])
        p3 = p2 + np.array([-l3 * sin(theta1) * cos(theta2),
                           -l3 * cos(theta1) * cos(theta2),
                           l3 * sin(theta2), 0])
        p4 = p3 + np.array([-l4 * sin(theta1) * cos(theta23),
                           -l4 * cos(theta1) * cos(theta23),
                           l4 * sin(theta23), 0])

        return np.array([p0, p1, p2, p3, p4])

    def body_ik(self, roll, pitch, yaw, x_offset, y_offset, z_offset):
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

        rotation_matrix = Rx.dot(Ry.dot(Rz))

        translation_matrix = np.array([[0, 0, 0, x_offset],
                                     [0, 0, 0, y_offset],
                                     [0, 0, 0, z_offset],
                                     [0, 0, 0, 0]])

        body_transform = translation_matrix + rotation_matrix

        half_pi_sin = sin(pi/2)
        half_pi_cos = cos(pi/2)
        L, W = self.body_length, self.body_width

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
        roll, pitch, yaw = body_rotation
        x_pos, y_pos, z_pos = body_position

        leg_transforms = self.body_ik(roll, pitch, yaw, x_pos, y_pos, z_pos)

        mirror_matrix = np.array([[-1, 0, 0, 0],
                                 [0, 1, 0, 0],
                                 [0, 0, 1, 0],
                                 [0, 0, 0, 1]])

        angles = np.zeros((4, 3))

        angles[0] = self.leg_ik(np.linalg.inv(leg_transforms[0]).dot(foot_positions[0]))
        angles[1] = self.leg_ik(mirror_matrix.dot(np.linalg.inv(leg_transforms[1]).dot(foot_positions[1])))
        angles[2] = self.leg_ik(np.linalg.inv(leg_transforms[2]).dot(foot_positions[2]))
        angles[3] = self.leg_ik(mirror_matrix.dot(np.linalg.inv(leg_transforms[3]).dot(foot_positions[3])))

        return angles

    def init_ik(self, foot_positions):
        ax = setup_3d_view(200)
        ax.view_init(elev=12., azim=28)

        self.joint_angles = self.calc_ik(foot_positions, (0, 0, 0), (0, 0, 0))
        self.visualize_robot(foot_positions, (0, 0, 0), (0, 0, 0))

        return self.joint_angles

    def visualize_robot(self, foot_positions, body_position, body_rotation):
        roll, pitch, yaw = body_rotation
        x_pos, y_pos, z_pos = body_position

        home_point = [0, 0, 0, 1]
        leg_transforms = self.body_ik(roll, pitch, yaw, x_pos, y_pos, z_pos)
        corner_points = [transform.dot(home_point) for transform in leg_transforms]

        body_outline = [corner_points[i] for i in [0, 1, 3, 2, 0]]

        plt.plot([p[0] for p in body_outline],
                [p[2] for p in body_outline],
                [p[1] for p in body_outline], 'bo-', lw=2)

        self.render_leg_pair(leg_transforms[0], leg_transforms[1],
                            foot_positions[0], foot_positions[1],
                            self.leg_front)

        self.render_leg_pair(leg_transforms[2], leg_transforms[3],
                            foot_positions[2], foot_positions[3],
                            self.leg_back)

    def render_leg_pair(self, left_transform, right_transform, left_foot, right_foot, leg_group):
        mirror_matrix = np.array([[-1, 0, 0, 0],
                                 [0, 1, 0, 0],
                                 [0, 0, 1, 0],
                                 [0, 0, 0, 1]])

        left_angles = self.leg_ik(np.linalg.inv(left_transform).dot(left_foot))
        right_angles = self.leg_ik(mirror_matrix.dot(np.linalg.inv(right_transform).dot(right_foot)))

        self.joint_angles[leg_group + self.leg_left] = np.array(left_angles)
        self.joint_angles[leg_group + self.leg_right] = np.array(right_angles)

        left_points = [left_transform.dot(point) for point in self.leg_fk(left_angles)]
        right_points = [right_transform.dot(mirror_matrix.dot(point)) for point in self.leg_fk(right_angles)]

        self.draw_leg_structure(left_points)
        self.draw_leg_structure(right_points)

    def draw_leg_structure(self, joint_points):
        plt.plot([p[0] for p in joint_points],
                [p[2] for p in joint_points],
                [p[1] for p in joint_points], 'k-', lw=3)

        plt.plot([joint_points[0][0]], [joint_points[0][2]], [joint_points[0][1]], 'bo', lw=2)
        plt.plot([joint_points[4][0]], [joint_points[4][2]], [joint_points[4][1]], 'ro', lw=2)

    def plot(self):
        plt.show()


if __name__ == "__main__":
    foot_positions = np.array([[100, -100, 100, 1],
                              [100, -100, -100, 1],
                              [-100, -100, 100, 1],
                              [-100, -100, -100, 1]])

    robot_kinematics = QuadrupedKinematics()
    calculated_angles = robot_kinematics.init_ik(foot_positions)
    robot_kinematics.plot()