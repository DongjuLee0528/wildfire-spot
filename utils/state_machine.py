"""
State machine for the wildfire detection robot.

Defines all possible robot states and manages valid state transitions
to ensure the robot operates in a predictable and safe manner.
"""

from enum import Enum
from utils.logger import WildfireLogger

class RobotState(Enum):
    """All possible states the wildfire robot can be in."""
    CALIBRATING = "CALIBRATING"      # Setting up patrol zone boundaries
    IDLE = "IDLE"                    # Waiting for commands
    PATROLLING = "PATROLLING"        # Actively monitoring patrol zone
    DETECTING = "DETECTING"          # Analyzing potential fire signals
    FIRE_DETECTED = "FIRE_DETECTED"  # Confirmed fire detection
    REPORTING = "REPORTING"          # Transmitting fire alert data
    RETURNING = "RETURNING"          # Returning to base/start position
    ERROR = "ERROR"                  # System error state

class StateMachine:
    """
    Manages robot state transitions with validation.

    Enforces valid state transitions to prevent invalid operations.
    For example, the robot cannot jump from IDLE directly to FIRE_DETECTED
    without first transitioning through PATROLLING and DETECTING states.
    """

    def __init__(self):
        """Initialize state machine in IDLE state with transition rules."""
        self._current_state = RobotState.IDLE
        try:
            self.logger = WildfireLogger("StateMachine")
        except Exception as e:
            print(f"Failed to initialize logger: {e}")
            self.logger = None

        # Define valid state transitions (from_state: [allowed_to_states])
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

    def get_state(self):
        """Get the current robot state."""
        return self._current_state

    def close(self):
        """Clean up logger resources."""
        if hasattr(self, 'logger') and self.logger is not None:
            self.logger.close()
