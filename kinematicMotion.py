"""
Quadruped leg motion planning and diagonal trot gait generation.

Three classes work together to animate the robot's legs:
  LegMotionController    — time-based linear interpolation for a single leg.
  QuadrupedMotionManager — coordinates motion for all four legs simultaneously.
  QuadrupedGaitPattern   — generates target foot positions using a four-phase
                           diagonal trot gait driven by keyboard input and time.

The output of QuadrupedGaitPattern.calculate_leg_positions() is a numpy array
of shape (4, 4) (homogeneous foot targets) fed to
DHParameterSolver.solve_complete_inverse_kinematics() in the gait loop.
"""

from utils.config import (GAIT_STEP_GAIN, GAIT_MAX_SL, GAIT_BODY_POS, GAIT_BODY_ROT,
                         GAIT_TIMING, GAIT_INITIAL_VALUES, GAIT_FOOT_POSITIONS,
                         GAIT_RC, GAIT_ANGLE_STEP, GAIT_END_Y, GAIT_TOTAL_TIME_CALC,
                         MATH_PI_DIVISOR, STEP_HEIGHT, FORWARD_DISTANCE, BACKWARD_DISTANCE,
                         ROBOT_BODY_HEIGHT)
import time
import numpy as np
import math

class LegMotionController:
    """
    Time-based position interpolator for a single leg.

    Moves a leg from its current position to a target position over a
    given duration in milliseconds. An optional motion_func can modify
    the interpolated position on each step (e.g. to add a lift arc).
    """

    def __init__(self, initial_position):
        """
        Args:
            initial_position: Starting foot position as a numpy array (homogeneous).
        """
        self.current_time = time.time()
        self.is_active = False
        self.leg_position = initial_position

    def initiate_move(self, target_position, duration_ms, motion_func=None):
        """
        Start a new motion toward target_position over duration_ms milliseconds.

        Returns False without starting if a motion is already in progress.

        Args:
            target_position: Destination foot position (numpy array, homogeneous).
            duration_ms: Motion duration in milliseconds.
            motion_func: Optional callable(progress_ratio, position) that modifies
                         the interpolated position each step (e.g. swing arc).
        """
        if self.is_active:
            print("Motion already in progress, please wait.")
            return False

        self.motion_start_time = time.time()
        self.initial_position = self.leg_position
        self.motion_function = motion_func
        self.target_position = target_position
        self.motion_end_time = time.time() + duration_ms / 1000
        self.is_active = True
        return True

    def refresh_position(self):
        """
        Advance the interpolation by the time elapsed since initiate_move.

        Updates self.leg_position. Applies motion_func if provided.
        Sets is_active to False when the motion deadline is reached.
        """
        elapsed_time = time.time() - self.motion_start_time
        position_delta = self.target_position - self.initial_position
        total_duration = self.motion_end_time - self.motion_start_time

        try:
            progress_ratio = elapsed_time / total_duration
        except ZeroDivisionError as e:
            progress_ratio = 1

        if time.time() > self.motion_end_time and self.is_active:
            self.is_active = False
            progress_ratio = 1

        self.leg_position = self.initial_position + position_delta * progress_ratio

        if self.motion_function:
            self.leg_position = self.motion_function(progress_ratio, self.leg_position)

    def execute_step(self):
        """
        Advance the motion and return the current leg position.

        Returns:
            Current foot position as a numpy array.
        """
        if self.is_active:
            self.refresh_position()
        return self.leg_position

class QuadrupedMotionManager:
    """
    Coordinates simultaneous motion for all four legs.

    Wraps four LegMotionController instances and provides convenience
    methods to start and step all legs together.
    """

    def __init__(self, leg_positions):
        """
        Args:
            leg_positions: List of four initial foot positions (numpy arrays).
        """
        self.leg_positions = leg_positions
        self.leg_controllers = [LegMotionController(leg_positions[i]) for i in range(4)]

    def move_all_legs(self, new_positions, duration_ms):
        """Start a simultaneous motion on all four legs toward new_positions."""
        [self.leg_controllers[i].initiate_move(new_positions[i], duration_ms) for i in range(4)]

    def move_single_leg(self, leg_index, new_position, duration_ms, motion_func=None):
        """Start a motion on a single leg; leg_index is 0=FL, 1=FR, 2=BL, 3=BR."""
        return self.leg_controllers[leg_index].initiate_move(new_position, duration_ms, motion_func)

    def execute_motion_step(self):
        """Advance all leg motions and return the current foot positions as a list."""
        return [controller.execute_step() for controller in self.leg_controllers]

