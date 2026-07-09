"""
Manual control command layer for web-based robot control.

Translates high-level directional commands into the KB_CONTROL_OFFSET
dict format consumed by monitor_commands() and the existing keyboard
control pipeline. Acts as a parallel input source alongside keyboard
control; does not replace or modify the keyboard path.
"""

from queue import Empty
from utils.config import (
    KB_CONTROL_OFFSET,
    FORWARD_DISTANCE,
    KB_X_STEP_DIVISOR,
    KB_Y_STEP,
    KB_YAW_STEP,
)
from utils.logger import WildfireLogger

VALID_COMMANDS = {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP", "RESET"}
_SAFE_COMMANDS = {"STOP", "RESET"}

_FORWARD_STEP = FORWARD_DISTANCE / KB_X_STEP_DIVISOR
_LATERAL_STEP = KB_Y_STEP
_ROTATION_STEP = KB_YAW_STEP

_COMMAND_MAP = {
    "FORWARD":  {"IDstepLength": -_FORWARD_STEP,  "IDstepWidth": 0.0,            "IDstepAlpha": 0.0,            "StartStepping": True},
    "BACKWARD": {"IDstepLength":  _FORWARD_STEP,  "IDstepWidth": 0.0,            "IDstepAlpha": 0.0,            "StartStepping": True},
    "LEFT":     {"IDstepLength": 0.0,             "IDstepWidth": -_LATERAL_STEP, "IDstepAlpha": 0.0,            "StartStepping": True},
    "RIGHT":    {"IDstepLength": 0.0,             "IDstepWidth":  _LATERAL_STEP, "IDstepAlpha": 0.0,            "StartStepping": True},
    "STOP":     {"IDstepLength": 0.0,             "IDstepWidth": 0.0,            "IDstepAlpha": 0.0,            "StartStepping": False},
    "RESET":    {"IDstepLength": 0.0,             "IDstepWidth": 0.0,            "IDstepAlpha": 0.0,            "StartStepping": False},
}


class ManualControlManager:
    """
    Accepts high-level directional commands and pushes them into the
    robot command queue shared with the keyboard control pipeline.

    The command queue must hold exactly one dict at a time following the
    KB_CONTROL_OFFSET schema. This manager drains the current value,
    replaces it with the translated command dict, and re-inserts it so
    monitor_commands() picks it up on its next read.
    """

    def __init__(self, command_queue=None, mode_manager=None, movement_available=False):
        """
        Initialise the manual control manager.

        Args:
            command_queue: multiprocessing.Queue holding KB_CONTROL_OFFSET
                dicts — specifically RobotKeyboardController.robot_commands,
                which is consumed by the gait execution loop running in a
                daemon thread. Pass None only when no movement loop is running;
                commands will be rejected with reason
                'movement_loop_unavailable' instead of silently pretending
                to succeed.
            mode_manager: Optional ModeControlManager instance. When provided,
                non-safe commands are blocked unless the mode is MANUAL.
                STOP and RESET are always forwarded regardless of mode.
            movement_available: Set True only after the gait execution loop
                (QuadrupedGaitPattern → DHParameterSolver → QuadrupedServoManager)
                has started successfully. Non-safe movement commands are rejected
                with reason 'movement_loop_unavailable' when False.
        """
        self.logger = WildfireLogger("ManualControlManager")
        self._command_queue = command_queue
        self._mode_manager = mode_manager
        self._movement_available = movement_available
        self._current_command = "STOP"

    def send_command(self, command):
        """
        Validate and dispatch a high-level command.

        Args:
            command: String command name. Must be one of VALID_COMMANDS.

        Returns:
            dict with keys:
            - accepted (bool)
            - command (str): the submitted command
            - reason (str): 'ok', 'invalid_command', 'wrong_mode',
                            or 'movement_loop_unavailable'
        """
        command_upper = str(command).upper() if command is not None else ""

        if command_upper not in VALID_COMMANDS:
            self.logger.log_error(
                "ManualControlManager.send_command",
                f"Rejected unknown command: {command!r}",
            )
            return {"accepted": False, "command": str(command), "reason": "invalid_command"}

        if self._mode_manager is not None and command_upper not in _SAFE_COMMANDS:
            if not self._mode_manager.is_manual():
                self.logger.log_error(
                    "ManualControlManager.send_command",
                    f"Command {command_upper} blocked: mode is {self._mode_manager.get_current_mode()}",
                )
                return {"accepted": False, "command": command_upper, "reason": "wrong_mode"}

        if command_upper not in _SAFE_COMMANDS and not self._movement_available:
            self.logger.log_error(
                "ManualControlManager.send_command",
                f"Command {command_upper} rejected: gait/servo loop is not running",
            )
            return {"accepted": False, "command": command_upper, "reason": "movement_loop_unavailable"}

        if self._command_queue is None:
            self.logger.log_error(
                "ManualControlManager.send_command",
                f"Command {command_upper} rejected: no movement loop attached to this runtime",
            )
            return {"accepted": False, "command": command_upper, "reason": "movement_loop_unavailable"}

        payload = dict(_COMMAND_MAP[command_upper])

        try:
            try:
                self._command_queue.get_nowait()
            except Empty:
                pass
            self._command_queue.put(payload)
            self._current_command = command_upper
            self.logger.info(f"MANUAL_CTRL | command={command_upper}")
            return {"accepted": True, "command": command_upper, "reason": "ok"}
        except Exception as e:
            self.logger.log_error("ManualControlManager.send_command", str(e))
            return {"accepted": False, "command": command_upper, "reason": "movement_loop_unavailable"}

    def move_forward(self):
        """Send FORWARD command."""
        return self.send_command("FORWARD")

    def move_backward(self):
        """Send BACKWARD command."""
        return self.send_command("BACKWARD")

    def turn_left(self):
        """Send LEFT command."""
        return self.send_command("LEFT")

    def turn_right(self):
        """Send RIGHT command."""
        return self.send_command("RIGHT")

    def stop(self):
        """Send STOP command."""
        return self.send_command("STOP")

    def reset(self):
        """Send RESET command."""
        return self.send_command("RESET")

    def set_movement_available(self, available):
        """
        Update the gait loop availability flag at runtime.

        Args:
            available: True if the gait execution loop started successfully
                and servo hardware is ready; False otherwise.
        """
        self._movement_available = bool(available)
        self.logger.info(f"MANUAL_CTRL | movement_available={self._movement_available}")

    def get_current_command(self):
        """
        Return the most recently accepted command name.

        Returns:
            str: Last accepted command, or 'STOP' if no command has been
            accepted yet.
        """
        return self._current_command
