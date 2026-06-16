from utils.config import *

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_sht31d
import Jetson.GPIO as GPIO
import busio
import board
import time

class SensorManager:
    def __init__(self):
        self._available = True

        try:
            self._i2c = busio.I2C(I2C_SCL, I2C_SDA)
        except:
            print("I2C initialization failed")
            self._available = False
            return

        try:
            self._ads1_1 = ADS.ADS1115(self._i2c, address=ADS1115_MQ2_1)
            self._ads1_2 = ADS.ADS1115(self._i2c, address=ADS1115_MQ2_2)
            self._mq2_chan1 = AnalogIn(self._ads1_1, ADS.P0)
            self._mq2_chan2 = AnalogIn(self._ads1_2, ADS.P0)
        except:
            print("ADS1115 initialization failed")
            self._available = False

        try:
            self._sht31 = adafruit_sht31d.SHT31D(self._i2c, address=SHT31_ADDRESS)
        except:
            print("SHT31 initialization failed")
            self._available = False

        GPIO.setmode(GPIO.BOARD)

        self._ky026_pins = [KY026_PIN_1, KY026_PIN_2, KY026_PIN_3, KY026_PIN_4]
        for pin in self._ky026_pins:
            if pin is not None:
                GPIO.setup(pin, GPIO.IN)

        if HCSR04_TRIGGER_PIN is not None and HCSR04_ECHO_PIN is not None:
            GPIO.setup(HCSR04_TRIGGER_PIN, GPIO.OUT)
            GPIO.setup(HCSR04_ECHO_PIN, GPIO.IN)

    def read_mq2(self):
        if not self._available:
            return 0
        try:
            value1 = self._mq2_chan1.value
            value2 = self._mq2_chan2.value
            return int((value1 + value2) / 2)
        except:
            return 0

    def read_sht31(self):
        if not self._available:
            return (0.0, 0.0)
        try:
            temperature = self._sht31.temperature
            humidity = self._sht31.relative_humidity
            return (temperature, humidity)
        except:
            return (0.0, 0.0)

    def read_ky026(self):
        flame_detected = []
        for pin in self._ky026_pins:
            if pin is not None:
                flame_detected.append(not GPIO.input(pin))
            else:
                flame_detected.append(False)
        return flame_detected

    def read_hcsr04(self):
        if HCSR04_TRIGGER_PIN is None or HCSR04_ECHO_PIN is None:
            return 0.0

        GPIO.output(HCSR04_TRIGGER_PIN, GPIO.LOW)
        time.sleep(0.000002)
        GPIO.output(HCSR04_TRIGGER_PIN, GPIO.HIGH)
        time.sleep(0.00001)
        GPIO.output(HCSR04_TRIGGER_PIN, GPIO.LOW)

        pulse_start = time.time()
        while GPIO.input(HCSR04_ECHO_PIN) == 0:
            pulse_start = time.time()

        pulse_end = time.time()
        while GPIO.input(HCSR04_ECHO_PIN) == 1:
            pulse_end = time.time()

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150

        return round(distance, 2)

    def read_all(self):
        smoke = self.read_mq2()
        temperature, humidity = self.read_sht31()
        flame = self.read_ky026()
        distance = self.read_hcsr04()

        return {
            "smoke": smoke,
            "temperature": temperature,
            "humidity": humidity,
            "flame": flame,
            "distance": distance
        }