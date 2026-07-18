"""
Keyboard-based robot motion controller using multiprocessing.

Captures WASD/QE/Space key presses in a subprocess and translates them
into KB_CONTROL_OFFSET command dicts placed on a shared multiprocessing Queue.
The gait execution loop in main.py reads from this queue.

Key mappings:
  W / S    : forward / backward  (IDstepLength)
  A / D    : strafe left / right (IDstepWidth)
  Q / E    : yaw left / right    (IDstepAlpha)
  Space    : stop (reset all movement to zero)
"""

from utils.config import (KB_KEY_VALUES, KB_CONTROL_OFFSET, FORWARD_DISTANCE,
                         KB_X_STEP_DIVISOR, KB_Y_STEP, KB_YAW_STEP, KB_TEST_SLEEP_TIME)
import time
from queue import Empty
from multiprocessing import Process, Queue, Lock, Value

KEYBOARD_POLL_SLEEP = 0.02    # Seconds between keyboard polls (~50 Hz)
COMMAND_QUEUE_TIMEOUT = 0.2   # Seconds to block waiting for a command in monitor_commands


def _load_keyboard():
    try:
        import keyboard
    except ImportError as exc:
        raise RuntimeError("keyboard module is required to start keyboard listener") from exc
    return keyboard


class RobotKeyboardController:
    """
    Keyboard input handler for the Wildfire Spot robot.

    Maintains two single-element multiprocessing Queues:
      movement_data  — raw key press counts per key.
      robot_commands — KB_CONTROL_OFFSET dict consumed by the gait loop.

    start_listening() is intended to run inside a child Process.
    calculate_movement() translates accumulated key state into gait commands
    and is called from within the same child process on each poll cycle.
    """

    def __init__(self):
        self.movement_data = Queue()
        self.movement_data.put(KB_KEY_VALUES.copy())

        self.robot_commands = Queue()
        self.robot_commands.put(KB_CONTROL_OFFSET.copy())
        self.forward_step = FORWARD_DISTANCE / KB_X_STEP_DIVISOR
        self.lateral_step = KB_Y_STEP
        self.rotation_step = KB_YAW_STEP
        self.movement_lock = Lock()
        self.command_lock = Lock()
        self._running = Value('b', True)

    def reset_movement(self, movement_queue=None):
        """Clear all accumulated key press counts and set StartStepping to False."""
        movement_queue = movement_queue or self.movement_data
        with self.movement_lock:
            movement_queue.get()
            movement_queue.put(KB_KEY_VALUES.copy())

    def register_key(self, key_char, movement_queue=None):
        """Increment the press count for key_char and set the move flag to True."""
        movement_queue = movement_queue or self.movement_data
        with self.movement_lock:
            current_data = movement_queue.get()
            current_data[key_char] = current_data.get(key_char, 0) + 1
            current_data['move'] = True
            movement_queue.put(current_data)

    def calculate_movement(self, movement_queue=None, command_queue=None):
        """
        Translate current key press state into a KB_CONTROL_OFFSET command dict
        and replace the value in command_queue.

        W/S drive IDstepLength, A/D drive IDstepWidth, Q/E drive IDstepAlpha.
        StartStepping is True only while a directional key is held.
        """
        movement_queue = movement_queue or self.movement_data
        command_queue = command_queue or self.robot_commands
        with self.movement_lock:
            current_data = movement_queue.get()
            with self.command_lock:
                command_data = command_queue.get()
                command_data['IDstepLength'] = self.forward_step * current_data.get('s', 0) - self.forward_step * current_data.get('w', 0)
                command_data['IDstepWidth'] = self.lateral_step * current_data.get('d', 0) - self.lateral_step * current_data.get('a', 0)
                command_data['IDstepAlpha'] = self.rotation_step * current_data.get('q', 0) - self.rotation_step * current_data.get('e', 0)

                if current_data.get('move', False):
                    command_data['StartStepping'] = True
                else:
                    command_data['StartStepping'] = False

                command_queue.put(command_data)
            movement_queue.put(current_data)

    def stop(self):
        """Signal the listening loop to exit on its next poll iteration."""
        self._running.value = False

    def cleanup(self):
        """Close inter-process queues. Call after the listener process has terminated."""
        if hasattr(self, 'movement_data'):
            self.movement_data.close()
        if hasattr(self, 'robot_commands'):
            self.robot_commands.close()

    def start_listening(self, process_id, movement_queue, command_queue):
        """
        Poll the keyboard and update movement_queue and command_queue in a loop.

        Designed to run inside a child Process. Polls at KEYBOARD_POLL_SLEEP intervals
        and calls calculate_movement() on every iteration. On unhandled exception,
        drains command_queue and inserts a stop command before exiting.

        Args:
            process_id: Unused process identifier (reserved for future logging).
            movement_queue: Queue holding the current key press state dict.
            command_queue: Queue holding the KB_CONTROL_OFFSET command dict.
        """
        key_pressed = False

        try:
            keyboard = _load_keyboard()
            while self._running.value:
                if keyboard.is_pressed('w'):
                    if not key_pressed:
                        self.register_key('w', movement_queue)
                        key_pressed = True
                elif keyboard.is_pressed('a'):
                    if not key_pressed:
                        self.register_key('a', movement_queue)
                        key_pressed = True
                elif keyboard.is_pressed('s'):
                    if not key_pressed:
                        self.register_key('s', movement_queue)
                        key_pressed = True
                elif keyboard.is_pressed('d'):
                    if not key_pressed:
                        self.register_key('d', movement_queue)
                        key_pressed = True
                elif keyboard.is_pressed('q'):
                    if not key_pressed:
                        self.register_key('q', movement_queue)
                        key_pressed = True
                elif keyboard.is_pressed('e'):
                    if not key_pressed:
                        self.register_key('e', movement_queue)
                        key_pressed = True
                elif keyboard.is_pressed('space'):
                    if not key_pressed:
                        self.reset_movement(movement_queue)
                        key_pressed = True
                else:
                    key_pressed = False

                self.calculate_movement(movement_queue, command_queue)
                time.sleep(KEYBOARD_POLL_SLEEP)
        except Exception as exc:
            print(f"Keyboard listener error: {type(exc).__name__}: {exc}")
            self._running.value = False
            while True:
                try:
                    command_queue.get_nowait()
                except Empty:
                    break
            command_queue.put({
                'IDstepLength': 0.0,
                'IDstepWidth': 0.0,
                'IDstepAlpha': 0.0,
                'StartStepping': False,
                'stop_command': True,
            })

