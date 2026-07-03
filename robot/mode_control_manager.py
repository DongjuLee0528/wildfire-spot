"""
Operating mode control layer for AUTO / MANUAL switching.

Wraps StateMachine.set_mode() / get_mode() behind a structured API so
that higher-level components (API server, web dashboard) never mutate
mode state directly. StateMachine remains the single source of truth.
"""

from utils.state_machine import RobotMode, StateMachine
from utils.logger import WildfireLogger

VALID_MODES = {"AUTO", "MANUAL"}

_MODE_MAP = {
    "AUTO": RobotMode.AUTO,
    "MANUAL": RobotMode.MANUAL,
}


class ModeControlManager:
    """
    Accepts high-level mode strings and delegates to StateMachine.set_mode().

    Provides convenience helpers so callers never import RobotMode directly.
    """

    def __init__(self, state_machine: StateMachine):
        """
        Initialise the mode control manager.

        Args:
            state_machine: The shared StateMachine instance that owns mode state.
        """
        self.logger = WildfireLogger("ModeControlManager")
        self._sm = state_machine

    def set_mode(self, mode):
        """
        Switch the operating mode.

        Args:
            mode: String 'AUTO' or 'MANUAL' (case-insensitive).

        Returns:
            dict with keys:
            - accepted (bool)
            - mode (str): normalised mode name submitted
            - reason (str): 'ok' or 'invalid_mode'
        """
        mode_upper = str(mode).upper() if mode is not None else ""

        if mode_upper not in VALID_MODES:
            self.logger.log_error(
                "ModeControlManager.set_mode",
                f"Rejected unknown mode: {mode!r}",
            )
            return {"accepted": False, "mode": str(mode), "reason": "invalid_mode"}

        if self._sm is None:
            self.logger.log_error(
                "ModeControlManager.set_mode",
                "StateMachine is unavailable",
            )
            return {"accepted": False, "mode": mode_upper, "reason": "state_machine_unavailable"}

        try:
            success = self._sm.set_mode(_MODE_MAP[mode_upper])
        except Exception as e:
            self.logger.log_error(
                "ModeControlManager.set_mode",
                f"StateMachine.set_mode raised: {e}",
            )
            return {"accepted": False, "mode": mode_upper, "reason": "state_machine_error"}

        if not success:
            return {"accepted": False, "mode": mode_upper, "reason": "invalid_mode"}

        self.logger.info(f"MODE_CTRL | mode={mode_upper}")
        return {"accepted": True, "mode": mode_upper, "reason": "ok"}

    def switch_to_auto(self):
        """Switch to AUTO mode."""
        return self.set_mode("AUTO")

    def switch_to_manual(self):
        """Switch to MANUAL mode."""
        return self.set_mode("MANUAL")

    def get_current_mode(self):
        """
        Return the current mode as a string.

        Returns:
            'AUTO' or 'MANUAL'.
        """
        return self._sm.get_mode().value

    def is_auto(self):
        """Return True if current mode is AUTO."""
        return self._sm.get_mode() is RobotMode.AUTO

    def is_manual(self):
        """Return True if current mode is MANUAL."""
        return self._sm.get_mode() is RobotMode.MANUAL
