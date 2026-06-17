from enum import Enum
from utils.logger import WildfireLogger

class RobotState(Enum):
    CALIBRATING = "CALIBRATING"
    IDLE = "IDLE"
    PATROLLING = "PATROLLING"
    DETECTING = "DETECTING"
    FIRE_DETECTED = "FIRE_DETECTED"
    REPORTING = "REPORTING"
    RETURNING = "RETURNING"
    ERROR = "ERROR"

class StateMachine:
    def __init__(self):
        self._current_state = RobotState.IDLE
        try:
            self.logger = WildfireLogger("StateMachine")
        except Exception as e:
            print(f"Failed to initialize logger: {e}")
            self.logger = None

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
        if from_state not in self._valid_transitions:
            return False
        return to_state in self._valid_transitions[from_state]

    def transition_to(self, state):
        if not isinstance(state, RobotState):
            self.logger.log_error("StateMachine.transition_to", f"Invalid state type: {type(state)}")
            return False

        if not self.can_transition(self._current_state, state):
            self.logger.log_error("StateMachine.transition_to",
                                 f"Invalid transition from {self._current_state.value} to {state.value}")
            return False

        old_state = self._current_state
        self._current_state = state
        self.logger.log_system_state(f"{old_state.value} -> {state.value}")
        return True

    def get_state(self):
        return self._current_state

    def close(self):
        if hasattr(self, 'logger') and self.logger is not None:
            self.logger.close()
