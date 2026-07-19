"""
Interactive per-servo offset calibration tool using adafruit PCA9685 directly.

Connects to the PCA9685 at address 0x40 on I2C bus 0 (SCL_1/SDA_1, pins 28/27)
and initialises servo objects with min_pulse=460, max_pulse=2440.

Prompts for a servo index and target angle, sweeping from the previous position
at 1-degree increments with a 10 ms delay per step.

Expand val_list to [90]*12 to calibrate all 12 channels.
Run on Jetson hardware only; requires adafruit_pca9685 and adafruit_motor.
"""

import time

# I2C bus selection: Bus 0 uses pins 28 (SCL_1) and 27 (SDA_1) on the Jetson
# Channel layout: [0-2]=FL, [3-5]=FR, [6-8]=RL, [9-11]=RR
val_list = [90, 90]   # Extend to [90]*12 for all 12 servos


def main():
    """
    Interactively calibrate servo offset angles via direct PCA9685 control.

    On each iteration the user selects a servo index (0 to len(val_list)-1)
    and a target angle (0-180). The servo sweeps from its previous angle to
    the target one degree at a time with a 10 ms delay per step.
    Uncomment the second PCA9685 block to include the rear board (0x41).
    """
    from adafruit_pca9685 import PCA9685
    from adafruit_motor import servo
    import board
    import busio

    print("Initializing Servos")
    i2c_bus0=(busio.I2C(board.SCL_1, board.SDA_1))
    print("Initializing ServoKit")

    pca = list()
    pca.append(PCA9685(i2c_bus0, address=0x40))  # Front board
    pca[-1].frequency = 60
    # pca.append(PCA9685(i2c_bus0, address=0x41))  # Rear board (uncomment to enable)
    # pca[-1].frequency = 60

    # pca[0] drives servos 0-5 (front board); pca[1] would drive servos 6-11 (rear board)
    print("Done initializing")

    servos = list()
    for i in range(len(val_list)):
        servos.append(servo.Servo(pca[int(i/6)].channels[int(i%6)], min_pulse=460, max_pulse=2440))
        # servos.append(servo.Servo(pca[int(i/6)].channels[int(i%6)], min_pulse=771, max_pulse=2740))

    for i in range(len(val_list)):
        servos[i].angle = val_list[i]

    while True:
        # num is index of motor to rotate
        num=int(input(f"Enter Servo to rotate (0-{len(servos) - 1}): "))
        if num < 0 or num >= len(servos):
            print(f"Invalid servo number: {num}")
            continue
        
        # new angle to be written on selected motor
        angle=int(input("Enter new angles (0-180): "))
        prev_angle = val_list[num]
        
        # increase(decrease) prev_angle to angle by 1 degree
        sweep = range(prev_angle, angle, 1) if (prev_angle < angle) else range(prev_angle, angle, -1)
        for degree in sweep:
            servos[num].angle=degree
            time.sleep(0.01)

        val_list[num] = angle


if __name__ == '__main__':
    main()
