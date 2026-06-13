from utils.config import *
import time
import keyboard
from multiprocessing import Process, Queue

class RobotKeyboardController:

    def __init__(self):
        self.movement_data = Queue()
        self.movement_data.put(KB_KEY_VALUES)

        self.robot_commands = Queue()
        self.robot_commands.put(KB_CONTROL_OFFSET)
        self.forward_step = FORWARD_DISTANCE / KB_X_STEP_DIVISOR
        self.lateral_step = KB_Y_STEP
        self.rotation_step = KB_YAW_STEP

    def reset_movement(self):
        current_data = self.movement_data.get()
        self.movement_data.put(KB_KEY_VALUES)

    def register_key(self, key_char):
        current_data = self.movement_data.get()
        current_data[key_char] += 1
        current_data['move'] = True
        self.movement_data.put(current_data)

    def calculate_movement(self):
        current_data = self.movement_data.get()
        command_data = self.robot_commands.get()
        command_data['IDstepLength'] = self.forward_step * current_data['s'] - self.forward_step * current_data['w']
        command_data['IDstepWidth'] = self.lateral_step * current_data['d'] - self.lateral_step * current_data['a']
        command_data['IDstepAlpha'] = self.rotation_step * current_data['q'] - self.rotation_step * current_data['e']

        if current_data['move']:
            command_data['StartStepping'] = True
        else:
            command_data['StartStepping'] = False

        self.movement_data.put(current_data)
        self.robot_commands.put(command_data)

    def start_listening(self, process_id, movement_queue, command_queue):
        key_pressed = False

        while True:
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
    try:
        controller = RobotKeyboardController()
        keyboard_process = Process(target=controller.start_listening, args=(1, controller.movement_data, controller.robot_commands))

        keyboard_process.start()

        monitor_commands(2, controller.robot_commands)
    except Exception as e:
        print(e)
    finally:
        print("Done... ")