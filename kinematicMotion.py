"""
Kinematic Motion Module for Quadruped Gait Generation

This module implements motion control and gait generation for a quadruped robot.
It provides trotting gait patterns, individual leg motion control, and smooth
interpolation between foot positions.

Classes:
    KinematicLegMotion: Individual leg motion controller with interpolation
    KinematicMotion: Coordinator for all four leg motions
    TrottingGait: Trotting gait pattern generator with configurable parameters

Features:
    - Smooth motion interpolation between positions
    - Trotting gait implementation with diagonal leg coupling
    - Configurable step length, width, height, and timing
    - Real-time motion updates with error handling
    - Support for custom motion functions

Dependencies:
    - NumPy for matrix calculations
    - Time-based motion interpolation
    - Mathematical functions for trajectory generation
"""

from utils.config import *
import time
import numpy as np
import math
import logging

class KinematicLegMotion:
    """
    Individual leg motion controller with smooth interpolation.

    Manages smooth motion of a single leg from current position to target position
    over a specified time duration. Supports custom motion functions for trajectory
    modification during movement.

    Attributes:
        rtime (float): Reference time for motion calculations
        running (bool): Motion execution status
        LLp (np.ndarray): Current leg position [x, y, z, 1]
        startTime (float): Motion start timestamp
        startLLp (np.ndarray): Starting position for current motion
        targetLLp (np.ndarray): Target position for current motion
        endTime (float): Motion end timestamp
        func: Optional custom function for trajectory modification
    """

    def __init__(self, LLp):
        """
        Initialize leg motion controller.

        Args:
            LLp (np.ndarray): Initial leg position [x, y, z, 1]
        """
        self.rtime = time.time()
        self.running = False
        self.LLp = LLp

    def moveTo(self, newLLp, rtime, func=None):
        """
        Start motion to new leg position.

        Args:
            newLLp (np.ndarray): Target leg position [x, y, z, 1]
            rtime (float): Motion duration in milliseconds
            func: Optional function to modify trajectory during motion

        Returns:
            bool: True if motion started successfully, False if already moving
        """
        if self.running:
            print("Movement already running, please try again later.")
            return False

        # Initialize motion parameters
        self.startTime = time.time()
        self.startLLp = self.LLp
        self.func = func
        self.targetLLp = newLLp
        self.endTime = time.time() + rtime / 1000  # Convert milliseconds to seconds
        self.running = True
        return True
    
    def update(self):
        """
        Update leg position during motion using linear interpolation.

        Calculates current position based on elapsed time and applies custom
        function if provided. Handles motion completion and error cases.
        """
        # Calculate time progress
        diff = time.time() - self.startTime
        ldiff = self.targetLLp - self.startLLp
        tdiff = self.endTime - self.startTime

        # Calculate interpolation parameter (0 to 1)
        try:
            p = diff / tdiff  # Progress ratio
        except ZeroDivisionError:
            p = 1  # Complete motion if no duration

        # Check for motion completion
        if time.time() > self.endTime and self.running:
            self.running = False
            p = 1  # Ensure we reach exact target

        # Linear interpolation between start and target positions
        self.LLp = self.startLLp + ldiff * p

        # Apply custom function if provided
        if self.func:
            self.LLp = self.func(p, self.LLp)

    def step(self):
        """
        Execute one motion step and return current position.

        Returns:
            np.ndarray: Current leg position [x, y, z, 1]
        """
        if self.running:
            self.update()
        return self.LLp

class KinematicMotion:
    """
    Coordinator for all four leg motions in quadruped robot.

    Manages synchronized motion of all four legs with individual control
    capabilities. Provides unified interface for robot locomotion.

    Attributes:
        Lp (list): List of leg positions [4x4] for all legs
        legs (list): List of KinematicLegMotion objects for each leg
    """

    def __init__(self, Lp):
        """
        Initialize motion controller for all legs.

        Args:
            Lp (list): Initial positions for all four legs [4x[x,y,z,1]]
        """
        self.Lp = Lp
        # Create motion controller for each leg
        self.legs = [KinematicLegMotion(Lp[x]) for x in range(4)]

    def moveLegsTo(self, newLp, rtime):
        """
        Move all legs to new positions simultaneously.

        Args:
            newLp (list): Target positions for all legs [4x[x,y,z,1]]
            rtime (float): Motion duration in milliseconds
        """
        # Start motion for all legs simultaneously
        [self.legs[x].moveTo(newLp[x], rtime) for x in range(4)]

    def moveLegTo(self, leg, newLLp, rtime, func=None):
        """
        Move a specific leg to new position.

        Args:
            leg (int): Leg index (0-3)
            newLLp (np.ndarray): Target leg position [x, y, z, 1]
            rtime (float): Motion duration in milliseconds
            func: Optional trajectory modification function

        Returns:
            bool: True if motion started, False if leg already moving
        """
        return self.legs[leg].moveTo(newLLp, rtime, func)

    def step(self):
        """
        Execute motion step for all legs.

        Returns:
            list: Current positions of all legs [4x[x,y,z,1]]
        """
        return [x.step() for x in self.legs]


