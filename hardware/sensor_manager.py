"""
Sensor Manager Module for Environmental Monitoring

This module manages various environmental sensors for wildfire detection including:
- MQ2 gas/smoke sensors via ADS1115 ADC
- SHT31 temperature and humidity sensor
- KY026 flame detection sensors
- HC-SR04 ultrasonic distance sensor

Classes:
    SensorManager: Unified interface for all environmental sensors

Dependencies:
    - Adafruit CircuitPython libraries for I2C sensors
    - Jetson.GPIO for digital sensors
    - I2C communication for ADC and environmental sensors
"""

from utils.config import *

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_sht31d
import Jetson.GPIO as GPIO
import busio
import board
import time

class SensorManager:
    """
    Unified sensor management class for environmental monitoring.

    Manages multiple sensors for wildfire detection including gas/smoke detection,
    environmental monitoring, flame detection, and distance measurement.

    Attributes:
        _available (bool): Overall sensor availability status
        _i2c: I2C bus for sensor communication
        _ads1_1, _ads1_2: ADS1115 ADC objects for MQ2 sensors
        _mq2_chan1, _mq2_chan2: Analog input channels for smoke sensors
        _sht31: SHT31D temperature/humidity sensor object
        _ky026_pins: GPIO pins for flame detection sensors
    """

    def __init__(self):
        """Initialize all environmental sensors and configure GPIO pins."""
        self._available = True

        # Initialize I2C communication bus
        try:
            self._i2c = busio.I2C(I2C_SCL, I2C_SDA)
        except:
            print("I2C initialization failed")
            self._available = False
            return

        # Initialize MQ2 smoke sensors via ADS1115 ADCs
        try:
            self._ads1_1 = ADS.ADS1115(self._i2c, address=ADS1115_MQ2_1)
            self._ads1_2 = ADS.ADS1115(self._i2c, address=ADS1115_MQ2_2)
            self._mq2_chan1 = AnalogIn(self._ads1_1, ADS.P0)
            self._mq2_chan2 = AnalogIn(self._ads1_2, ADS.P0)
        except:
            print("ADS1115 initialization failed")
            self._available = False

        # Initialize SHT31 temperature and humidity sensor
        try:
            self._sht31 = adafruit_sht31d.SHT31D(self._i2c, address=SHT31_ADDRESS)
        except:
            print("SHT31 initialization failed")
            self._available = False

        # Configure GPIO for digital sensors
        GPIO.setmode(GPIO.BOARD)

        # Setup KY026 flame detection sensor pins
        self._ky026_pins = [KY026_PIN_1, KY026_PIN_2, KY026_PIN_3, KY026_PIN_4]
        for pin in self._ky026_pins:
            if pin is not None:
                GPIO.setup(pin, GPIO.IN)

        # Setup HC-SR04 ultrasonic distance sensor pins
        if HCSR04_TRIGGER_PIN is not None and HCSR04_ECHO_PIN is not None:
            GPIO.setup(HCSR04_TRIGGER_PIN, GPIO.OUT)
            GPIO.setup(HCSR04_ECHO_PIN, GPIO.IN)

    def read_mq2(self):
        """
        Read MQ2 gas/smoke sensor values from both sensors.

        Reads analog values from two MQ2 sensors and returns their average.
        Higher values indicate higher concentration of combustible gases.

        Returns:
            int: Average gas sensor reading (0-65535), 0 if sensors unavailable
        """
        if not self._available:
            return 0
        try:
            value1 = self._mq2_chan1.value  # First MQ2 sensor
            value2 = self._mq2_chan2.value  # Second MQ2 sensor
            return int((value1 + value2) / 2)  # Return average reading
        except:
            return 0

    def read_sht31(self):
        """
        Read temperature and humidity from SHT31 sensor.

        Returns:
            tuple: (temperature, humidity) where:
                - temperature (float): Temperature in Celsius
                - humidity (float): Relative humidity as percentage
                Returns (0.0, 0.0) if sensor unavailable
        """
        if not self._available:
            return (0.0, 0.0)
        try:
            temperature = self._sht31.temperature
            humidity = self._sht31.relative_humidity
            return (temperature, humidity)
        except:
            return (0.0, 0.0)

    def read_ky026(self):
        """
        Read flame detection status from KY026 flame sensors.

        KY026 sensors output LOW when flame is detected, so we invert the reading.
        Multiple sensors provide directional flame detection capability.

        Returns:
            list: Boolean list indicating flame detection status for each sensor
                True = flame detected, False = no flame detected
        """
        flame_detected = []
        for pin in self._ky026_pins:
            if pin is not None:
                # KY026 outputs LOW when flame detected, so invert the reading
                flame_detected.append(not GPIO.input(pin))
            else:
                flame_detected.append(False)
        return flame_detected

    def read_hcsr04(self):
        """
        Read distance measurement from HC-SR04 ultrasonic sensor.

        Sends ultrasonic pulse and measures time for echo return to calculate distance.
        Uses sound speed of 343 m/s for distance calculation.

        Returns:
            float: Distance in centimeters, 0.0 if sensor not configured
        """
        if HCSR04_TRIGGER_PIN is None or HCSR04_ECHO_PIN is None:
            return 0.0

        # Send trigger pulse
        GPIO.output(HCSR04_TRIGGER_PIN, GPIO.LOW)
        time.sleep(0.000002)  # Settle time
        GPIO.output(HCSR04_TRIGGER_PIN, GPIO.HIGH)
        time.sleep(0.00001)   # 10us trigger pulse
        GPIO.output(HCSR04_TRIGGER_PIN, GPIO.LOW)

        # Measure echo pulse duration
        pulse_start = time.time()
        while GPIO.input(HCSR04_ECHO_PIN) == 0:
            pulse_start = time.time()

        pulse_end = time.time()
        while GPIO.input(HCSR04_ECHO_PIN) == 1:
            pulse_end = time.time()

        # Calculate distance: (time * speed of sound) / 2
        # Speed of sound = 34300 cm/s, divide by 2 for round trip
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # 34300/2 = 17150

        return round(distance, 2)

    def read_all_sensors(self):
        """
        Read data from all available sensors.

        Performs a comprehensive sensor reading including smoke detection,
        environmental conditions, flame detection, and distance measurement.

        Returns:
            dict: Dictionary containing all sensor readings:
                - "smoke" (int): Gas/smoke sensor reading
                - "temperature" (float): Temperature in Celsius
                - "humidity" (float): Relative humidity percentage
                - "flame" (list): Flame detection status for each sensor
                - "distance" (float): Distance measurement in cm
        """
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