def monitor_commands(process_id, command_queue, running_flag):
    """
    Diagnostic loop that prints and re-enqueues command dicts from command_queue.

    Intended for standalone testing only (see __main__ block). Exits when a
    command dict contains 'stop_command': True or running_flag is cleared.

    Args:
        process_id: Unused identifier for the monitoring process.
        command_queue: Queue holding KB_CONTROL_OFFSET dicts.
        running_flag: multiprocessing.Value('b') controlling the loop.
    """
    while running_flag.value:
        try:
            command_data = command_queue.get(timeout=COMMAND_QUEUE_TIMEOUT)
        except Empty:
            continue
        print(command_data)
        if command_data.get('stop_command'):
            running_flag.value = False
            break
        command_queue.put(command_data)
        time.sleep(KB_TEST_SLEEP_TIME)

if __name__ == "__main__":
    controller = None
    keyboard_process = None
    running = Value('b', True)
    try:
        controller = RobotKeyboardController()
        keyboard_process = Process(target=controller.start_listening, args=(1, controller.movement_data, controller.robot_commands))

        keyboard_process.start()

        monitor_commands(2, controller.robot_commands, controller._running)
    except (RuntimeError, ImportError, OSError, KeyboardInterrupt) as e:
        print(f"Keyboard listener error: {type(e).__name__}: {e}")
        running.value = False
    finally:
        print("Done... ")
        running.value = False
        if keyboard_process is not None:
            keyboard_process.terminate()
            keyboard_process.join()
        if controller is not None:
            controller.cleanup()
