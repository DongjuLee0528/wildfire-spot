from utils.config import *
import time
import keyboard
from multiprocessing import Process, Queue
key_value_default = {'w': 0, 'a': 0, 's': 0, 'd': 0, 'q': 0, 'e': 0, 'move': False }
control_offset = {'IDstepLength': 0.0, 'IDstepWidth': 0.0, 'IDstepAlpha': 0.0, 'StartStepping': False }

class KeyInterrupt():

    def __init__(self):
        self.key_status = Queue()
        self.key_status.put(key_value_default)

        self.command_status = Queue()
        self.command_status.put(control_offset)
        self.X_STEP = FORWARD_DISTANCE / 12.0
        self.Y_STEP = 5.0
        self.YAW_STEP = 3.0

    def resetStatus(self):
        result_dict = self.key_status.get()
        self.key_status.put(key_value_default)

    def keyCounter(self, character):
        result_dict = self.key_status.get()
        result_dict[character] += 1
        result_dict['move'] = True
        self.key_status.put(result_dict)

    def calcRbStep(self):
        result_dict = self.key_status.get()
        command_dict = self.command_status.get()
        command_dict['IDstepLength'] = self.X_STEP * result_dict['s'] - self.X_STEP * result_dict['w']
        command_dict['IDstepWidth'] = self.Y_STEP * result_dict['d'] - self.Y_STEP * result_dict['a']
        command_dict['IDstepAlpha'] = self.YAW_STEP * result_dict['q'] - self.YAW_STEP * result_dict['e']
        
        if result_dict['move']:
            command_dict['StartStepping'] = True
        else:
            command_dict['StartStepping'] = False

        self.key_status.put(result_dict)
        self.command_status.put(command_dict)

    def keyInterrupt(self, id, key_status, command_status):
        
        was_pressed = False

        while True:
            if keyboard.is_pressed('w'):
                if not was_pressed:
                    self.keyCounter('w')
                    was_pressed = True
            elif keyboard.is_pressed('a'):
                if not was_pressed:
                    self.keyCounter('a')
                    was_pressed = True
            elif keyboard.is_pressed('s'):
                if not was_pressed:
                    self.keyCounter('s')
                    was_pressed = True
            elif keyboard.is_pressed('d'):
                if not was_pressed:
                    self.keyCounter('d')
                    was_pressed = True
            elif keyboard.is_pressed('q'):
                if not was_pressed:
                    self.keyCounter('q')
                    was_pressed = True
            elif keyboard.is_pressed('e'):
                if not was_pressed:
                    self.keyCounter('e')
                    was_pressed = True
            elif keyboard.is_pressed('space'):
                if not was_pressed:
                    self.resetStatus()
                    was_pressed = True
            else:
                was_pressed = False

            self.calcRbStep()

def testWhile(id, command_status):
    while True:
        result_dict = command_status.get()
        print(result_dict)
        command_status.put(result_dict)
        time.sleep(1)
if __name__ == "__main__":
    try:
        KeyTest = KeyInterrupt()
        KeyProcess = Process(target=KeyTest.keyInterrupt, args=(1, KeyTest.key_status, KeyTest.command_status))

        KeyProcess.start()

        testWhile(2, KeyTest.command_status)
    except Exception as e:
        print(e)
    finally:
        print("Done... ")