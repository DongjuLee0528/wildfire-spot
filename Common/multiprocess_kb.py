from utils.config import (KB_KEY_VALUES, KB_CONTROL_OFFSET, FORWARD_DISTANCE,
                         KB_X_STEP_DIVISOR, KB_Y_STEP, KB_YAW_STEP, KB_TEST_SLEEP_TIME)
import time
import keyboard
from multiprocessing import Process, Queue, Lock

class RobotKeyboardController:

    def __init__(self):
        self.movement_data = Queue()
        self.movement_data.put(KB_KEY_VALUES)

        self.robot_commands = Queue()
        self.robot_commands.put(KB_CONTROL_OFFSET)
        self.forward_step = FORWARD_DISTANCE / KB_X_STEP_DIVISOR
        self.lateral_step = KB_Y_STEP
        self.rotation_step = KB_YAW_STEP
        self.movement_lock = Lock()
        self.command_lock = Lock()
        self._running = True

    def reset_movement(self):
        with self.movement_lock:
            current_data = self.movement_data.get()
            self.movement_data.put(KB_KEY_VALUES)

    def register_key(self, key_char):
        with self.movement_lock:
            current_data = self.movement_data.get()
            current_data[key_char] = current_data.get(key_char, 0) + 1
            current_data['move'] = True
            self.movement_data.put(current_data)

    def calculate_movement(self):
        with self.movement_lock:
            current_data = self.movement_data.get()
            with self.command_lock:
                command_data = self.robot_commands.get()
                command_data['IDstepLength'] = self.forward_step * current_data.get('s', 0) - self.forward_step * current_data.get('w', 0)
                command_data['IDstepWidth'] = self.lateral_step * current_data.get('d', 0) - self.lateral_step * current_data.get('a', 0)
                command_data['IDstepAlpha'] = self.rotation_step * current_data.get('q', 0) - self.rotation_step * current_data.get('e', 0)

                if current_data.get('move', False):
                    command_data['StartStepping'] = True
                else:
                    command_data['StartStepping'] = False

                self.robot_commands.put(command_data)
            self.movement_data.put(current_data)

    def stop(self):
        self._running = False

    def cleanup(self):
        if hasattr(self, 'movement_data'):
            self.movement_data.close()
        if hasattr(self, 'robot_commands'):
            self.robot_commands.close()

    def start_listening(self, process_id, movement_queue, command_queue):
        key_pressed = False

        while self._running:
            if keyboard.is_pressed('w'):
                if not key_pressed:
                    self.register_key('w')
                    key_pressed = True
            elif keyboard.is_pressed('a'):
                if not key_pressed:
                    self.register_key('a')
                    key_pressed = True
            elif keyboard.is_pressed('s'):
                if not key_pressed:
                    self.register_key('s')
                    key_pressed = True
            elif keyboard.is_pressed('d'):
                if not key_pressed:
                    self.register_key('d')
                    key_pressed = True
            elif keyboard.is_pressed('q'):
                if not key_pressed:
                    self.register_key('q')
                    key_pressed = True
            elif keyboard.is_pressed('e'):
                if not key_pressed:
                    self.register_key('e')
                    key_pressed = True
            elif keyboard.is_pressed('space'):
                if not key_pressed:
                    self.reset_movement()
                    key_pressed = True
            else:
                key_pressed = False

            self.calculate_movement()

def monitor_commands(process_id, command_queue):
    while True:
        command_data = command_queue.get()
        print(command_data)
        command_queue.put(command_data)
        time.sleep(KB_TEST_SLEEP_TIME)

if __name__ == "__main__":
    controller = None
    keyboard_process = None
    try:
        controller = RobotKeyboardController()
        keyboard_process = Process(target=controller.start_listening, args=(1, controller.movement_data, controller.robot_commands))

        keyboard_process.start()

        monitor_commands(2, controller.robot_commands)
    except (ImportError, OSError, KeyboardInterrupt):
        print("Exception occurred")
    finally:
        print("Done... ")
        if keyboard_process is not None:
            keyboard_process.terminate()
            keyboard_process.join()
        if controller is not None:
            controller.cleanup()

