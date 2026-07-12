"""
State machine for the wildfire detection robot.

Defines all possible robot states and manages valid state transitions
to ensure the robot operates in a predictable and safe manner.
"""

from enum import Enum
from utils.logger import WildfireLogger


class RobotMode(Enum):
    """
    Operating mode that controls which input sources may issue movement commands.

    AUTO   — Autonomous patrol and detection; manual movement commands are blocked.
    MANUAL — Operator-driven control via web dashboard or keyboard; patrol logic pauses.
    """

    AUTO = "AUTO"
    MANUAL = "MANUAL"


class RobotState(Enum):
    """All possible states the wildfire robot can be in."""
    CALIBRATING = "CALIBRATING"      # Setting up patrol zone boundaries via GPS waypoints
    IDLE = "IDLE"                    # Waiting for commands; no active patrol
    PATROLLING = "PATROLLING"        # Actively traversing and monitoring the patrol zone
    DETECTING = "DETECTING"          # Analysing potential fire signals from sensors/camera
    FIRE_DETECTED = "FIRE_DETECTED"  # Confirmed fire — awaiting report transmission
    REPORTING = "REPORTING"          # Transmitting fire alert data to the Spring backend
    RETURNING = "RETURNING"          # Returning to base/start position after a mission
    ERROR = "ERROR"                  # Unrecoverable subsystem failure; only IDLE transition allowed

class StateMachine:
    """
    Manages robot state transitions with validation.

    Enforces valid state transitions to prevent invalid operations.
    For example, the robot cannot jump from IDLE directly to FIRE_DETECTED
    without first transitioning through PATROLLING and DETECTING states.
    """

    def __init__(self):
        """Initialize state machine in IDLE state with AUTO mode and transition rules."""
        self._current_state = RobotState.IDLE
        self._current_mode = RobotMode.AUTO
        try:
            self.logger = WildfireLogger("StateMachine")
        except Exception as e:
            print(f"Failed to initialize logger: {e}")
            self.logger = None

        # Valid state transitions map: each key state may only move to the listed states.
        # Any transition not listed here will be rejected by transition_to().
        #
        # Allowed transition graph:
        #   CALIBRATING -> IDLE
        #   IDLE        -> PATROLLING | CALIBRATING | ERROR
        #   PATROLLING  -> DETECTING  | IDLE        | ERROR
        #   DETECTING   -> FIRE_DETECTED | PATROLLING | ERROR
        #   FIRE_DETECTED -> REPORTING | ERROR
        #   REPORTING   -> RETURNING  | ERROR
        #   RETURNING   -> IDLE       | ERROR
        #   ERROR       -> IDLE
        self._valid_transitions = {
            RobotState.CALIBRATING: [RobotState.IDLE],
            RobotState.IDLE: [RobotState.PATROLLING, RobotState.CALIBRATING, RobotState.ERROR],
            RobotState.PATROLLING: [RobotState.DETECTING, RobotState.IDLE, RobotState.ERROR],
            RobotState.DETECTING: [RobotState.FIRE_DETECTED, RobotState.PATROLLING, RobotState.ERROR],
            RobotState.FIRE_DETECTED: [RobotState.REPORTING, RobotState.ERROR],
            RobotState.REPORTING: [RobotState.RETURNING, RobotState.ERROR],
            RobotState.RETURNING: [RobotState.IDLE, RobotState.ERROR],
            RobotState.ERROR: [RobotState.IDLE]
        }

        if self.logger is not None:
            self.logger.log_system_state(self._current_state.value)

    def can_transition(self, from_state, to_state):
        """
        Check if a state transition is valid.

        Args:
            from_state: Starting state
            to_state: Target state

        Returns:
            True if transition is allowed, False otherwise
        """
        if from_state not in self._valid_transitions:
            return False
        return to_state in self._valid_transitions[from_state]

    def transition_to(self, state):
        """
        Attempt to transition to a new state.

        Args:
            state: Target RobotState to transition to

        Returns:
            True if transition succeeded, False if invalid

        Validates the transition before executing it and logs the state change.
        """
        if not isinstance(state, RobotState):
            self.logger.log_error("StateMachine.transition_to", f"Invalid state type: {type(state)}")
            return False

        # Validate transition is allowed from current state
        if not self.can_transition(self._current_state, state):
            self.logger.log_error("StateMachine.transition_to",
                                 f"Invalid transition from {self._current_state.value} to {state.value}")
            return False

        # Execute transition and log it
        old_state = self._current_state
        self._current_state = state
        self.logger.log_system_state(f"{old_state.value} -> {state.value}")
        return True

    def set_mode(self, mode):
        """
        Switch the operating mode.

        Args:
            mode: RobotMode value to switch to.

        Returns:
            True if mode was accepted and set, False if the value is invalid.
        """
        if not isinstance(mode, RobotMode):
            if self.logger is not None:
                self.logger.log_error("StateMachine.set_mode", f"Invalid mode type: {mode!r}")
            return False
        self._current_mode = mode
        if self.logger is not None:
            self.logger.info(f"MODE | {mode.value}")
        return True

    def get_mode(self):
        """Return the current RobotMode."""
        return self._current_mode

    def get_state(self):
        """Return the current RobotState."""
        return self._current_state

    def close(self):
        """Release logger resources; call once on shutdown."""
        if hasattr(self, 'logger') and self.logger is not None:
            self.logger.close()