class QuadrupedGaitPattern:
    """
    Diagonal trot gait: generates target foot positions from keyboard input and time.

    The gait is divided into four sequential phases per leg (phase 0-3):
      Phase 0: hold at start position
      Phase 1: swing forward (air phase) with optional yaw rotation applied
      Phase 2: hold at end position
      Phase 3: push back (ground phase, with vertical lift arc)

    Front-left/back-right and front-right/back-left legs move in opposing phase
    (half-period offset) to maintain stability during a trot.
    """

    def __init__(self):
        self.stride_gain = GAIT_STEP_GAIN
        self.max_stride_length = GAIT_MAX_SL

        self.body_position = GAIT_BODY_POS
        self.body_rotation = GAIT_BODY_ROT

        self.phase_0_time = GAIT_TIMING[0]
        self.phase_1_time = GAIT_TIMING[1]
        self.phase_2_time = GAIT_TIMING[2]
        self.phase_3_time = GAIT_TIMING[3]

        self.stride_length = GAIT_INITIAL_VALUES[0]
        self.stride_width = GAIT_INITIAL_VALUES[1]
        self.lift_height = STEP_HEIGHT
        self.stride_angle = GAIT_INITIAL_VALUES[2]

        self.front_spacing = GAIT_FOOT_POSITIONS[0]
        self.rear_spacing = GAIT_FOOT_POSITIONS[1]

        self.forward_offset = FORWARD_DISTANCE
        self.rear_offset = abs(BACKWARD_DISTANCE)

        self.rotation_center = GAIT_RC

    def compute_leg_trajectory(self, time_param, x_pos, y_pos, z_pos):
        """
        Compute the target foot position for one leg at the given gait phase time.

        Args:
            time_param: Current phase time in milliseconds (0 to total period).
            x_pos: Nominal foot X position in mm (forward offset from body centre).
            y_pos: Nominal foot Y position in mm (body height, negative downward).
            z_pos: Nominal foot Z position in mm (lateral offset, sign encodes side).

        Returns:
            numpy array of shape (4,) — homogeneous foot target [x, y, z, 1].
        """
        start_position = np.array([x_pos - self.stride_length/2.0, y_pos, z_pos - self.stride_width, 1])
        end_y_position = GAIT_END_Y
        end_position = np.array([x_pos + self.stride_length/2, y_pos + end_y_position, z_pos + self.stride_width, 1])

        if time_param < self.phase_0_time:
            return start_position

        elif time_param < self.phase_0_time + self.phase_1_time:
            delta_time = time_param - self.phase_0_time
            try:
                time_progress = delta_time / self.phase_1_time
            except ZeroDivisionError as e:
                time_progress = 0

            position_difference = end_position - start_position
            current_position = start_position + position_difference * time_progress

            try:
                rotation_angle = -((math.pi/MATH_PI_DIVISOR*self.stride_angle)/2) + (math.pi/MATH_PI_DIVISOR*self.stride_angle)*time_progress
            except (ZeroDivisionError, ValueError) as e:
                rotation_angle = 0

            try:
                rotation_matrix = np.array([[np.cos(rotation_angle), 0, np.sin(rotation_angle), 0],
                                          [0, 1, 0, 0],
                                          [-np.sin(rotation_angle), 0, np.cos(rotation_angle), 0],
                                          [0, 0, 0, 1]])
            except (ValueError, OverflowError) as e:
                rotation_matrix = np.array([[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])

            try:
                current_position = rotation_matrix.dot(current_position)
            except (ValueError, np.linalg.LinAlgError) as e:
                current_position = start_position
            return current_position

        elif time_param < self.phase_0_time + self.phase_1_time + self.phase_2_time:
            return end_position

        elif time_param < self.phase_0_time + self.phase_1_time + self.phase_2_time + self.phase_3_time:
            delta_time = time_param - (self.phase_0_time + self.phase_1_time + self.phase_2_time)
            try:
                time_progress = delta_time / self.phase_3_time
            except ZeroDivisionError as e:
                time_progress = 0

            position_difference = start_position - end_position
            current_position = end_position + position_difference * time_progress

            try:
                current_position[1] += self.lift_height * math.sin(math.pi * time_progress)
            except (ValueError, OverflowError, IndexError) as e:
                pass
            return current_position

    def set_stride_length(self, length):
        """Override the stride length directly (bypasses keyboard input mapping)."""
        self.stride_length = length

    def calculate_leg_positions(self, time_value, keyboard_input={}):
        """
        Compute target foot positions for all four legs at the given wall-clock time.

        Reads IDstepLength, IDstepWidth, and IDstepAlpha from keyboard_input to
        update stride parameters, then evaluates the gait trajectory for each leg
        with a half-period phase offset between diagonal pairs.

        Args:
            time_value: Current time in seconds (typically time.time()).
            keyboard_input: KB_CONTROL_OFFSET dict from the command queue.

        Returns:
            numpy array of shape (4, 4) — homogeneous foot targets [FL, FR, BL, BR].
        """
        front_foot_spacing = self.front_spacing
        rear_foot_spacing = self.rear_spacing

        if keyboard_input and all(v == 0.0 for k, v in keyboard_input.items() if k in ['IDstepLength', 'IDstepWidth', 'IDstepAlpha']):
            self.stride_length = 0.0
            self.stride_width = 0.0
            self.stride_angle = 0.0
        else:
            self.stride_length = keyboard_input.get('IDstepLength', 0.0)
            self.stride_width = keyboard_input.get('IDstepWidth', 0.0)
            self.stride_angle = keyboard_input.get('IDstepAlpha', 0.0)

        total_period = (self.phase_0_time + self.phase_1_time + self.phase_2_time + self.phase_3_time)

        if total_period == 0:
            return np.array([[0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1]])

        half_period = total_period / 2
        phase_offset = 0

        time_1 = (time_value * GAIT_TOTAL_TIME_CALC) % total_period
        time_2 = (time_value * GAIT_TOTAL_TIME_CALC - half_period) % total_period
        rear_time_1 = (time_value * GAIT_TOTAL_TIME_CALC - phase_offset) % total_period
        rear_time_2 = (time_value * GAIT_TOTAL_TIME_CALC - half_period - phase_offset) % total_period

        front_x_position = self.forward_offset
        rear_x_position = -1 * self.rear_offset
        front_y_position = ROBOT_BODY_HEIGHT
        rear_y_position = ROBOT_BODY_HEIGHT

        leg_positions = np.array([
            self.compute_leg_trajectory(time_1, front_x_position, front_y_position, front_foot_spacing),
            self.compute_leg_trajectory(time_2, front_x_position, front_y_position, -front_foot_spacing),
            self.compute_leg_trajectory(rear_time_2, rear_x_position, rear_y_position, rear_foot_spacing),
            self.compute_leg_trajectory(rear_time_1, rear_x_position, rear_y_position, -rear_foot_spacing)
        ])
        return leg_positions