class TrottingGait:
    """
    Trotting gait pattern generator for quadruped locomotion.

    Implements a four-phase trotting gait where diagonal leg pairs move together.
    Provides configurable step parameters including length, width, height, and timing.
    Each gait cycle consists of stance and swing phases with smooth transitions.

    Gait Phases:
        t0: Pre-stance phase (preparation)
        t1: Stance phase (foot on ground, body moves forward)
        t2: Post-stance phase (weight transition)
        t3: Swing phase (foot in air, returns to start)

    Attributes:
        step_gain: Step size multiplier
        maxSl: Maximum step length
        bodyPos: Robot body position offset
        bodyRot: Robot body rotation offset
        t0, t1, t2, t3: Timing for each gait phase
        Sl: Current step length
        Sw: Current step width
        Sh: Step height (lift during swing)
        Sa: Step angle (turning component)
        Spf: Front foot position offset
        Spr: Rear foot position offset
        Fo: Forward distance reference
        Ro: Backward distance reference
        Rc: Rotation coefficient
    """

    def __init__(self):
        """Initialize trotting gait with default parameters from config."""
        # Gait scaling and limits
        self.step_gain = GAIT_STEP_GAIN
        self.maxSl = GAIT_MAX_SL

        # Body pose parameters
        self.bodyPos = GAIT_BODY_POS
        self.bodyRot = GAIT_BODY_ROT

        # Gait timing phases (t0: pre-stance, t1: stance, t2: post-stance, t3: swing)
        self.t0 = GAIT_TIMING[0]
        self.t1 = GAIT_TIMING[1]
        self.t2 = GAIT_TIMING[2]
        self.t3 = GAIT_TIMING[3]

        # Step parameters
        self.Sl = GAIT_INITIAL_VALUES[0]  # Step length
        self.Sw = GAIT_INITIAL_VALUES[1]  # Step width
        self.Sh = STEP_HEIGHT             # Step height
        self.Sa = GAIT_INITIAL_VALUES[2]  # Step angle

        # Foot position offsets
        self.Spf = GAIT_FOOT_POSITIONS[0] # Front feet offset
        self.Spr = GAIT_FOOT_POSITIONS[1] # Rear feet offset

        # Distance references
        self.Fo = FORWARD_DISTANCE        # Forward body position
        self.Ro = abs(BACKWARD_DISTANCE)  # Backward body position

        self.Rc = GAIT_RC
    def calcLeg(self, t, x, y, z):
        """
        Calculate leg position for given time in gait cycle.

        Implements four-phase gait cycle with smooth transitions between phases.
        Handles stance phase (foot on ground) and swing phase (foot in air) with
        rotation and height modulation.

        Args:
            t (float): Time within current gait cycle
            x (float): Base X position for leg
            y (float): Base Y position for leg
            z (float): Base Z position for leg

        Returns:
            np.ndarray: Calculated foot position [x, y, z, 1]
        """
        # Define start and end positions for this gait cycle
        startLp = np.array([x - self.Sl/2.0, y, z - self.Sw, 1])
        endY = GAIT_END_Y
        endLp = np.array([x + self.Sl/2, y + endY, z + self.Sw, 1])

        # Phase 0: Pre-stance (static at start position)
        if t < self.t0:
            return startLp

        # Phase 1: Stance phase (foot on ground, body moves)
        elif t < self.t0 + self.t1:
            td = t - self.t0  # Time within this phase
            try:
                tp = td / self.t1  # Progress ratio (0 to 1)
            except ZeroDivisionError:
                tp = 0

            # Linear interpolation between start and end positions
            diffLp = endLp - startLp
            curLp = startLp + diffLp * tp

            # Apply rotation for turning (yaw rotation around Y-axis)
            try:
                psi = -((math.pi/MATH_PI_DIVISOR*self.Sa)/2) + (math.pi/MATH_PI_DIVISOR*self.Sa)*tp
            except (ZeroDivisionError, ValueError):
                psi = 0

            try:
                # Y-axis rotation matrix for turning
                Ry = np.array([[np.cos(psi), 0, np.sin(psi), 0],
                              [0, 1, 0, 0],
                              [-np.sin(psi), 0, np.cos(psi), 0],
                              [0, 0, 0, 1]])
            except (ValueError, OverflowError):
                # Identity matrix fallback
                Ry = np.array([[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])

            try:
                curLp = Ry.dot(curLp)
            except (ValueError, np.linalg.LinAlgError):
                logging.warning('Matrix operation failed, using original position')
                curLp = startLp
            return curLp

        # Phase 2: Post-stance (static at end position)
        elif t < self.t0 + self.t1 + self.t2:
            return endLp

        # Phase 3: Swing phase (foot lifted, returns to start)
        elif t < self.t0 + self.t1 + self.t2 + self.t3:
            td = t - (self.t0 + self.t1 + self.t2)  # Time within swing phase
            try:
                tp = td / self.t3  # Progress ratio (0 to 1)
            except ZeroDivisionError:
                tp = 0

            # Linear interpolation back to start position
            diffLp = startLp - endLp
            curLp = endLp + diffLp * tp

            # Add sinusoidal height variation during swing
            try:
                curLp[1] += self.Sh * math.sin(math.pi * tp)  # Peak at tp=0.5
            except (ValueError, OverflowError, IndexError):
                pass
            return curLp
            
    def stepLength(self, len):
        """
        Set step length for gait.

        Args:
            len (float): Desired step length
        """
        self.Sl = len

    def positions(self, t, kb_offset={}):
        """
        Calculate foot positions for all four legs at given time.

        Implements trotting gait where diagonal leg pairs move in opposition.
        Front legs and rear legs are phase-shifted by half cycle for stability.
        Supports keyboard/joystick input for dynamic gait parameter adjustment.

        Args:
            t (float): Current time for gait calculation
            kb_offset (dict): Optional keyboard/joystick offsets:
                - 'IDstepLength': Step length adjustment
                - 'IDstepWidth': Step width adjustment
                - 'IDstepAlpha': Step angle adjustment

        Returns:
            np.ndarray: Foot positions for all legs [4x4]
                Order: [front_left, front_right, rear_left, rear_right]
        """
        spf = self.Spf  # Front foot position offset
        spr = self.Spr  # Rear foot position offset

        # Handle input from keyboard/joystick
        if list(kb_offset.values()) == [0.0, 0.0, 0.0]:
            # Static pose when no input
            self.Sl = 0.0
            self.Sw = 0.0
            self.Sa = 0.0
        else:
            # Dynamic gait parameters from input
            self.Sl = kb_offset['IDstepLength']
            self.Sw = kb_offset['IDstepWidth']
            self.Sa = kb_offset['IDstepAlpha']

        # Calculate gait timing
        Tt = (self.t0 + self.t1 + self.t2 + self.t3)  # Total cycle time
        Tt2 = Tt / 2  # Half cycle for phase offset
        rd = 0  # Rear delay (currently unused)

        # Calculate phase times for each leg pair
        td = (t * GAIT_TOTAL_TIME_CALC) % Tt      # Front left time
        t2 = (t * GAIT_TOTAL_TIME_CALC - Tt2) % Tt  # Front right time (half cycle offset)
        rtd = (t * GAIT_TOTAL_TIME_CALC - rd) % Tt  # Rear left time
        rt2 = (t * GAIT_TOTAL_TIME_CALC - Tt2 - rd) % Tt  # Rear right time

        # Body positions for front and rear legs
        Fx = self.Fo     # Front body X position
        Rx = -1 * self.Ro # Rear body X position (negative for behind center)
        Fy = ROBOT_BODY_HEIGHT  # Front leg Y height
        Ry = ROBOT_BODY_HEIGHT  # Rear leg Y height

        # Calculate positions for all four legs
        # Diagonal pairs move together: (FL,RR) and (FR,RL)
        r = np.array([
            self.calcLeg(td, Fx, Fy, spf),    # Front left
            self.calcLeg(t2, Fx, Fy, -spf),   # Front right (opposite side)
            self.calcLeg(rt2, Rx, Ry, spr),   # Rear left (phase shifted)
            self.calcLeg(rtd, Rx, Ry, -spr)   # Rear right (diagonal to FL)
        ])
        return r
