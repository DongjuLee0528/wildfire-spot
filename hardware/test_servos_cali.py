"""
Interactive servo calibration tool using adafruit_servokit.

Connects to two PCA9685 boards via I2C bus 0 (SCL_1/SDA_1, pins 28/27):
  kit  (address 0x40) — channels 0-5, selected when motor_num < 6
  kit2 (address 0x41) — channels 0-5, selected when motor_num >= 6

Prompts for a servo index and target angle, then sweeps from the last
known angle to the new angle at 1-degree steps to avoid sudden jumps.

Expand val_list to [90]*12 to calibrate the full 12-servo robot.
Run on Jetson hardware only; requires adafruit_servokit.
"""

import time

# I2C bus selection: Bus 0 uses pins 28 (SCL_1) and 27 (SDA_1) on the Jetson
# Channel layout: [0-2]=FL, [3-5]=FR, [6-8]=RL, [9-11]=RR
val_list = [90]   # Extend to [90]*12 for all 12 servos
prev_angle = None
cur_angle = None


def main():
    """
    Interactively calibrate servo positions via ServoKit.

    On each iteration the user selects a servo index (0 to len(val_list)-1)
    and a target angle (0-180). The servo sweeps from its previous angle to
    the target one degree at a time with a 10 ms delay per step.
    """
    from adafruit_servokit import ServoKit
    import board
    import busio

    print("Initializing Servos")
    i2c_bus0=(busio.I2C(board.SCL_1, board.SDA_1))
    print("Initializing ServoKit")

    # kit  controls servos 0-5  (address 0x40)
    # kit2 controls servos 6-11 (address 0x41)
    kit = ServoKit(channels=16, i2c=i2c_bus0, address=0x40)
    kit2 = ServoKit(channels=16, i2c=i2c_bus0, address=0x41)

    print("Done initializing")

    global prev_angle, cur_angle

    while True:
        # motor_num is index of motor to rotate
        motor_num=int(input(f"Enter Servo to rotate (0-{len(val_list) - 1}): "))
        if motor_num < 0 or motor_num >= len(val_list):
            print(f"Invalid servo number: {motor_num}")
            continue
        
        # new angle to be written on selected motor
        cur_angle=int(input("Enter new angles (0-180): "))
        
        # increase(decrease) prev_angle to angle by 1 degree
        if prev_angle:
            sweep = range(prev_angle, cur_angle, 1) if (prev_angle < cur_angle) else range(prev_angle, cur_angle, -1)

            for degree in sweep:
                if motor_num < 6:
                    kit.servo[int(motor_num%6)].angle = cur_angle
                else:
                    kit2.servo[int(motor_num%6)].angle = cur_angle
                time.sleep(0.01)
        else:
            if motor_num < 6:
                kit.servo[int(motor_num%6)].angle = cur_angle
            else:
                kit2.servo[int(motor_num%6)].angle = cur_angle


        prev_angle = val_list[motor_num]


if __name__ == '__main__':
    main()
